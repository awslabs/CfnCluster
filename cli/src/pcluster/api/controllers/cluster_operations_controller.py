# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at http://aws.amazon.com/apache2.0/
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=W0613
import logging
import os
from typing import Dict, List

from pcluster.api.controllers.common import check_cluster_version, configure_aws_region
from pcluster.api.converters import cloud_formation_status_to_cluster_status
from pcluster.api.errors import (
    BadRequestException,
    CreateClusterBadRequestException,
    InternalServiceException,
    NotFoundException,
)
from pcluster.api.models import (
    CloudFormationStatus,
    ClusterConfigurationStructure,
    ClusterInfoSummary,
    CreateClusterBadRequestExceptionResponseContent,
    CreateClusterRequestContent,
    CreateClusterResponseContent,
    DeleteClusterResponseContent,
    DescribeClusterResponseContent,
    EC2Instance,
    InstanceState,
    ListClustersResponseContent,
    Tag,
    UpdateClusterRequestContent,
    UpdateClusterResponseContent,
)
from pcluster.api.models.cluster_status import ClusterStatus
from pcluster.aws.aws_api import AWSApi
from pcluster.aws.common import StackNotFoundError
from pcluster.cli_commands.compute_fleet_status_manager import ComputeFleetStatus
from pcluster.models.cluster import Cluster, ClusterActionError
from pcluster.models.cluster_resources import ClusterStack

LOGGER = logging.getLogger(__name__)


@configure_aws_region(is_query_string_arg=False)
def create_cluster(
    create_cluster_request_content: Dict,
    suppress_validators: List[str] = None,
    validation_failure_level: Dict = None,
    dryrun: bool = None,
    rollback_on_failure: bool = None,
    client_token: str = None,
) -> CreateClusterResponseContent:
    """
    Create a ParallelCluster managed cluster in a given region.

    :param create_cluster_request_content:
    :param suppress_validators: Identifies one or more config validators to suppress. Format:
    ALL|id:$value|level:(info|error|warning)|type:$value
    :param validation_failure_level: Min validation level that will cause the cluster creation to fail.
    Defaults to &#39;ERROR&#39;.
    :param dryrun: Only perform request validation without creating any resource. It can be used to validate the cluster
    configuration. Response code: 200
    :param rollback_on_failure: When set it automatically initiates a cluster stack rollback on failures.
    Defaults to true.
    :param client_token: Idempotency token that can be set by the client so that retries for the same request are
    idempotent
    """
    create_cluster_request_content = CreateClusterRequestContent.from_dict(create_cluster_request_content)
    if create_cluster_request_content.cluster_configuration == "invalid":
        raise CreateClusterBadRequestException(
            CreateClusterBadRequestExceptionResponseContent(configuration_validation_errors=[], message="invalid")
        )

    return CreateClusterResponseContent(
        ClusterInfoSummary(
            cluster_name="nameeee",
            cloudformation_stack_status=CloudFormationStatus.CREATE_COMPLETE,
            cloudformation_stack_arn="arn",
            region="region",
            version="3.0.0",
            cluster_status=ClusterStatus.CREATE_COMPLETE,
        )
    )


@configure_aws_region()
def delete_cluster(cluster_name, region=None, retain_logs=None, client_token=None):
    """
    Initiate the deletion of a cluster.

    :param cluster_name: Name of the cluster
    :type cluster_name: str
    :param region: AWS Region. Defaults to the region the API is deployed to.
    :type region: str
    :param retain_logs: Retain cluster logs on delete. Defaults to True.
    :type retain_logs: bool
    :param client_token: Idempotency token that can be set by the client so that retries for the same request are
    idempotent
    :type client_token: str

    :rtype: DeleteClusterResponseContent
    """
    return DeleteClusterResponseContent(
        cluster=ClusterInfoSummary(
            cluster_name="nameeee",
            cloudformation_stack_status=CloudFormationStatus.CREATE_COMPLETE,
            cloudformation_stack_arn="arn",
            region="region",
            version="3.0.0",
            cluster_status=ClusterStatus.CREATE_COMPLETE,
        )
    )


