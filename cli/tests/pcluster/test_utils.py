"""This module provides unit tests for the functions in the pcluster.utils module."""
import os

import pytest
from assertpy import assert_that
from botocore.exceptions import ClientError

import pcluster.utils as utils
from pcluster.aws.aws_api import AWSApi
from pcluster.aws.aws_resources import InstanceTypeInfo
from pcluster.models.cluster import Cluster, ClusterStack
from pcluster.utils import Cache
from tests.pcluster.aws.dummy_aws_api import mock_aws_api
from tests.utils import MockedBoto3Request

FAKE_CLUSTER_NAME = "cluster-name"
FAKE_STACK_NAME = f"parallelcluster-{FAKE_CLUSTER_NAME}"


@pytest.fixture()
def boto3_stubber_path():
    """Specify that boto3_mocker should stub calls to boto3 for the pcluster.utils module."""
    return "pcluster.utils.boto3"


def test_get_stack_name():
    """Test utils.get_stack_name."""
    cluster = dummy_cluster(FAKE_CLUSTER_NAME)
    assert_that(cluster.stack_name).is_equal_to(FAKE_STACK_NAME)


def dummy_cluster_stack():
    """Return dummy cluster stack object."""
    return ClusterStack({"StackName": FAKE_STACK_NAME})


def dummy_cluster(name=FAKE_CLUSTER_NAME, stack=None):
    """Return dummy cluster object."""
    if stack is None:
        stack = dummy_cluster_stack()
    return Cluster(name, stack=stack)


def test_retry_on_boto3_throttling(boto3_stubber, mocker):
    sleep_mock = mocker.patch("pcluster.utils.time.sleep")
    mocked_requests = [
        MockedBoto3Request(
            method="describe_stack_resources",
            response="Error",
            expected_params={"StackName": FAKE_STACK_NAME},
            generate_error=True,
            error_code="Throttling",
        ),
        MockedBoto3Request(
            method="describe_stack_resources",
            response="Error",
            expected_params={"StackName": FAKE_STACK_NAME},
            generate_error=True,
            error_code="Throttling",
        ),
        MockedBoto3Request(
            method="describe_stack_resources", response={}, expected_params={"StackName": FAKE_STACK_NAME}
        ),
    ]
    client = boto3_stubber("cloudformation", mocked_requests)
    utils.retry_on_boto3_throttling(client.describe_stack_resources, StackName=FAKE_STACK_NAME)
    sleep_mock.assert_called_with(5)


def test_get_stack_retry(boto3_stubber, mocker):
    sleep_mock = mocker.patch("pcluster.utils.time.sleep")
    expected_stack = {"StackName": FAKE_STACK_NAME, "CreationTime": 0, "StackStatus": "CREATED"}
    mocked_requests = [
        MockedBoto3Request(
            method="describe_stacks",
            response="Error",
            expected_params={"StackName": FAKE_STACK_NAME},
            generate_error=True,
            error_code="Throttling",
        ),
        MockedBoto3Request(
            method="describe_stacks",
            response={"Stacks": [expected_stack]},
            expected_params={"StackName": FAKE_STACK_NAME},
        ),
    ]
    boto3_stubber("cloudformation", mocked_requests)
    stack = utils.get_stack(FAKE_STACK_NAME)
    assert_that(stack).is_equal_to(expected_stack)
    sleep_mock.assert_called_with(5)


def test_verify_stack_status_retry(boto3_stubber, mocker):
    sleep_mock = mocker.patch("pcluster.utils.time.sleep")
    mocker.patch(
        "pcluster.utils.get_stack",
        side_effect=[{"StackStatus": "CREATE_IN_PROGRESS"}, {"StackStatus": "CREATE_FAILED"}],
    )
    mocked_requests = [
        MockedBoto3Request(
            method="describe_stack_events",
            response="Error",
            expected_params={"StackName": FAKE_STACK_NAME},
            generate_error=True,
            error_code="Throttling",
        ),
        MockedBoto3Request(
            method="describe_stack_events",
            response={"StackEvents": [_generate_stack_event()]},
            expected_params={"StackName": FAKE_STACK_NAME},
        ),
    ]
    client = boto3_stubber("cloudformation", mocked_requests)
    verified = utils.verify_stack_status(FAKE_STACK_NAME, ["CREATE_IN_PROGRESS"], "CREATE_COMPLETE", client)
    assert_that(verified).is_false()
    sleep_mock.assert_called_with(5)


