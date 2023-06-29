from time import sleep

from typing import Dict

from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk.core import CfnTag, Construct, NestedStack, Stack, Fn, Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_lambda as _lambda
from pcluster.config.cluster_config import LoginNodesPool, SlurmClusterConfig
from pcluster.constants import PCLUSTER_LOGIN_NODES_POOL_NAME_TAG
from pcluster.templates.cdk_builder_utils import (
    CdkLaunchTemplateBuilder,
    get_default_instance_tags,
    get_default_volume_tags,
    get_login_nodes_security_groups_full,
)
from pcluster.utils import get_http_tokens_setting


class Pool(Construct):
    """Construct defining Login Nodes Pool specific resources."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        pool: LoginNodesPool,
        config: SlurmClusterConfig,
        shared_storage_infos,
        shared_storage_mount_dirs: Dict,
        shared_storage_attributes: Dict,
        login_security_group,
        stack_name,
    ):
        super().__init__(scope, id)
        self._pool = pool
        self._config = config
        self._login_nodes_stack_id = id
        self._shared_storage_infos = shared_storage_infos
        self._shared_storage_mount_dirs = shared_storage_mount_dirs
        self._shared_storage_attributes = shared_storage_attributes
        self._login_security_group = login_security_group
        self.stack_name = stack_name

        self._add_resources()

    def _add_resources(self):
        self._vpc = ec2.Vpc.from_vpc_attributes(
            self,
            f"VPC{self._pool.name}",
            vpc_id=self._config.vpc_id,
            availability_zones=self._pool.networking.az_list,
        )
        self._login_nodes_pool_target_group = self._add_login_nodes_pool_target_group()
        self._login_nodes_pool_load_balancer = self._add_login_nodes_pool_load_balancer(
            self._login_nodes_pool_target_group
        )

        self._launch_template = self._add_login_nodes_pool_launch_template()
        self._add_login_nodes_pool_auto_scaling_group()

    def _add_lifecycle_hook_lambda(self):
        """Create a Lambda function to handle the ASG lifecycle hook."""
        lifecycle_hook_function = _lambda.Function(
            self, "LifecycleHookFunction",
            code=_lambda.Code.from_inline(
                """
import json
import boto3
import time
import os

def handler(event, context):
    print(f"Received event: {event}")
    asg = boto3.client('autoscaling')
    
    message = json.loads(event['Records'][0]['Sns']['Message'])
    lifecycle_hook_name = message['LifecycleHookName']
    ec2_instance_id = message['EC2InstanceId']
    asg_group_name = message['AutoScalingGroupName']
    lifecycle_action_token = message['LifecycleActionToken']

    gracetime = int(os.environ['GRACETIME']) # read gracetime from environment variable

    try:
        time.sleep(gracetime)

        # tell ASG to complete the lifecycle action so it can terminate the instance
        asg.complete_lifecycle_action(
            LifecycleHookName=lifecycle_hook_name,
            AutoScalingGroupName=asg_group_name,
            LifecycleActionResult='CONTINUE',
            InstanceId=ec2_instance_id,
            LifecycleActionToken=lifecycle_action_token
        )

    except Exception as e:
        asg.complete_lifecycle_action(
            LifecycleHookName=lifecycle_hook_name,
            AutoScalingGroupName=asg_group_name,
            LifecycleActionResult='ABANDON',
            InstanceId=ec2_instance_id,
            LifecycleActionToken=lifecycle_action_token
        )

        print(f"Error handling lifecycle hook: {e}")
                """
            ),
            handler="index.handler",
            timeout=Duration.seconds(  # additional 300 seconds is for the lambda running time
                self._pool.gracetime_period * 60 + 300
            ),
            runtime=_lambda.Runtime.PYTHON_3_9,
            role=self.LogAutoScalingEventRole,
            environment={  # pass the gracetime as an environment variable
                "GRACETIME": str(self._pool.gracetime_period * 60)
            }
        )
        return lifecycle_hook_function

    def _add_login_nodes_pool_launch_template(self):
        login_nodes_pool_lt_security_groups = get_login_nodes_security_groups_full(
            self._login_security_group,
            self._pool,
        )
        login_nodes_pool_lt_nw_interface = [
            ec2.CfnLaunchTemplate.NetworkInterfaceProperty(
                device_index=0,
                interface_type=None,
                groups=login_nodes_pool_lt_security_groups,
                subnet_id=self._pool.networking.subnet_ids[0],
            )
        ]

        # User data to setup and run the daemon script
        user_data = """echo -e '#!/bin/bash