@configure_aws_region()
def describe_cluster(cluster_name, region=None):
    """
    Get detailed information about an existing cluster.

    :param cluster_name: Name of the cluster
    :type cluster_name: str
    :param region: AWS Region. Defaults to the region the API is deployed to.
    :type region: str

    :rtype: DescribeClusterResponseContent
    """
    try:
        cluster = Cluster(cluster_name)
        cfn_stack = cluster.stack
    except StackNotFoundError:
        raise NotFoundException(
            f"cluster {cluster_name} does not exist or belongs to an incompatible ParallelCluster " "major version."
        )

    if not check_cluster_version(cluster):
        raise BadRequestException(f"cluster {cluster_name} belongs to an incompatible ParallelCluster major version.")

    fleet_status = cluster.compute_fleet_status  # TODO: use Dynamodb client
    if fleet_status == ComputeFleetStatus.UNKNOWN:
        raise InternalServiceException("could not retrieve compute fleet status.")

    config_url = "NOT_AVAILABLE"
    try:
        config_url = cluster.config_presigned_url  # TODO: add config retrieval by version
    except ClusterActionError as e:
        # Do not fail request when S3 bucket is not available
        LOGGER.error(e)

    response = DescribeClusterResponseContent(
        creation_time=cfn_stack.creation_time,
        version=cfn_stack.version,
        cluster_configuration=ClusterConfigurationStructure(s3_url=config_url),  # TODO: add config version
        tags=[Tag(value=tag.get("Value"), key=tag.get("Key")) for tag in cfn_stack.tags],
        cloud_formation_status=cfn_stack.status,
        cluster_name=cluster_name,
        compute_fleet_status=fleet_status.value,
        cloudformation_stack_arn=cfn_stack.id,
        last_updated_time=cfn_stack.last_updated_time,
        region=os.environ.get("AWS_DEFAULT_REGION"),
        cluster_status=cloud_formation_status_to_cluster_status(cfn_stack.status),
    )

    try:
        head_node = cluster.head_node_instance
        response.headnode = EC2Instance(
            instance_id=head_node.id,
            launch_time=head_node.launch_time,
            public_ip_address=head_node.public_ip,
            instance_type=head_node.instance_type,
            state=InstanceState.from_dict(head_node.state),
            private_ip_address=head_node.private_ip,
        )
    except ClusterActionError as e:
        # This should not be treated as a failure cause head node might not be running in some cases
        LOGGER.info(e)

    return response


@configure_aws_region()
def list_clusters(region=None, next_token=None, cluster_status=None):
    """
    Retrieve the list of existing clusters managed by the API. Deleted clusters are not listed by default.

    :param region: List clusters deployed to a given AWS Region. Defaults to the AWS region the API is deployed to.
    :type region: str
    :param next_token: Token to use for paginated requests.
    :type next_token: str
    :param cluster_status: Filter by cluster status.
    :type cluster_status: list | bytes

    :rtype: ListClustersResponseContent
    """
    stacks, next_token = AWSApi.instance().cfn.list_pcluster_stacks(next_token=next_token)
    stacks = [ClusterStack(stack) for stack in stacks]

    cluster_info_list = []
    for stack in stacks:
        current_cluster_status = cloud_formation_status_to_cluster_status(stack.status)
        if not cluster_status or current_cluster_status in cluster_status:
            cluster_info = ClusterInfoSummary(
                cluster_name=stack.cluster_name,
                cloudformation_stack_status=stack.status,
                cloudformation_stack_arn=stack.id,
                region=os.environ.get("AWS_DEFAULT_REGION"),
                version=stack.version,
                cluster_status=current_cluster_status,
            )
            cluster_info_list.append(cluster_info)

    return ListClustersResponseContent(items=cluster_info_list, next_token=next_token)


@configure_aws_region()
def update_cluster(
    update_cluster_request_content: Dict,
    cluster_name,
    suppress_validators=None,
    validation_failure_level=None,
    region=None,
    dryrun=None,
    force_update=None,
    client_token=None,
):
    """
    Update cluster.

    :param update_cluster_request_content:
    :param cluster_name: Name of the cluster
    :type cluster_name: str
    :param suppress_validators: Identifies one or more config validators to suppress.
    Format: ALL|id:$value|level:(info|error|warning)|type:$value
    :type suppress_validators: List[str]
    :param validation_failure_level: Min validation level that will cause the update to fail.
    Defaults to &#39;error&#39;.
    :type validation_failure_level: dict | bytes
    :param region: AWS Region. Defaults to the region the API is deployed to.
    :type region: str
    :param dryrun: Only perform request validation without creating any resource.
    It can be used to validate the cluster configuration and update requirements. Response code: 200
    :type dryrun: bool
    :param force_update: Force update by ignoring the update validation errors.
    :type force_update: bool
    :param client_token: Idempotency token that can be set by the client so that retries for the same request are
    idempotent
    :type client_token: str

    :rtype: UpdateClusterResponseContent
    """
    update_cluster_request_content = UpdateClusterRequestContent.from_dict(update_cluster_request_content)
    return UpdateClusterResponseContent(
        cluster=ClusterInfoSummary(
            cluster_name="nameeee",
            cloudformation_stack_status=CloudFormationStatus.CREATE_COMPLETE,
            cloudformation_stack_arn="arn",
            region="region",
            version="3.0.0",
            cluster_status=ClusterStatus.CREATE_COMPLETE,
        )
    )