def test_get_stack_events_retry(boto3_stubber, mocker):
    sleep_mock = mocker.patch("pcluster.utils.time.sleep")
    expected_events = [_generate_stack_event()]
    mocked_requests = [
        MockedBoto3Request(
            method="describe_stack_events",
            response="Error",
            expected_params={"StackName": FAKE_STACK_NAME},
            generate_error=True,
            error_code="Throttling",
        ),
        MockedBoto3Request(
            method="describe_stack_events",
            response={"StackEvents": expected_events},
            expected_params={"StackName": FAKE_STACK_NAME},
        ),
    ]
    boto3_stubber("cloudformation", mocked_requests)
    assert_that(utils.get_stack_events(FAKE_STACK_NAME)).is_equal_to(expected_events)
    sleep_mock.assert_called_with(5)


def _generate_stack_event():
    return {
        "LogicalResourceId": "id",
        "ResourceStatus": "status",
        "StackId": "id",
        "EventId": "id",
        "StackName": FAKE_STACK_NAME,
        "Timestamp": 0,
    }


@pytest.mark.parametrize(
    "bucket_prefix", ["test", "test-", "prefix-63-characters-long--------------------------------to-cut"]
)
def test_generate_random_name_with_prefix(bucket_prefix):
    bucket_name = utils.generate_random_name_with_prefix(bucket_prefix)
    max_bucket_name_length = 63
    random_suffix_length = 17  # 16 digits + 1 separator

    pruned_prefix = bucket_prefix[: max_bucket_name_length - len(bucket_prefix) - random_suffix_length]
    assert_that(bucket_name).starts_with(pruned_prefix)
    assert_that(len(bucket_name)).is_equal_to(len(pruned_prefix) + random_suffix_length)

    # Verify bucket name limits: bucket name must be at least 3 and no more than 63 characters long
    assert_that(len(bucket_name)).is_between(3, max_bucket_name_length)


def test_generate_random_prefix():
    prefix = utils.generate_random_prefix()
    assert_that(len(prefix)).is_equal_to(16)


@pytest.mark.parametrize(
    "architecture, supported_oses",
    [
        ("x86_64", ["alinux2", "centos7", "centos8", "ubuntu1804", "ubuntu2004"]),
        ("arm64", ["alinux2", "ubuntu1804", "ubuntu2004", "centos8"]),
    ],
)
def test_get_supported_os_for_architecture(architecture, supported_oses):
    """Verify that the expected OSes are supported based on a given architecture."""
    assert_that(utils.get_supported_os_for_architecture(architecture)).contains_only(
        *supported_oses
    ).does_not_contain_duplicates()


@pytest.mark.parametrize(
    "scheduler, supported_oses",
    [
        ("slurm", ["alinux2", "centos7", "centos8", "ubuntu1804", "ubuntu2004"]),
        ("awsbatch", ["alinux2"]),
    ],
)
def test_get_supported_os_for_scheduler(scheduler, supported_oses):
    """Verify that the expected OSes are supported based on a given architecture."""
    assert_that(utils.get_supported_os_for_scheduler(scheduler)).contains_only(
        *supported_oses
    ).does_not_contain_duplicates()


