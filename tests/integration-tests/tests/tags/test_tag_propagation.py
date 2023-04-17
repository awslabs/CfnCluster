# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file.
# This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied.
# See the License for the specific language governing permissions and limitations under the License.

import logging

import pytest
from assertpy import assert_that
from remote_command_executor import RemoteCommandExecutor
from retrying import retry
from tags_utils import (
    convert_tags_dicts_to_tags_list,
    get_compute_node_root_volume_tags,
    get_compute_node_tags,
    get_head_node_root_volume_tags,
    get_head_node_tags,
    get_main_stack_tags,
    get_shared_volume_tags,
)
from time_utils import minutes, seconds

from tests.common.schedulers_common import SlurmCommands
from tests.common.utils import get_installed_parallelcluster_version


@pytest.mark.usefixtures("region", "instance")
def test_tag_propagation(pcluster_config_reader, clusters_factory, scheduler, os):
    """
    Verify tags from various sources are propagated to the expected resources.
    Updates cluster configuration and checks tags afterwards as well.

    The following resources are checked for tags:
    - main CFN stack
    - head node
    - head node's root EBS volume
    - compute node (traditional schedulers)
    - compute node's root EBS volume (traditional schedulers)
    - shared EBS volume
    """
    volume_name = "name1"
    cluster_config = pcluster_config_reader(volume_name=volume_name)
    cluster = clusters_factory(cluster_config)

    # Uses helper function to perform the tests
    _check_tag_propagation(cluster, scheduler, os, volume_name)

    cluster.stop()

    # Updates cluster with new configuration
    updated_cluster_config = pcluster_config_reader(config_file="pcluster.config.update.yaml", volume_name=volume_name)
    cluster.update(str(updated_cluster_config), force_update="true")

    cluster.start()

    # Makes sure that the compute nodes have started before checking tags
    _wait_for_compute_fleet_start(cluster)

    # Checks for tag propagation
    _check_tag_propagation(cluster, scheduler, os, volume_name)

    if scheduler == "slurm":
        _test_queue_and_compute_resources_tags(cluster, pcluster_config_reader, scheduler, os, volume_name)


@retry(wait_fixed=seconds(20), stop_max_delay=minutes(5))
def _wait_for_compute_fleet_start(cluster):
    compute_nodes = cluster.get_cluster_instance_ids(node_type="Compute")
    assert_that(compute_nodes).is_length(1)


def _check_tag_propagation(cluster, scheduler, os, volume_name, queue_tags=None, compute_resource_tags=None):
    config_file_tags = {
        "ConfigFileTag": "ConfigFileTagValue",
        "QueueOverrideTag": "ClusterLevelValue",
        "ComputeOverrideTag": "ClusterLevelValue",
    }
    if not queue_tags:
        queue_tags = {
            "QueueTag": "QueueValue",
            "QueueOverrideTag": "QueueLevelValue",
            "ComputeOverrideTag": "QueueLevelValue",
        }
    if not compute_resource_tags:
        compute_resource_tags = {
            "ComputeResourceTag": "ComputeResourceValue",
            "ComputeOverrideTag": "ComputeLevelValue",
        }

    version_tags = {"parallelcluster:version": get_installed_parallelcluster_version()}
    cluster_name_tags = {"parallelcluster:cluster-name": cluster.name}
    test_cases = [
        {
            "resource": "Main CloudFormation Stack",
            "tag_getter": get_main_stack_tags,
            "expected_tags": (version_tags, config_file_tags, cluster_name_tags),
        },
        {
            "resource": "Head Node",
            "tag_getter": get_head_node_tags,
            "expected_tags": (
                cluster_name_tags,
                {"Name": "HeadNode", "parallelcluster:node-type": "HeadNode"},
            ),
        },
        {
            "resource": "Head Node Root Volume",
            "tag_getter": get_head_node_root_volume_tags,
            "expected_tags": (cluster_name_tags, {"parallelcluster:node-type": "HeadNode"}),
            "tag_getter_kwargs": {"cluster": cluster, "os": os},
        },
        {
            "resource": "Compute Node",
            "tag_getter": get_compute_node_tags,
            "expected_tags": (
                cluster_name_tags,
                {"Name": "Compute", "parallelcluster:node-type": "Compute"},
                {**config_file_tags, **queue_tags, **compute_resource_tags},
            ),
            "skip": scheduler == "awsbatch",
        },
        {
            "resource": "Compute Node Root Volume",
            "tag_getter": get_compute_node_root_volume_tags,
            "expected_tags": (
                cluster_name_tags,
                {"parallelcluster:node-type": "Compute"},
                {**config_file_tags, **queue_tags, **compute_resource_tags},
            ),
            "tag_getter_kwargs": {"cluster": cluster, "os": os},
            "skip": scheduler == "awsbatch",
        },
        {
            "resource": "Shared EBS Volume",
            "tag_getter": get_shared_volume_tags,
            "tag_getter_kwargs": {"cluster": cluster, "volume_name": volume_name},
            "expected_tags": (version_tags, config_file_tags, cluster_name_tags),
        },
    ]

    for test_case in test_cases:
        if test_case.get("skip"):
            continue

        logging.info("Verifying tags were propagated to %s", test_case.get("resource"))
        tag_getter = test_case.get("tag_getter")
        # Assume tag getters use lone cluster object arg if none explicitly given
        tag_getter_args = test_case.get("tag_getter_kwargs", {"cluster": cluster})
        observed_tags = tag_getter(**tag_getter_args)
        expected_tags = test_case["expected_tags"]
        assert_that(observed_tags).contains(*convert_tags_dicts_to_tags_list(expected_tags))


def _test_queue_and_compute_resources_tags(cluster, pcluster_config_reader, scheduler, os, volume_name):
    # Test update queue level tags and compute resource level tags with queue update strategy
    command_executor = RemoteCommandExecutor(cluster)
    slurm_commands = SlurmCommands(command_executor)
    result = slurm_commands.submit_command("sleep infinity", constraint="static")
    job_id = slurm_commands.assert_job_submitted(result.stdout)
    slurm_commands.wait_job_running(job_id)

    # Updates cluster with new configuration
    updated_cluster_config = pcluster_config_reader(
        config_file="pcluster.config.update.queue_update.yaml", volume_name=volume_name
    )
    cluster.update(str(updated_cluster_config))

    slurm_commands.assert_job_state(job_id, "RUNNING")
    # check nodes still have old tags before replacement
    _check_tag_propagation(cluster, scheduler, os, volume_name)

    # requeue job to launch new instances for nodes
    command_executor.run_remote_command(f"scontrol requeue {job_id}")
    slurm_commands.wait_job_running(job_id)
    # check new instances have new tags
    new_queue_tags = {
        "QueueTagUpdate": "QueueValueUpdate",
        "QueueOverrideTag": "QueueLevelValueUpdate",
        "ComputeOverrideTag": "QueueLevelValueUpdate",
    }
    new_compute_resource_tags = {
        "ComputeResourceTagUpdate": "ComputeResourceValueUpdate",
        "ComputeOverrideTag": "ComputeLevelValueUpdate",
    }
    _check_tag_propagation(cluster, scheduler, os, volume_name, new_queue_tags, new_compute_resource_tags)