while true; do
  TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
  LIFECYCLE_STATE=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -v http://169.254.169.254/latest/meta-data/autoscaling/target-lifecycle-state)
  if [[ $LIFECYCLE_STATE == "Terminated" ]]; then
    /opt/parallelcluster/scripts/termination_script.sh
  fi
  sleep 60
done' > /opt/parallelcluster/scripts/daemon_script.sh

echo -e '#!/bin/bash
DEFAULT_USER=''
OS=$(cat /etc/os-release | grep '^ID=' | cut -f2 -d'"')
if [[ $OS == "amzn" ]]; then
    DEFAULT_USER='ec2-user'
elif [[ $OS == "centos" ]]; then
    DEFAULT_USER='centos'
elif [[ $OS == "ubuntu" ]]; then
    DEFAULT_USER='ubuntu'
elif [[ $OS == "rhel" ]]; then
    DEFAULT_USER='ec2-user'
fi
# Prevent further login/SSH attempts by updating ssh config
echo "AllowUsers $DEFAULT_USER" >> /etc/ssh/sshd_config

# Reload the ssh configuration
systemctl reload sshd

# Broadcast a message to all logged in users using the wall command
MSG="System is going down for termination in {0} minutes!"
wall "$MSG"' > /opt/parallelcluster/scripts/termination_script.sh