@pytest.mark.parametrize(
    "snapshot_id, raise_exceptions, error_message",
    [
        ("snap-1234567890abcdef0", False, None),
        ("snap-1234567890abcdef0", True, None),
        ("snap-1234567890abcdef0", False, "Some error message"),
        ("snap-1234567890abcdef0", True, "Some error message"),
    ],
)
def test_get_ebs_snapshot_info(boto3_stubber, snapshot_id, raise_exceptions, error_message):
    """Verify that get_snapshot_info makes the expected API call."""
    response = {
        "Description": "This is my snapshot",
        "Encrypted": False,
        "VolumeId": "vol-049df61146c4d7901",
        "State": "completed",
        "VolumeSize": 120,
        "StartTime": "2014-02-28T21:28:32.000Z",
        "Progress": "100%",
        "OwnerId": "012345678910",
        "SnapshotId": "snap-1234567890abcdef0",
    }
    describe_snapshots_response = {"Snapshots": [response]}

    mocked_requests = [
        MockedBoto3Request(
            method="describe_snapshots",
            response=describe_snapshots_response if error_message is None else error_message,
            expected_params={"SnapshotIds": ["snap-1234567890abcdef0"]},
            generate_error=error_message is not None,
        )
    ]
    boto3_stubber("ec2", mocked_requests)
    if error_message is None:
        assert_that(utils.get_ebs_snapshot_info(snapshot_id, raise_exceptions=raise_exceptions)).is_equal_to(response)
    elif error_message and raise_exceptions:
        with pytest.raises(ClientError, match=error_message) as clienterror:
            utils.get_ebs_snapshot_info(snapshot_id, raise_exceptions=raise_exceptions)
            assert_that(clienterror.value.code).is_not_equal_to(0)
    else:
        with pytest.raises(SystemExit, match=error_message) as sysexit:
            utils.get_ebs_snapshot_info(snapshot_id, raise_exceptions=raise_exceptions)
            assert_that(sysexit.value.code).is_not_equal_to(0)


class TestCache:
    invocations = []

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        utils.Cache.clear_all()

    @pytest.fixture(autouse=True)
    def clear_invocations(self):
        del self.invocations[:]

    @pytest.fixture
    def disabled_cache(self):
        os.environ["PCLUSTER_CACHE_DISABLED"] = "true"
        yield
        del os.environ["PCLUSTER_CACHE_DISABLED"]

    @staticmethod
    @Cache.cached
    def _cached_method_1(arg1, arg2):
        TestCache.invocations.append((arg1, arg2))
        return arg1, arg2

    @staticmethod
    @Cache.cached
    def _cached_method_2(arg1, arg2):
        TestCache.invocations.append((arg1, arg2))
        return arg1, arg2

    def test_cached_method(self):
        for _ in range(0, 2):
            assert_that(self._cached_method_1(1, 2)).is_equal_to((1, 2))
            assert_that(self._cached_method_2(1, 2)).is_equal_to((1, 2))
            assert_that(self._cached_method_1(2, 1)).is_equal_to((2, 1))
            assert_that(self._cached_method_1(1, arg2=2)).is_equal_to((1, 2))
            assert_that(self._cached_method_1(arg1=1, arg2=2)).is_equal_to((1, 2))

        assert_that(self.invocations).is_length(5)

    def test_disabled_cache(self, disabled_cache):
        assert_that(self._cached_method_1(1, 2)).is_equal_to((1, 2))
        assert_that(self._cached_method_1(1, 2)).is_equal_to((1, 2))

        assert_that(self.invocations).is_length(2)

    def test_clear_all(self):
        for _ in range(0, 2):
            assert_that(self._cached_method_1(1, 2)).is_equal_to((1, 2))
            assert_that(self._cached_method_2(1, 2)).is_equal_to((1, 2))

        Cache.clear_all()

        for _ in range(0, 2):
            assert_that(self._cached_method_1(1, 2)).is_equal_to((1, 2))
            assert_that(self._cached_method_2(1, 2)).is_equal_to((1, 2))

        assert_that(self.invocations).is_length(4)


