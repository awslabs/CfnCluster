# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.
import logging
import time
from typing import List, Union

import boto3
from assertpy import assert_that, soft_assertions
from constants import NodeType
from remote_command_executor import RemoteCommandExecutor
from retrying import RetryError, retry
from time_utils import minutes, seconds
from utils import (
    get_cfn_resources,
    get_cluster_nodes_instance_ids,
    get_compute_nodes_instance_count,
    get_compute_nodes_instance_ids,
    get_compute_nodes_instance_ips,
)

from tests.common.scaling_common import get_compute_nodes_allocation
from tests.common.utils import get_ddb_item


@retry(wait_fixed=seconds(20), stop_max_delay=minutes(5))
def wait_instance_replaced_or_terminating(instance_id, region):
    assert_instance_replaced_or_terminating(instance_id, region)


def assert_instance_replaced_or_terminating(instance_id, region):
    """Assert that a given instance got replaced or is marked as Unhealthy."""
    ec2_response = boto3.client("ec2", region_name=region).describe_instances(InstanceIds=[instance_id])
    assert_that(ec2_response["Reservations"][0]["Instances"][0]["State"]["Name"]).is_in("shutting-down", "terminated")


def assert_no_errors_in_logs(remote_command_executor, scheduler, skip_ice=False, ignore_patterns=None):
    __tracebackhide__ = True

    ice_patterns = [
        "InsufficientInstanceCapacity",
        "Insufficient capacity",
        "Failed to launch instances due to limited EC2 capacity",
    ]

    patterns_to_ignore = []
    if skip_ice:
        patterns_to_ignore += ice_patterns
    if ignore_patterns:
        patterns_to_ignore += ignore_patterns
    if scheduler == "slurm":
        log_files = [
            "/var/log/parallelcluster/clustermgtd",
            "/var/log/parallelcluster/clusterstatusmgtd",
            "/var/log/parallelcluster/slurm_resume.log",
            "/var/log/parallelcluster/slurm_suspend.log",
            "/var/log/parallelcluster/slurm_fleet_status_manager.log",
        ]
    else:
        log_files = []

    for log_file in log_files:
        log_file_user = remote_command_executor.get_user_to_operate_on_file(log_file)
        log = remote_command_executor.run_remote_command(f"sudo -u {log_file_user} cat {log_file}", hide=True).stdout
        log = "\n".join(
            [line for line in log.splitlines() if not any(pattern in line for pattern in patterns_to_ignore)]
        )
        for error_level in ["CRITICAL", "ERROR"]:
            assert_that(log).does_not_contain(error_level)


def assert_no_msg_in_logs(remote_command_executor: RemoteCommandExecutor, log_files: List[str], log_msg: List[str]):
    """Assert log msgs are not in logs."""
    __tracebackhide__ = True
    log = ""
    for log_file in log_files:
        log_file_user = remote_command_executor.get_user_to_operate_on_file(log_file)
        log += remote_command_executor.run_remote_command(f"sudo -u {log_file_user} cat {log_file}", hide=True).stdout
    for message in log_msg:
        assert_that(log).does_not_contain(message)


def assert_msg_in_log(remote_command_executor: RemoteCommandExecutor, log_file: str, message: str):
    """Assert message is in log_file."""
    __tracebackhide__ = True
    log_file_user = remote_command_executor.get_user_to_operate_on_file(log_file)
    log = remote_command_executor.run_remote_command(f"sudo -u {log_file_user} cat {log_file}", hide=True).stdout
    assert_that(log).contains(message)


def assert_lines_in_logs(remote_command_executor: RemoteCommandExecutor, log_files, expected_errors):
    # assert every expected error exists in at least one of the log files
    __tracebackhide__ = True

    log = ""
    for log_file in log_files:
        log_file_user = remote_command_executor.get_user_to_operate_on_file(log_file)
        log += remote_command_executor.run_remote_command(f"sudo -u {log_file_user} cat {log_file}", hide=True).stdout
    for message in expected_errors:
        assert_that(log).matches(message)