chmod +x /opt/parallelcluster/scripts/*.sh
nohup /opt/parallelcluster/scripts/daemon_script.sh > /var/log/daemon_script.log 2>&1 &
""".format(self._pool.gracetime_period)

        return ec2.CfnLaunchTemplate(
            self,
            f"LoginNodeLaunchTemplate{self._pool.name}",
            launch_template_name=f"{self.stack_name}-{self._pool.name}",
            launch_template_data=ec2.CfnLaunchTemplate.LaunchTemplateDataProperty(
                image_id=self._config.login_nodes_ami[self._pool.name],
                instance_type=self._pool.instance_type,
                key_name=self._pool.ssh.key_name,
                user_data=Fn.base64(user_data),
                metadata_options=ec2.CfnLaunchTemplate.MetadataOptionsProperty(
                    http_tokens=get_http_tokens_setting(self._config.imds.imds_support)
                ),
                network_interfaces=login_nodes_pool_lt_nw_interface,
                tag_specifications=[
                    ec2.CfnLaunchTemplate.TagSpecificationProperty(
                        resource_type="instance",
                        tags=get_default_instance_tags(
                            self.stack_name, self._config, self._pool, "LoginNode", self._shared_storage_infos
                        )
                        + [CfnTag(key=PCLUSTER_LOGIN_NODES_POOL_NAME_TAG, value=self._pool.name)],
                    ),
                    ec2.CfnLaunchTemplate.TagSpecificationProperty(
                        resource_type="volume",
                        tags=get_default_volume_tags(self.stack_name, "LoginNode")
                        + [CfnTag(key=PCLUSTER_LOGIN_NODES_POOL_NAME_TAG, value=self._pool.name)],
                    ),
                ],
            ),
        )

    def _add_login_nodes_pool_auto_scaling_group(self):
        launch_template_specification = autoscaling.CfnAutoScalingGroup.LaunchTemplateSpecificationProperty(
            launch_template_id=self._launch_template.ref,
            version=self._launch_template.attr_latest_version_number,
        )

        auto_scaling_group = autoscaling.CfnAutoScalingGroup(
            self,
            f"{self._login_nodes_stack_id}-AutoScalingGroup",
            launch_template=launch_template_specification,
            min_size=str(self._pool.count),
            max_size=str(self._pool.count),
            desired_capacity=str(self._pool.count),
            target_group_arns=[self._login_nodes_pool_target_group.node.default_child.ref],
            vpc_zone_identifier=self._pool.networking.subnet_ids,
        )

        self._add_lifecycle_hook(auto_scaling_group)

        return auto_scaling_group

    def _add_lifecycle_hook(self, auto_scaling_group):
        self.LogAutoScalingEventRole = self._get_iam_role()
        self.lifecycle_hook_function = self._add_lifecycle_hook_lambda()

        lifecycle_topic = sns.Topic(self, "lifecycleTopic")
        lifecycle_topic.add_subscription(subscriptions.LambdaSubscription(self.lifecycle_hook_function))

        return autoscaling.CfnLifecycleHook(
            self,
            "LoginNodesASGLifecycleHook",
            auto_scaling_group_name=auto_scaling_group.ref,
            lifecycle_transition="autoscaling:EC2_INSTANCE_TERMINATING",
            notification_target_arn=lifecycle_topic.topic_arn,
            role_arn=self.LogAutoScalingEventRole.role_arn,
        )

    def _get_iam_role(self):
        role = iam.Role(
            self,
            "LifecycleHookExecutionRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("autoscaling.amazonaws.com"),
            ),
        )
        role.add_to_policy(
            iam.PolicyStatement(
                resources=["*"],
                actions=[
                    "autoscaling:CompleteLifecycleAction",
                    "autoscaling:RecordLifecycleActionHeartbeat",
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "lambda:InvokeFunction",
                    "sns:Publish",
                ]
            )
        )

        return role

    def _add_login_nodes_pool_target_group(self):
        return elbv2.NetworkTargetGroup(
            self,
            f"{self._pool.name}TargetGroup",
            health_check=elbv2.HealthCheck(
                port="22",
                protocol=elbv2.Protocol.TCP,
            ),
            port=22,
            protocol=elbv2.Protocol.TCP,
            target_type=elbv2.TargetType.INSTANCE,
            vpc=self._vpc,
        )

    def _add_login_nodes_pool_load_balancer(
        self,
        target_group,
    ):
        login_nodes_load_balancer = elbv2.NetworkLoadBalancer(
            self,
            f"{self._pool.name}LoadBalancer",
            vpc=self._vpc,
            internet_facing=self._pool.networking.is_subnet_public,
            vpc_subnets=ec2.SubnetSelection(
                subnets=[
                    ec2.Subnet.from_subnet_id(self, f"LoginNodesSubnet{i}", subnet_id)
                    for i, subnet_id in enumerate(self._pool.networking.subnet_ids)
                ]
            ),
        )

        listener = login_nodes_load_balancer.add_listener(f"LoginNodesListener{self._pool.name}", port=22)
        listener.add_target_groups(f"LoginNodesListenerTargets{self._pool.name}", target_group)
        return login_nodes_load_balancer


class LoginNodesStack(NestedStack):
    """Stack encapsulating a set of LoginNodes and the associated resources."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        cluster_config: SlurmClusterConfig,
        shared_storage_infos: Dict,
        shared_storage_mount_dirs: Dict,
        shared_storage_attributes: Dict,
        login_security_group,
    ):
        super().__init__(scope, id)
        self._login_nodes = cluster_config.login_nodes
        self._config = cluster_config
        self._login_security_group = login_security_group
        self._launch_template_builder = CdkLaunchTemplateBuilder()
        self._shared_storage_infos = shared_storage_infos
        self._shared_storage_mount_dirs = shared_storage_mount_dirs
        self._shared_storage_attributes = shared_storage_attributes

        self._add_resources()

    @property
    def stack_name(self):
        """Name of the CFN stack."""
        return Stack.of(self.nested_stack_parent).stack_name

    def _add_resources(self):
        self.pools = {}
        for pool in self._login_nodes.pools:
            pool_construct = Pool(
                self,
                f"Pool{pool.name}",
                pool,
                self._config,
                self._shared_storage_infos,
                self._shared_storage_mount_dirs,
                self._shared_storage_attributes,
                self._login_security_group,
                self.stack_name,
            )
            self.pools[pool.name] = pool_construct