def test_init_from_instance_type(mocker, caplog):
    mock_aws_api(mocker, mock_instance_type_info=False)

    mocker.patch(
        "pcluster.aws.ec2.Ec2Client.get_instance_type_info",
        return_value=InstanceTypeInfo(
            {
                "InstanceType": "c4.xlarge",
                "VCpuInfo": {"DefaultVCpus": 4, "DefaultCores": 2, "DefaultThreadsPerCore": 2},
                "NetworkInfo": {"EfaSupported": False, "MaximumNetworkCards": 1},
                "ProcessorInfo": {"SupportedArchitectures": ["x86_64"]},
            }
        ),
    )
    c4_instance_info = AWSApi.instance().ec2.get_instance_type_info("c4.xlarge")
    assert_that(c4_instance_info.gpu_count()).is_equal_to(0)
    assert_that(caplog.text).is_empty()
    assert_that(c4_instance_info.max_network_interface_count()).is_equal_to(1)
    assert_that(c4_instance_info.default_threads_per_core()).is_equal_to(2)
    assert_that(c4_instance_info.vcpus_count()).is_equal_to(4)
    assert_that(c4_instance_info.supported_architecture()).is_equal_to(["x86_64"])
    assert_that(c4_instance_info.is_efa_supported()).is_equal_to(False)

    mocker.patch(
        "pcluster.aws.ec2.Ec2Client.get_instance_type_info",
        return_value=InstanceTypeInfo(
            {
                "InstanceType": "g4dn.metal",
                "VCpuInfo": {"DefaultVCpus": 96},
                "GpuInfo": {"Gpus": [{"Name": "T4", "Manufacturer": "NVIDIA", "Count": 8}]},
                "NetworkInfo": {"EfaSupported": True, "MaximumNetworkCards": 4},
                "ProcessorInfo": {"SupportedArchitectures": ["x86_64"]},
            }
        ),
    )
    g4dn_instance_info = AWSApi.instance().ec2.get_instance_type_info("g4dn.metal")
    assert_that(g4dn_instance_info.gpu_count()).is_equal_to(8)
    assert_that(caplog.text).is_empty()
    assert_that(g4dn_instance_info.max_network_interface_count()).is_equal_to(4)
    assert_that(g4dn_instance_info.default_threads_per_core()).is_equal_to(2)
    assert_that(g4dn_instance_info.vcpus_count()).is_equal_to(96)
    assert_that(g4dn_instance_info.supported_architecture()).is_equal_to(["x86_64"])
    assert_that(g4dn_instance_info.is_efa_supported()).is_equal_to(True)

    mocker.patch(
        "pcluster.aws.ec2.Ec2Client.get_instance_type_info",
        return_value=InstanceTypeInfo(
            {
                "InstanceType": "g4ad.16xlarge",
                "VCpuInfo": {"DefaultVCpus": 64},
                "GpuInfo": {"Gpus": [{"Name": "*", "Manufacturer": "AMD", "Count": 4}]},
                "NetworkInfo": {"EfaSupported": False, "MaximumNetworkCards": 1},
                "ProcessorInfo": {"SupportedArchitectures": ["x86_64"]},
            }
        ),
    )
    g4ad_instance_info = AWSApi.instance().ec2.get_instance_type_info("g4ad.16xlarge")
    assert_that(g4ad_instance_info.gpu_count()).is_equal_to(0)
    assert_that(caplog.text).matches("not offer native support for 'AMD' GPUs.")
    assert_that(g4ad_instance_info.max_network_interface_count()).is_equal_to(1)
    assert_that(g4ad_instance_info.default_threads_per_core()).is_equal_to(2)
    assert_that(g4ad_instance_info.vcpus_count()).is_equal_to(64)
    assert_that(g4ad_instance_info.supported_architecture()).is_equal_to(["x86_64"])
    assert_that(g4ad_instance_info.is_efa_supported()).is_equal_to(False)


@pytest.mark.parametrize(
    "url, expect_output",
    [
        ("https://test.s3.cn-north-1.amazonaws.com.cn/post_install.sh", "https"),
        (
            "s3://test/post_install.sh",
            "s3",
        ),
    ],
)
def test_get_url_scheme(url, expect_output):
    assert_that(utils.get_url_scheme(url)).is_equal_to(expect_output)