def submit_job_and_assert_logs(
    scheduler_commands,
    remote_command_executor: RemoteCommandExecutor,
    job_kwargs: dict,
    log_files: list,
    log_assertions: Union[list, iter],
    wait_for_job_completion: bool = False,
    clear_logs_before_job_submission: bool = False,
):
    """Submit a job based on specific keyword-arguments and assert log patterns in specific log files."""
    if clear_logs_before_job_submission:
        for log_file in log_files:
            remote_command_executor.clear_log_file(log_file)

    result = scheduler_commands.submit_command(**job_kwargs)
    job_id = scheduler_commands.assert_job_submitted(result.stdout)
    if wait_for_job_completion:
        try:
            scheduler_commands.wait_job_completed(job_id, timeout=2)
        except RetryError as e:
            # Timeout waiting for job to be completed
            logging.info("Exception while waiting for job to complete: %s", e)
    retry(wait_fixed=seconds(20), stop_max_delay=minutes(3))(assert_lines_in_logs)(
        remote_command_executor, log_files, log_assertions
    )
    scheduler_commands.cancel_job(job_id)


def assert_no_node_in_ec2(region, stack_name, instance_types=None):
    assert_that(get_compute_nodes_instance_count(stack_name, region, instance_types)).is_equal_to(0)


def assert_scaling_worked(
    scheduler_commands,
    region,
    stack_name,
    scaledown_idletime,
    expected_max,
    expected_final,
    assert_ec2=True,
    assert_scheduler=True,
):
    jobs_execution_time = 1
    estimated_scaleup_time = 5
    max_scaledown_time = 10
    ec2_capacity_time_series, compute_nodes_time_series, _ = get_compute_nodes_allocation(
        scheduler_commands=scheduler_commands,
        region=region,
        stack_name=stack_name,
        max_monitoring_time=minutes(jobs_execution_time)
        + minutes(scaledown_idletime)
        + minutes(estimated_scaleup_time)
        + minutes(max_scaledown_time),
    )

    with soft_assertions():
        if assert_ec2:
            ec2_capacity_time_series_str = f"ec2_capacity_time_series={ec2_capacity_time_series}"
            assert_that(max(ec2_capacity_time_series)).described_as(ec2_capacity_time_series_str).is_equal_to(
                expected_max
            )
            assert_that(ec2_capacity_time_series[-1]).described_as(ec2_capacity_time_series_str).is_equal_to(
                expected_final
            )
        if assert_scheduler:
            compute_nodes_time_series_str = f"compute_nodes_time_series={compute_nodes_time_series}"
            assert_that(max(compute_nodes_time_series)).described_as(compute_nodes_time_series_str).is_equal_to(
                expected_max
            )
            assert_that(compute_nodes_time_series[-1]).described_as(compute_nodes_time_series_str).is_equal_to(
                expected_final
            )


@retry(wait_fixed=seconds(20), stop_max_delay=minutes(5))
def wait_for_num_instances_in_cluster(cluster_name, region, desired):
    return assert_num_instances_in_cluster(cluster_name, region, desired)


def assert_num_instances_in_cluster(cluster_name, region, desired):
    instances = get_compute_nodes_instance_ids(cluster_name, region)
    assert_that(instances).is_length(desired)
    return instances


@retry(wait_fixed=seconds(20), stop_max_delay=minutes(5))
def wait_for_num_instances_in_queue(cluster_name, region, desired, queue):
    return assert_num_instances_in_queue(cluster_name, region, desired, queue)


def assert_num_instances_in_queue(cluster_name, region, desired, queue):
    instances = get_cluster_nodes_instance_ids(cluster_name, region, node_type="Compute", queue_name=queue)
    assert_that(instances).is_length(desired)
    return instances


