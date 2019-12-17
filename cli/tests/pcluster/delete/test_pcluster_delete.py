"""This module provides unit tests for the functions in the pcluster.delete module."""

from collections import namedtuple

import pytest

import pcluster.commands as commands
import pcluster.utils as utils
from assertpy import assert_that

FakePdeleteArgs = namedtuple("FakePdeleteArgs", "cluster_name config_file nowait keep_logs region")
FAKE_CLUSTER_NAME = "cluster_name"
FAKE_STACK_NAME = utils.get_stack_name(FAKE_CLUSTER_NAME)
LOG_GROUP_TYPE = "AWS::Logs::LogGroup"


def get_fake_pdelete_args(cluster_name="cluster_name", config_file=None, nowait=False, keep_logs=False, region=None):
    """Get a FakePdeleteArgs instance, with None used for any parameters not specified."""
    return FakePdeleteArgs(
        cluster_name=cluster_name, config_file=config_file, nowait=nowait, keep_logs=keep_logs, region=region
    )


@pytest.mark.parametrize(
    "keep_logs,stack_exists,warn_call_count,persist_called,delete_called",
    [
        (True, False, 2, False, False),
        (False, False, 1, False, False),
        (False, True, 0, False, True),
        (True, True, 0, True, True),
    ],
)
def test_delete(mocker, keep_logs, stack_exists, warn_call_count, persist_called, delete_called):
    """Verify that commands.delete behaves as expected."""
    mocker.patch("pcluster.commands.utils.stack_exists").return_value = stack_exists
    mocker.patch("pcluster.commands._persist_cloudwatch_log_groups")
    mocker.patch("pcluster.commands._delete_cluster")
    mocker.patch("pcluster.commands.utils.warn")
    mocker.patch("pcluster.commands.PclusterConfig.init_aws")
    args = get_fake_pdelete_args(keep_logs=keep_logs)

    if not stack_exists:
        with pytest.raises(SystemExit) as sysexit:
            commands.delete(args)
        assert_that(sysexit.value.code).is_equal_to(0)
    else:
        commands.delete(args)

    commands.PclusterConfig.init_aws.called_with(args.config_file)

    assert_that(commands.utils.warn.call_count).is_equal_to(warn_call_count)
    if warn_call_count > 0:
        commands.utils.warn.assert_called_with("Cluster {0} has already been deleted.".format(args.cluster_name))

    assert_that(commands._persist_cloudwatch_log_groups.called).is_equal_to(persist_called)
    if persist_called:
        commands._persist_cloudwatch_log_groups.assert_called_with(args.cluster_name)

    assert_that(commands._delete_cluster.called).is_equal_to(delete_called)
    if delete_called:
        commands._delete_cluster.assert_called_with(args.cluster_name, args.nowait)


@pytest.mark.parametrize(
    "stacks,template",
    [
        ([], {}),
        (
            [{"StackName": FAKE_STACK_NAME}, {"StackName": "substack_one"}],
            {"Resources": {"key": {"DeletionPolicy": "Retain"}}},
        ),
        ([{"StackName": FAKE_STACK_NAME}], {"Resources": {"key": {"DeletionPolicy": "Don't Retain"}}}),
        ([{"StackName": FAKE_STACK_NAME}], {"Resources": {"key": {"DeletionPolicy": "Delete"}}}),
    ],
)
def test_persist_cloudwatch_log_groups(mocker, stacks, template):
    """Verify that commands._persist_cloudwatch_log_groups behaves as expected."""
    mocker.patch("pcluster.commands.utils.get_cluster_substacks").return_value = stacks
    mocker.patch("pcluster.commands.utils.get_stack_template").return_value = template
    mocker.patch("pcluster.commands._persist_stack_resources")
    if template.get("Resources", {}).get("key", {}).get("DeletionPolicy") == "Retain":
        keys = ["key"]
        expected_persist_cloudwatch_log_groups_call_count = len(stacks)
    else:
        keys = []
        expected_persist_cloudwatch_log_groups_call_count = 0
    mocker.patch("pcluster.commands._get_unretained_cw_log_group_resource_keys").return_value = keys
    commands._persist_cloudwatch_log_groups(FAKE_CLUSTER_NAME)
    commands.utils.get_cluster_substacks.assert_called_with(FAKE_CLUSTER_NAME)
    assert_that(commands.utils.get_stack_template.call_count).is_equal_to(len(stacks))
    assert_that(commands._get_unretained_cw_log_group_resource_keys.call_count).is_equal_to(len(stacks))
    assert_that(commands._persist_stack_resources.call_count).is_equal_to(
        expected_persist_cloudwatch_log_groups_call_count
    )


@pytest.mark.parametrize(
    "template",
    [
        {},
        {"Resources": {}},
        {"Resources": {"key": {}}},
        {"Resources": {"key": {"DeletionPolicy": "Don't Retain"}}},
        {"Resources": {"key": {"DeletionPolicy": "Delete"}}},
        {"Resources": {"key": {"DeletionPolicy": "Retain"}}},  # Note update_stack_template still called for this
    ],
)
def test_persist_stack_resources(mocker, template):
    """Verify that commands._persist_stack_resources behaves as expected."""
    mocker.patch("pcluster.commands.utils.update_stack_template")
    stack = {"StackName": FAKE_STACK_NAME, "Parameters": {"Some Key": "Some Values"}}

    if "Resources" not in template:
        expected_error_message = "Resources"
    elif "key" not in template.get("Resources"):
        expected_error_message = "key"
    else:
        expected_error_message = None

    if expected_error_message:
        with pytest.raises(KeyError, match=expected_error_message):
            commands._persist_stack_resources(stack, template, ["key"])
        assert_that(commands.utils.update_stack_template.called).is_false()
    else:
        commands._persist_stack_resources(stack, template, ["key"])
        commands.utils.update_stack_template.assert_called_with(
            stack.get("StackName"), template, stack.get("Parameters")
        )
        assert_that(template["Resources"]["key"]["DeletionPolicy"]).is_equal_to("Retain")


@pytest.mark.parametrize(
    "template,expected_return",
    [
        ({}, []),
        ({"Resources": {}}, []),
        ({"Resources": {"ResourceOne": {"Type": LOG_GROUP_TYPE, "DeletionPolicy": "Retain"}}}, []),
        ({"Resources": {"ResourceOne": {"Type": LOG_GROUP_TYPE, "DeletionPolicy": "NotRetain"}}}, ["ResourceOne"]),
        ({"Resources": {"ResourceOne": {"Type": LOG_GROUP_TYPE, "DeletionPolicy": "Delete"}}}, ["ResourceOne"]),
    ],
)
def test_get_unretained_cw_log_group_resource_keys(template, expected_return):
    """Verify that commands._get_unretained_cw_log_group_resource_keys behaves as expected."""
    observed_return = commands._get_unretained_cw_log_group_resource_keys(template)
    assert_that(observed_return) == expected_return