def assert_num_instances_constant(cluster_name, region, desired, timeout=5):
    """Assert number of cluster instances if constant during a time period."""
    logging.info("Waiting for cluster daemon action")
    start_time = time.time()
    while time.time() < start_time + 60 * (timeout):
        assert_num_instances_in_cluster(cluster_name, region, desired)


def assert_head_node_is_running(region, cluster):
    logging.info("Asserting the head node is running")
    head_node_state = (
        boto3.client("ec2", region_name=region)
        .describe_instances(Filters=[{"Name": "ip-address", "Values": [cluster.head_node_ip]}])
        .get("Reservations")[0]
        .get("Instances")[0]
        .get("State")
        .get("Name")
    )
    assert_that(head_node_state).is_equal_to("running")


def assert_cluster_imds_v2_requirement_status(region, cluster, status):
    logging.info(f"Checking that all the nodes in the cluster have IMDSv2 {status}")

    describe_response = boto3.client("ec2", region_name=region).describe_instances(
        Filters=[
            {"Name": "tag:parallelcluster:cluster-name", "Values": [cluster.cfn_name]},
        ]
    )

    for reservations in describe_response.get("Reservations"):
        for instance in reservations.get("Instances"):
            assert_instance_has_desired_imds_v2_setting(instance, status)


def assert_instance_has_desired_imds_v2_setting(instance, status):
    instance_id = instance.get("InstanceId")
    instance_name = [tag["Value"] for tag in instance.get("Tags") if tag["Key"] == "Name"]
    instance_name_part = f" ({instance_name[0]})" if instance_name else ""
    imds_v2_status = instance.get("MetadataOptions").get("HttpTokens")

    logging.info(f"Instance {instance_id}{instance_name_part} has IMDSv2 {imds_v2_status}")

    assert_that(imds_v2_status).is_equal_to(status)


def assert_instance_has_desired_tags(instance, tags: List[dict]):
    instance_id = instance.get("InstanceId")
    instance_tags = instance.get("Tags")
    instance_name = [tag["Value"] for tag in instance_tags if tag["Key"] == "Name"]
    instance_name_part = f" ({instance_name[0]})" if instance_name else ""

    logging.info(f"Instance {instance_id}{instance_name_part} has tags {instance_tags}")

    for tag in tags:
        assert_that(instance_tags).contains(tag)


def assert_aws_identity_access_is_correct(cluster, users_allow_list, remote_command_executor=None):
    logging.info("Asserting access to AWS caller identity is correct")

    if not remote_command_executor:
        remote_command_executor = RemoteCommandExecutor(cluster)

    for user, allowed in users_allow_list.items():
        logging.info(f"Asserting access to AWS caller identity is {'allowed' if allowed else 'denied'} for user {user}")
        command = f"sudo -u {user} aws sts get-caller-identity --region {cluster.region}"
        result = remote_command_executor.run_remote_command(command, raise_on_error=False)
        logging.info(f"user={user} and result.failed={result.failed}")
        logging.info(f"user={user} and result.stdout={result.stdout}")
        assert_that(result.failed).is_equal_to(not allowed)


def assert_default_user_has_desired_sudo_access(
    cluster,
    node_type,
    region,
    disable_sudo_access_default_user,
):
    remote_command_executors = []
    logging.info(
        f"Asserting sudo access is {'disabled' if disable_sudo_access_default_user else 'enabled'} "
        + f"for default user in node {node_type.value}"
    )
    if node_type == NodeType.HEAD_NODE:
        remote_command_executors.append(RemoteCommandExecutor(cluster))
    elif node_type == NodeType.COMPUTE_NODES:
        for compute_node_ip in get_compute_nodes_instance_ips(cluster.name, region):
            remote_command_executors.append(RemoteCommandExecutor(cluster, compute_node_ip=compute_node_ip))
    elif node_type == NodeType.LOGIN_NODES:
        remote_command_executors.append(RemoteCommandExecutor(cluster, use_login_node=True))

    command = "sudo -n cat /etc/sudoers.d/90-cloud-init-users"
    for node_index, remote_command_executor in enumerate(remote_command_executors):
        result = remote_command_executor.run_remote_command(command, raise_on_error=False, timeout=300)
        logging.info(f"Default user in {node_type} number {node_index} and result.failed={result.failed}")
        logging.info(f"Default user in {node_type}  number {node_index} and result.stdout={result.stdout}")
        if disable_sudo_access_default_user:
            assert_that(result.stdout).contains("a password is required")
        assert_that(result.failed).is_equal_to(disable_sudo_access_default_user)


def assert_lambda_vpc_settings_are_correct(stack_name, region, security_group_ids, subnet_ids):
    logging.info("Checking the cleanup lambda VPC config")

    lambda_client = boto3.client("lambda", region_name=region)
    iam_client = boto3.client("iam", region_name=region)

    lambda_functions = [
        res for res in get_cfn_resources(stack_name, region) if res["ResourceType"] == "AWS::Lambda::Function"
    ]

    for lambda_function in lambda_functions:
        function = lambda_client.get_function(FunctionName=lambda_function["PhysicalResourceId"])["Configuration"]
        policies = {
            policy["PolicyName"]
            for policy in iam_client.list_attached_role_policies(RoleName=function["Role"].split("/")[-1])[
                "AttachedPolicies"
            ]
        }

        assert_that(function["VpcConfig"]["SecurityGroupIds"]).is_equal_to(security_group_ids)
        assert_that(function["VpcConfig"]["SubnetIds"]).is_equal_to(subnet_ids)
        assert_that(policies).contains("AWSLambdaVPCAccessExecutionRole")


def wait_for_slurm_rebooted_nodes(
    compute_nodes,
    remote_command_executor,
    wait_fixed_secs: int = 10,
    stop_max_delay_secs: int = 300,
):
    """
    Wait for compute nodes to return to service in Slurm.

    This function assumes that the "returned to service" line is not present in the slurmctld.log file
    prior to its call.
    """
    retry(wait_fixed=seconds(wait_fixed_secs), stop_max_delay=seconds(stop_max_delay_secs))(
        _assert_slurm_rebooted_nodes
    )(compute_nodes, remote_command_executor)


def _assert_slurm_rebooted_nodes(compute_nodes, remote_command_executor):
    """
    Assert that compute nodes have returned to service in Slurm.

    Caution: this function will return true even if older "returned to service" lines are found for the requested node.
    """
    for node in compute_nodes:
        assert_msg_in_log(
            remote_command_executor,
            "/var/log/slurmctld.log",
            f"node {node} returned to service",
        )


def assert_instance_config_version_on_ddb(
    cluster, expected_cluster_config_version: str, node_types=("Compute", "LoginNode")
):
    """Verifies that every cluster node stored on DynamoDB the expected cluster config version."""
    for node_type in node_types:
        nodes = cluster.describe_cluster_instances(node_type=node_type)
        n_nodes = len(nodes)
        if n_nodes == 0:
            logging.info(f"No nodes of type {node_type} found to check, skipping")
            continue
        logging.info(
            f"Verifying that all {n_nodes} nodes ({node_type}) stored the expected config version on DDB: "
            f"{expected_cluster_config_version}"
        )
        for node in nodes:
            instance_id = node["instanceId"]
            table_name = f"parallelcluster-{cluster.name}"
            item_id = f"CLUSTER_CONFIG.{instance_id}"
            item = get_ddb_item(cluster.region, table_name, {"Id": item_id})
            assert_that(item, f"DDB record for {instance_id} ({node_type}) exists").is_not_none()
            cluster_config_version_on_ddb = item["Data"]["cluster_config_version"]
            assert_that(
                cluster_config_version_on_ddb,
                f"DDB record for {instance_id} ({node_type}) has the correct config version",
            ).is_equal_to(expected_cluster_config_version)
        logging.info(
            f"Verified that all {n_nodes} nodes ({node_type}) stored the expected config version on DDB: "
            f"{expected_cluster_config_version}"
        )
