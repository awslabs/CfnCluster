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
import datetime
import os
import re

import configparser
import pytest
from assertpy import assert_that

import tests.pcluster.config.utils as utils
from pcluster.config.mappings import ALLOWED_VALUES
from pcluster.config.validators import (
    EBS_VOLUME_TYPE_TO_VOLUME_SIZE_BOUNDS,
    FSX_MESSAGES,
    FSX_SUPPORTED_ARCHITECTURES_OSES,
    efa_gdr_validator,
    intel_hpc_architecture_validator,
    queue_validator,
    settings_validator,
)
from tests.common import MockedBoto3Request
from tests.pcluster.config.defaults import DefaultDict


@pytest.fixture()
def boto3_stubber_path():
    return "pcluster.config.validators.boto3"


@pytest.mark.parametrize("instance_type, expected_message", [("t2.micro", None), ("c4.xlarge", None)])
def test_head_node_instance_type_validator(mocker, instance_type, expected_message):
    config_parser_dict = {"cluster default": {"master_instance_type": instance_type}}
    utils.assert_param_validator(mocker, config_parser_dict, expected_message)


def test_ec2_key_pair_validator(mocker, boto3_stubber):
    describe_key_pairs_response = {
        "KeyPairs": [
            {"KeyFingerprint": "12:bf:7c:56:6c:dd:4f:8c:24:45:75:f1:1b:16:54:89:82:09:a4:26", "KeyName": "key1"}
        ]
    }
    mocked_requests = [
        MockedBoto3Request(
            method="describe_key_pairs", response=describe_key_pairs_response, expected_params={"KeyNames": ["key1"]}
        )
    ]
    boto3_stubber("ec2", mocked_requests)

    # TODO test with invalid key
    config_parser_dict = {"cluster default": {"key_name": "key1"}}
    utils.assert_param_validator(mocker, config_parser_dict)


@pytest.mark.parametrize(
    "image_architecture, bad_ami_message, bad_architecture_message",
    [
        ("x86_64", None, None),
        (
            "arm64",
            None,
            "incompatible with the architecture supported by the instance type chosen for the head node",
        ),
        (
            "arm64",
            "Unable to get information for AMI",
            "incompatible with the architecture supported by the instance type chosen for the head node",
        ),
    ],
)
def test_ec2_ami_validator(mocker, boto3_stubber, image_architecture, bad_ami_message, bad_architecture_message):
    describe_images_response = {
        "Images": [
            {
                "VirtualizationType": "paravirtual",
                "Name": "My server",
                "Hypervisor": "xen",
                "ImageId": "ami-12345678",
                "RootDeviceType": "ebs",
                "State": "available",
                "BlockDeviceMappings": [
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "DeleteOnTermination": True,
                            "SnapshotId": "snap-1234567890abcdef0",
                            "VolumeSize": 8,
                            "VolumeType": "standard",
                        },
                    }
                ],
                "Architecture": image_architecture,
                "ImageLocation": "123456789012/My server",
                "KernelId": "aki-88aa75e1",
                "OwnerId": "123456789012",
                "RootDeviceName": "/dev/sda1",
                "Public": False,
                "ImageType": "machine",
                "Description": "An AMI for my server",
            }
        ]
    }
    mocked_requests = [
        MockedBoto3Request(
            method="describe_images",
            response=describe_images_response,
            expected_params={"ImageIds": ["ami-12345678"]},
            generate_error=bad_ami_message,
        )
    ]
    boto3_stubber("ec2", mocked_requests)

    # TODO test with invalid key
    config_parser_dict = {"cluster default": {"custom_ami": "ami-12345678"}}
    expected_message = bad_ami_message or bad_architecture_message
    utils.assert_param_validator(mocker, config_parser_dict, expected_message)


@pytest.mark.parametrize(
    "section_dict, expected_message",
    [
        ({"tags": {"key": "value", "key2": "value2"}}, None),
        (
            {"tags": {"key": "value", "Version": "value2"}},
            r"Version.*reserved",
        ),
    ],
)
def test_tags_validator(mocker, capsys, section_dict, expected_message):
    config_parser_dict = {"cluster default": section_dict}
    utils.assert_param_validator(mocker, config_parser_dict, expected_error=expected_message)


def test_ec2_volume_validator(mocker, boto3_stubber):
    describe_volumes_response = {
        "Volumes": [
            {
                "AvailabilityZone": "us-east-1a",
                "Attachments": [
                    {
                        "AttachTime": "2013-12-18T22:35:00.000Z",
                        "InstanceId": "i-1234567890abcdef0",
                        "VolumeId": "vol-12345678",
                        "State": "attached",
                        "DeleteOnTermination": True,
                        "Device": "/dev/sda1",
                    }
                ],
                "Encrypted": False,
                "VolumeType": "gp2",
                "VolumeId": "vol-049df61146c4d7901",
                "State": "available",  # TODO add test with "in-use"
                "SnapshotId": "snap-1234567890abcdef0",
                "CreateTime": "2013-12-18T22:35:00.084Z",
                "Size": 8,
            }
        ]
    }
    mocked_requests = [
        MockedBoto3Request(
            method="describe_volumes",
            response=describe_volumes_response,
            expected_params={"VolumeIds": ["vol-12345678"]},
        )
    ]
    boto3_stubber("ec2", mocked_requests)

    # TODO test with invalid key
    config_parser_dict = {
        "cluster default": {"ebs_settings": "default"},
        "ebs default": {"shared_dir": "test", "ebs_volume_id": "vol-12345678"},
    }
    utils.assert_param_validator(mocker, config_parser_dict)


@pytest.mark.parametrize(
    "region, base_os, scheduler, expected_message",
    [
        # verify awsbatch supported regions
        ("ap-northeast-3", "alinux", "awsbatch", "scheduler is not supported in the .* region"),
        ("us-gov-east-1", "alinux", "awsbatch", None),
        ("us-gov-west-1", "alinux", "awsbatch", None),
        ("eu-west-1", "alinux", "awsbatch", None),
        ("us-east-1", "alinux", "awsbatch", None),
        ("eu-north-1", "alinux", "awsbatch", None),
        ("cn-north-1", "alinux", "awsbatch", None),
        ("cn-northwest-1", "alinux", "awsbatch", None),
        ("cn-northwest-1", "alinux2", "awsbatch", None),
        # verify traditional schedulers are supported in all the regions
        ("cn-northwest-1", "alinux", "sge", None),
        ("ap-northeast-3", "alinux", "sge", None),
        ("cn-northwest-1", "alinux", "slurm", None),
        ("ap-northeast-3", "alinux", "slurm", None),
        ("cn-northwest-1", "alinux", "torque", None),
        ("ap-northeast-3", "alinux", "torque", None),
        # verify awsbatch supported OSes
        ("eu-west-1", "centos7", "awsbatch", "scheduler supports the following Operating Systems"),
        ("eu-west-1", "centos8", "awsbatch", "scheduler supports the following Operating Systems"),
        ("eu-west-1", "ubuntu1604", "awsbatch", "scheduler supports the following Operating Systems"),
        ("eu-west-1", "ubuntu1804", "awsbatch", "scheduler supports the following Operating Systems"),
        ("eu-west-1", "alinux", "awsbatch", None),
        ("eu-west-1", "alinux2", "awsbatch", None),
        # verify sge supports all the OSes
        ("eu-west-1", "centos7", "sge", None),
        ("eu-west-1", "centos8", "sge", None),
        ("eu-west-1", "ubuntu1604", "sge", None),
        ("eu-west-1", "ubuntu1804", "sge", None),
        ("eu-west-1", "alinux", "sge", None),
        ("eu-west-1", "alinux2", "sge", None),
        # verify slurm supports all the OSes
        ("eu-west-1", "centos7", "slurm", None),
        ("eu-west-1", "centos8", "slurm", None),
        ("eu-west-1", "ubuntu1604", "slurm", None),
        ("eu-west-1", "ubuntu1804", "slurm", None),
        ("eu-west-1", "alinux", "slurm", None),
        ("eu-west-1", "alinux2", "slurm", None),
        # verify torque supports all the OSes
        ("eu-west-1", "centos7", "torque", None),
        ("eu-west-1", "centos8", "torque", None),
        ("eu-west-1", "ubuntu1604", "torque", None),
        ("eu-west-1", "ubuntu1804", "torque", None),
        ("eu-west-1", "alinux", "torque", None),
        ("eu-west-1", "alinux2", "torque", None),
    ],
)
def test_scheduler_validator(mocker, capsys, region, base_os, scheduler, expected_message):
    # we need to set the region in the environment because it takes precedence respect of the config file
    os.environ["AWS_DEFAULT_REGION"] = region
    config_parser_dict = {"cluster default": {"base_os": base_os, "scheduler": scheduler}}
    # Deprecation warning should be printed for sge and torque
    expected_warning = None
    wiki_url = "https://github.com/aws/aws-parallelcluster/wiki/Deprecation-of-SGE-and-Torque-in-ParallelCluster"
    if scheduler in ["sge", "torque"]:
        expected_warning = ".{0}. is scheduled to be deprecated.*{1}".format(scheduler, wiki_url)
    utils.assert_param_validator(mocker, config_parser_dict, expected_message, capsys, expected_warning)


def test_placement_group_validator(mocker, boto3_stubber):
    describe_placement_groups_response = {
        "PlacementGroups": [{"GroupName": "my-cluster", "State": "available", "Strategy": "cluster"}]
    }
    mocked_requests = [
        MockedBoto3Request(
            method="describe_placement_groups",
            response=describe_placement_groups_response,
            expected_params={"GroupNames": ["my-cluster"]},
        )
    ]
    boto3_stubber("ec2", mocked_requests)

    # TODO test with invalid group name
    config_parser_dict = {"cluster default": {"placement_group": "my-cluster"}}
    utils.assert_param_validator(mocker, config_parser_dict)


@pytest.mark.parametrize(
    "config, num_calls, error_code, bucket, expected_message",
    [
        (
            {
                "cluster default": {"fsx_settings": "fsx"},
                "fsx fsx": {
                    "storage_capacity": 1200,
                    "import_path": "s3://test/test1/test2",
                    "export_path": "s3://test/test1/test2",
                    "auto_import_policy": "NEW",
                },
            },
            2,
            None,
            {"Bucket": "test"},
            "AutoImport is not supported for cross-region buckets.",
        ),
        (
            {
                "cluster default": {"fsx_settings": "fsx"},
                "fsx fsx": {
                    "storage_capacity": 1200,
                    "import_path": "s3://test/test1/test2",
                    "export_path": "s3://test/test1/test2",
                    "auto_import_policy": "NEW",
                },
            },
            2,
            "NoSuchBucket",
            {"Bucket": "test"},
            "The S3 bucket 'test' does not appear to exist.",
        ),
        (
            {
                "cluster default": {"fsx_settings": "fsx"},
                "fsx fsx": {
                    "storage_capacity": 1200,
                    "import_path": "s3://test/test1/test2",
                    "export_path": "s3://test/test1/test2",
                    "auto_import_policy": "NEW",
                },
            },
            2,
            "AccessDenied",
            {"Bucket": "test"},
            "You do not have access to the S3 bucket",
        ),
    ],
)
def test_auto_import_policy_validator(mocker, boto3_stubber, config, num_calls, error_code, bucket, expected_message):
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"
    head_bucket_response = {
        "ResponseMetadata": {
            "AcceptRanges": "bytes",
            "ContentType": "text/html",
            "LastModified": "Thu, 16 Apr 2015 18:19:14 GMT",
            "ContentLength": 77,
            "VersionId": "null",
            "ETag": '"30a6ec7e1a9ad79c203d05a589c8b400"',
            "Metadata": {},
        }
    }
    get_bucket_location_response = {
        "ResponseMetadata": {
            "LocationConstraint": "af-south1",
        }
    }
    mocked_requests = []
    for _ in range(num_calls):
        mocked_requests.append(
            MockedBoto3Request(method="head_bucket", response=head_bucket_response, expected_params=bucket)
        )
    if error_code is None:
        mocked_requests.append(
            MockedBoto3Request(
                method="get_bucket_location", response=get_bucket_location_response, expected_params=bucket
            )
        )
    else:
        mocked_requests.append(
            MockedBoto3Request(
                method="get_bucket_location",
                response=get_bucket_location_response,
                expected_params=bucket,
                generate_error=error_code is not None,
                error_code=error_code,
            )
        )

    boto3_stubber("s3", mocked_requests)

    utils.assert_param_validator(mocker, config, expected_message)


@pytest.mark.parametrize(
    "config, num_calls, bucket, expected_message",
    [
        (
            {
                "cluster default": {"fsx_settings": "fsx"},
                "fsx fsx": {
                    "storage_capacity": 1200,
                    "import_path": "s3://test/test1/test2",
                    "export_path": "s3://test/test1/test2",
                },
            },
            2,
            {"Bucket": "test"},
            None,
        ),
        (
            {
                "cluster default": {"fsx_settings": "fsx"},
                "fsx fsx": {
                    "storage_capacity": 1200,
                    "import_path": "http://test/test.json",
                    "export_path": "s3://test/test1/test2",
                },
            },
            1,
            {"Bucket": "test"},
            "The value 'http://test/test.json' used for the parameter 'import_path' is not a valid S3 URI.",
        ),
    ],
)
def test_s3_validator(mocker, boto3_stubber, config, num_calls, bucket, expected_message):
    if bucket:
        _head_bucket_stubber(mocker, boto3_stubber, bucket, num_calls)
    utils.assert_param_validator(mocker, config, expected_message)


def test_ec2_vpc_id_validator(mocker, boto3_stubber):
    mocked_requests = []

    # mock describe_vpc boto3 call
    describe_vpc_response = {
        "Vpcs": [
            {
                "VpcId": "vpc-12345678",
                "InstanceTenancy": "default",
                "Tags": [{"Value": "Default VPC", "Key": "Name"}],
                "State": "available",
                "DhcpOptionsId": "dopt-4ef69c2a",
                "CidrBlock": "172.31.0.0/16",
                "IsDefault": True,
            }
        ]
    }
    mocked_requests.append(
        MockedBoto3Request(
            method="describe_vpcs", response=describe_vpc_response, expected_params={"VpcIds": ["vpc-12345678"]}
        )
    )

    # mock describe_vpc_attribute boto3 call
    describe_vpc_attribute_response = {
        "VpcId": "vpc-12345678",
        "EnableDnsSupport": {"Value": True},
        "EnableDnsHostnames": {"Value": True},
    }
    mocked_requests.append(
        MockedBoto3Request(
            method="describe_vpc_attribute",
            response=describe_vpc_attribute_response,
            expected_params={"VpcId": "vpc-12345678", "Attribute": "enableDnsSupport"},
        )
    )
    mocked_requests.append(
        MockedBoto3Request(
            method="describe_vpc_attribute",
            response=describe_vpc_attribute_response,
            expected_params={"VpcId": "vpc-12345678", "Attribute": "enableDnsHostnames"},
        )
    )
    boto3_stubber("ec2", mocked_requests)

    # TODO mock and test invalid vpc-id
    for vpc_id, expected_message in [("vpc-12345678", None)]:
        config_parser_dict = {"cluster default": {"vpc_settings": "default"}, "vpc default": {"vpc_id": vpc_id}}
        utils.assert_param_validator(mocker, config_parser_dict, expected_message)


def test_ec2_subnet_id_validator(mocker, boto3_stubber):
    describe_subnets_response = {
        "Subnets": [
            {
                "AvailabilityZone": "us-east-2c",
                "AvailabilityZoneId": "use2-az3",
                "AvailableIpAddressCount": 248,
                "CidrBlock": "10.0.1.0/24",
                "DefaultForAz": False,
                "MapPublicIpOnLaunch": False,
                "State": "available",
                "SubnetId": "subnet-12345678",
                "VpcId": "vpc-06e4ab6c6cEXAMPLE",
                "OwnerId": "111122223333",
                "AssignIpv6AddressOnCreation": False,
                "Ipv6CidrBlockAssociationSet": [],
                "Tags": [{"Key": "Name", "Value": "MySubnet"}],
                "SubnetArn": "arn:aws:ec2:us-east-2:111122223333:subnet/subnet-12345678",
            }
        ]
    }
    mocked_requests = [
        MockedBoto3Request(
            method="describe_subnets",
            response=describe_subnets_response,
            expected_params={"SubnetIds": ["subnet-12345678"]},
        )
    ]
    boto3_stubber("ec2", mocked_requests)

    # TODO test with invalid key
    config_parser_dict = {
        "cluster default": {"vpc_settings": "default"},
        "vpc default": {"master_subnet_id": "subnet-12345678"},
    }
    utils.assert_param_validator(mocker, config_parser_dict)


def test_ec2_security_group_validator(mocker, boto3_stubber):
    describe_security_groups_response = {
        "SecurityGroups": [
            {
                "IpPermissionsEgress": [],
                "Description": "My security group",
                "IpPermissions": [
                    {
                        "PrefixListIds": [],
                        "FromPort": 22,
                        "IpRanges": [{"CidrIp": "203.0.113.0/24"}],
                        "ToPort": 22,
                        "IpProtocol": "tcp",
                        "UserIdGroupPairs": [],
                    }
                ],
                "GroupName": "MySecurityGroup",
                "OwnerId": "123456789012",
                "GroupId": "sg-12345678",
            }
        ]
    }
    mocked_requests = [
        MockedBoto3Request(
            method="describe_security_groups",
            response=describe_security_groups_response,
            expected_params={"GroupIds": ["sg-12345678"]},
        )
    ]
    boto3_stubber("ec2", mocked_requests)

    # TODO test with invalid key
    config_parser_dict = {
        "cluster default": {"vpc_settings": "default"},
        "vpc default": {"vpc_security_group_id": "sg-12345678"},
    }
    utils.assert_param_validator(mocker, config_parser_dict)


@pytest.mark.parametrize(
    "kms_key_id, expected_message",
    [
        ("9e8a129be-0e46-459d-865b-3a5bf974a22k", None),
        (
            "9e7a129be-0e46-459d-865b-3a5bf974a22k",
            "Key 'arn:aws:kms:us-east-1:12345678:key/9e7a129be-0e46-459d-865b-3a5bf974a22k' does not exist",
        ),
    ],
)
def test_kms_key_validator(mocker, boto3_stubber, kms_key_id, expected_message):
    _kms_key_stubber(mocker, boto3_stubber, kms_key_id, expected_message, 1)

    config_parser_dict = {
        "cluster default": {"fsx_settings": "fsx"},
        "fsx fsx": {
            "storage_capacity": 1200,
            "fsx_kms_key_id": kms_key_id,
            "deployment_type": "PERSISTENT_1",
            "per_unit_storage_throughput": 50,
        },
    }
    utils.assert_param_validator(
        mocker, config_parser_dict, expected_error=expected_message if expected_message else None
    )


def _kms_key_stubber(mocker, boto3_stubber, kms_key_id, expected_message, num_calls):
    describe_key_response = {
        "KeyMetadata": {
            "AWSAccountId": "1234567890",
            "Arn": "arn:aws:kms:us-east-1:1234567890:key/{0}".format(kms_key_id),
            "CreationDate": datetime.datetime(2019, 1, 10, 11, 25, 59, 128000),
            "Description": "",
            "Enabled": True,
            "KeyId": kms_key_id,
            "KeyManager": "CUSTOMER",
            "KeyState": "Enabled",
            "KeyUsage": "ENCRYPT_DECRYPT",
            "Origin": "AWS_KMS",
        }
    }
    mocked_requests = [
        MockedBoto3Request(
            method="describe_key",
            response=expected_message if expected_message else describe_key_response,
            expected_params={"KeyId": kms_key_id},
            generate_error=True if expected_message else False,
        )
    ] * num_calls
    boto3_stubber("kms", mocked_requests)


@pytest.mark.parametrize(
    "section_dict, bucket, expected_error, num_calls",
    [
        (
            {
                "storage_capacity": 1200,
                "per_unit_storage_throughput": "50",
                "deployment_type": "PERSISTENT_1",
                "automatic_backup_retention_days": 2,
            },
            None,
            None,
            0,
        ),
        (
            {
                "storage_capacity": 1200,
                "deployment_type": "PERSISTENT_1",
                "per_unit_storage_throughput": "50",
                "automatic_backup_retention_days": 2,
                "daily_automatic_backup_start_time": "03:00",
                "copy_tags_to_backups": True,
            },
            None,
            None,
            0,
        ),
    ],
)
def test_fsx_validator(mocker, boto3_stubber, section_dict, bucket, expected_error, num_calls):
    if bucket:
        _head_bucket_stubber(mocker, boto3_stubber, bucket, num_calls)
    if "fsx_kms_key_id" in section_dict:
        _kms_key_stubber(mocker, boto3_stubber, section_dict.get("fsx_kms_key_id"), None, 0 if expected_error else 1)
    config_parser_dict = {"cluster default": {"fsx_settings": "default"}, "fsx default": section_dict}
    if expected_error:
        expected_error = re.escape(expected_error)
    utils.assert_param_validator(mocker, config_parser_dict, expected_error=expected_error)


@pytest.mark.parametrize(
    "section_dict, expected_error, expected_warning",
    [
        ({"storage_capacity": 7200}, None, None),
    ],
)
def test_fsx_storage_capacity_validator(mocker, boto3_stubber, capsys, section_dict, expected_error, expected_warning):
    config_parser_dict = {"cluster default": {"fsx_settings": "default"}, "fsx default": section_dict}
    utils.assert_param_validator(
        mocker, config_parser_dict, capsys=capsys, expected_error=expected_error, expected_warning=expected_warning
    )


def _head_bucket_stubber(mocker, boto3_stubber, bucket, num_calls):
    head_bucket_response = {
        "ResponseMetadata": {
            "AcceptRanges": "bytes",
            "ContentType": "text/html",
            "LastModified": "Thu, 16 Apr 2015 18:19:14 GMT",
            "ContentLength": 77,
            "VersionId": "null",
            "ETag": '"30a6ec7e1a9ad79c203d05a589c8b400"',
            "Metadata": {},
        }
    }
    mocked_requests = [
        MockedBoto3Request(method="head_bucket", response=head_bucket_response, expected_params=bucket)
    ] * num_calls
    boto3_stubber("s3", mocked_requests)
    mocker.patch("pcluster.config.validators.urllib.request.urlopen")


@pytest.mark.parametrize(
    "section_dict, expected_message",
    [
        ({"enable_intel_hpc_platform": "true", "base_os": "centos7"}, None),
        ({"enable_intel_hpc_platform": "true", "base_os": "centos8"}, None),
        ({"enable_intel_hpc_platform": "true", "base_os": "alinux"}, "it is required to set the 'base_os'"),
        ({"enable_intel_hpc_platform": "true", "base_os": "alinux2"}, "it is required to set the 'base_os'"),
        ({"enable_intel_hpc_platform": "true", "base_os": "ubuntu1604"}, "it is required to set the 'base_os'"),
        ({"enable_intel_hpc_platform": "true", "base_os": "ubuntu1804"}, "it is required to set the 'base_os'"),
        # intel hpc disabled, you can use any os
        ({"enable_intel_hpc_platform": "false", "base_os": "alinux"}, None),
    ],
)
def test_intel_hpc_os_validator(mocker, section_dict, expected_message):
    config_parser_dict = {"cluster default": section_dict}
    utils.assert_param_validator(mocker, config_parser_dict, expected_message)


@pytest.mark.parametrize(
    "section_dict, expected_error, expected_warning",
    [
        ({"enable_efa": "NONE"}, "invalid value", None),
        ({"enable_efa": "compute", "scheduler": "sge"}, "is required to set the 'compute_instance_type'", None),
        (
            {"enable_efa": "compute", "compute_instance_type": "t2.large", "scheduler": "sge"},
            None,
            "You may see better performance using a cluster placement group",
        ),
        (
            {
                "enable_efa": "compute",
                "compute_instance_type": "t2.large",
                "base_os": "alinux",
                "scheduler": "awsbatch",
            },
            "it is required to set the 'scheduler'",
            None,
        ),
        (
            {
                "enable_efa": "compute",
                "compute_instance_type": "t2.large",
                "base_os": "centos7",
                "scheduler": "sge",
                "placement_group": "DYNAMIC",
            },
            None,
            None,
        ),
        (
            {
                "enable_efa": "compute",
                "compute_instance_type": "t2.large",
                "base_os": "alinux2",
                "scheduler": "sge",
                "placement_group": "DYNAMIC",
            },
            None,
            None,
        ),
    ],
)
def test_efa_validator(boto3_stubber, mocker, capsys, section_dict, expected_error, expected_warning):
    if section_dict.get("enable_efa") != "NONE":
        mocked_requests = [
            MockedBoto3Request(
                method="describe_instance_types",
                response={"InstanceTypes": [{"InstanceType": "t2.large"}]},
                expected_params={"Filters": [{"Name": "network-info.efa-supported", "Values": ["true"]}]},
            )
        ]
        boto3_stubber("ec2", mocked_requests)
    config_parser_dict = {"cluster default": section_dict}
    utils.assert_param_validator(mocker, config_parser_dict, expected_error, capsys, expected_warning)


@pytest.mark.parametrize(
    "cluster_dict, expected_error",
    [
        # EFAGDR without EFA
        (
            {"enable_efa_gdr": "compute"},
            "The parameter 'enable_efa_gdr' can be used only in combination with 'enable_efa'",
        ),
        # EFAGDR with EFA
        ({"enable_efa": "compute", "enable_efa_gdr": "compute"}, None),
        # EFA withoud EFAGDR
        ({"enable_efa": "compute"}, None),
    ],
)
def test_efa_gdr_validator(cluster_dict, expected_error):
    config_parser_dict = {
        "cluster default": cluster_dict,
    }

    config_parser = configparser.ConfigParser()
    config_parser.read_dict(config_parser_dict)

    pcluster_config = utils.init_pcluster_config_from_configparser(config_parser, False, auto_refresh=False)
    enable_efa_gdr_value = pcluster_config.get_section("cluster").get_param_value("enable_efa_gdr")

    errors, warnings = efa_gdr_validator("enable_efa_gdr", enable_efa_gdr_value, pcluster_config)
    if expected_error:
        assert_that(errors[0]).matches(expected_error)
    else:
        assert_that(errors).is_empty()


@pytest.mark.parametrize(
    "ip_permissions, ip_permissions_egress, expected_message",
    [
        ([], [], "must allow all traffic in and out from itself"),
        (
            [{"IpProtocol": "-1", "UserIdGroupPairs": [{"UserId": "123456789012", "GroupId": "sg-12345678"}]}],
            [],
            "must allow all traffic in and out from itself",
        ),
        (
            [{"IpProtocol": "-1", "UserIdGroupPairs": [{"UserId": "123456789012", "GroupId": "sg-12345678"}]}],
            [{"IpProtocol": "-1", "UserIdGroupPairs": [{"UserId": "123456789012", "GroupId": "sg-12345678"}]}],
            None,
        ),
        (
            [
                {
                    "PrefixListIds": [],
                    "FromPort": 22,
                    "IpRanges": [{"CidrIp": "203.0.113.0/24"}],
                    "ToPort": 22,
                    "IpProtocol": "tcp",
                    "UserIdGroupPairs": [],
                }
            ],
            [],
            "must allow all traffic in and out from itself",
        ),
    ],
)
def test_efa_validator_with_vpc_security_group(
    boto3_stubber, mocker, ip_permissions, ip_permissions_egress, expected_message
):
    describe_security_groups_response = {
        "SecurityGroups": [
            {
                "IpPermissionsEgress": ip_permissions_egress,
                "Description": "My security group",
                "IpPermissions": ip_permissions,
                "GroupName": "MySecurityGroup",
                "OwnerId": "123456789012",
                "GroupId": "sg-12345678",
            }
        ]
    }
    mocked_requests = [
        MockedBoto3Request(
            method="describe_security_groups",
            response=describe_security_groups_response,
            expected_params={"GroupIds": ["sg-12345678"]},
        ),
        MockedBoto3Request(
            method="describe_instance_types",
            response={"InstanceTypes": [{"InstanceType": "t2.large"}]},
            expected_params={"Filters": [{"Name": "network-info.efa-supported", "Values": ["true"]}]},
        ),
        MockedBoto3Request(
            method="describe_security_groups",
            response=describe_security_groups_response,
            expected_params={"GroupIds": ["sg-12345678"]},
        ),  # it is called two times, for vpc_security_group_id validation and to validate efa
    ]

    boto3_stubber("ec2", mocked_requests)

    config_parser_dict = {
        "cluster default": {
            "enable_efa": "compute",
            "compute_instance_type": "t2.large",
            "placement_group": "DYNAMIC",
            "vpc_settings": "default",
            "scheduler": "sge",
        },
        "vpc default": {"vpc_security_group_id": "sg-12345678"},
    }
    utils.assert_param_validator(mocker, config_parser_dict, expected_message)


@pytest.mark.parametrize(
    "architecture, base_os, expected_message",
    [
        # Supported combinations
        ("x86_64", "alinux", None),
        ("x86_64", "alinux2", None),
        ("x86_64", "centos7", None),
        ("x86_64", "centos8", None),
        ("x86_64", "ubuntu1604", None),
        ("x86_64", "ubuntu1804", None),
        ("arm64", "ubuntu1804", None),
        ("arm64", "alinux2", None),
        ("arm64", "centos8", None),
        # Unsupported combinations
        (
            "UnsupportedArchitecture",
            "alinux2",
            FSX_MESSAGES["errors"]["unsupported_architecture"].format(
                supported_architectures=list(FSX_SUPPORTED_ARCHITECTURES_OSES.keys())
            ),
        ),
        (
            "arm64",
            "centos7",
            FSX_MESSAGES["errors"]["unsupported_os"].format(
                architecture="arm64", supported_oses=FSX_SUPPORTED_ARCHITECTURES_OSES.get("arm64")
            ),
        ),
        (
            "arm64",
            "alinux",
            FSX_MESSAGES["errors"]["unsupported_os"].format(
                architecture="arm64", supported_oses=FSX_SUPPORTED_ARCHITECTURES_OSES.get("arm64")
            ),
        ),
        (
            "arm64",
            "ubuntu1604",
            FSX_MESSAGES["errors"]["unsupported_os"].format(
                architecture="arm64", supported_oses=FSX_SUPPORTED_ARCHITECTURES_OSES.get("arm64")
            ),
        ),
    ],
)
def test_fsx_architecture_os_validator(mocker, architecture, base_os, expected_message):
    config_parser_dict = {
        "cluster default": {"base_os": base_os, "fsx_settings": "fsx"},
        "fsx fsx": {"storage_capacity": 3200},
    }
    expected_message = re.escape(expected_message) if expected_message else None
    extra_patches = {
        "pcluster.config.cfn_param_types.get_supported_architectures_for_instance_type": [architecture],
        "pcluster.utils.get_supported_architectures_for_instance_type": [architecture],
        "pcluster.utils.get_supported_os_for_architecture": [base_os],
    }
    utils.assert_param_validator(mocker, config_parser_dict, expected_message, extra_patches=extra_patches)


@pytest.mark.parametrize(
    "section_dict, expected_message",
    [
        (
            {"initial_queue_size": "0", "maintain_initial_size": True},
            "maintain_initial_size cannot be set to true if initial_queue_size is 0",
        ),
        (
            {"scheduler": "awsbatch", "maintain_initial_size": True},
            "maintain_initial_size is not supported when using awsbatch as scheduler",
        ),
    ],
)
def test_maintain_initial_size_validator(mocker, section_dict, expected_message):
    config_parser_dict = {"cluster default": section_dict}
    utils.assert_param_validator(mocker, config_parser_dict, expected_message)


@pytest.mark.parametrize(
    "cluster_section_dict, expected_message",
    [
        # SIT cluster, perfectly fine
        ({"scheduler": "slurm"}, None),
        # HIT cluster with one queue
        ({"scheduler": "slurm", "queue_settings": "queue1"}, None),
        ({"scheduler": "slurm", "queue_settings": "queue1,queue2,queue3,queue4,queue5"}, None),
        ({"scheduler": "slurm", "queue_settings": "queue1, queue2"}, None),
        (
            {"scheduler": "slurm", "queue_settings": "queue1,queue2,queue3,queue4,queue5,queue6"},
            "Invalid number of 'queue' sections specified. Max 5 expected.",
        ),
        (
            {"scheduler": "slurm", "queue_settings": "queue_1"},
            (
                "Invalid queue name 'queue_1'. Queue section names can be at most 30 chars long, must begin with"
                " a letter and only contain lowercase letters, digits and hyphens. It is forbidden to use"
                " 'default' as a queue section name."
            ),
        ),
        (
            {"scheduler": "slurm", "queue_settings": "default"},
            (
                "Invalid queue name 'default'. Queue section names can be at most 30 chars long, must begin with"
                " a letter and only contain lowercase letters, digits and hyphens. It is forbidden to use"
                " 'default' as a queue section name."
            ),
        ),
        (
            {"scheduler": "slurm", "queue_settings": "queue1, default"},
            (
                "Invalid queue name '.*'. Queue section names can be at most 30 chars long, must begin with"
                " a letter and only contain lowercase letters, digits and hyphens. It is forbidden to use"
                " 'default' as a queue section name."
            ),
        ),
        (
            {"scheduler": "slurm", "queue_settings": "QUEUE"},
            (
                "Invalid queue name 'QUEUE'. Queue section names can be at most 30 chars long, must begin with"
                " a letter and only contain lowercase letters, digits and hyphens. It is forbidden to use"
                " 'default' as a queue section name."
            ),
        ),
        (
            {"scheduler": "slurm", "queue_settings": "aQUEUEa"},
            (
                "Invalid queue name 'aQUEUEa'. Queue section names can be at most 30 chars long, must begin with"
                " a letter and only contain lowercase letters, digits and hyphens. It is forbidden to use"
                " 'default' as a queue section name."
            ),
        ),
        ({"scheduler": "slurm", "queue_settings": "my-default-queue"}, None),
    ],
)
def test_queue_settings_validator(mocker, cluster_section_dict, expected_message):
    config_parser_dict = {"cluster default": cluster_section_dict}
    if cluster_section_dict.get("queue_settings"):
        for i, queue_name in enumerate(cluster_section_dict["queue_settings"].split(",")):
            config_parser_dict["queue {0}".format(queue_name.strip())] = {
                "compute_resource_settings": "cr{0}".format(i),
                "disable_hyperthreading": True,
                "enable_efa": True,
            }
            config_parser_dict["compute_resource cr{0}".format(i)] = {"instance_type": "t2.micro"}

    utils.assert_param_validator(mocker, config_parser_dict, expected_message)


@pytest.mark.parametrize(
    "cluster_dict, queue_dict, expected_error_messages, expected_warning_messages",
    [
        (
            {"queue_settings": "default"},
            {"compute_resource_settings": "cr1,cr2", "enable_efa": True, "disable_hyperthreading": True},
            [
                "Duplicate instance type 't2.micro' found in queue 'default'. "
                "Compute resources in the same queue must use different instance types"
            ],
            [
                "EFA was enabled on queue 'default', but instance type 't2.micro' "
                "defined in compute resource settings cr1 does not support EFA.",
                "EFA was enabled on queue 'default', but instance type 't2.micro' "
                "defined in compute resource settings cr2 does not support EFA.",
            ],
        ),
        (
            {"queue_settings": "default"},
            {"compute_resource_settings": "cr3,cr4", "enable_efa": True, "disable_hyperthreading": True},
            [
                "Duplicate instance type 'c4.xlarge' found in queue 'default'. "
                "Compute resources in the same queue must use different instance types"
            ],
            [
                "EFA was enabled on queue 'default', but instance type 'c4.xlarge' "
                "defined in compute resource settings cr3 does not support EFA.",
                "EFA was enabled on queue 'default', but instance type 'c4.xlarge' "
                "defined in compute resource settings cr4 does not support EFA.",
            ],
        ),
        (
            {"queue_settings": "default"},
            {"compute_resource_settings": "cr1,cr3", "enable_efa": True, "disable_hyperthreading": True},
            None,
            [
                "EFA was enabled on queue 'default', but instance type 't2.micro' "
                "defined in compute resource settings cr1 does not support EFA.",
                "EFA was enabled on queue 'default', but instance type 'c4.xlarge' "
                "defined in compute resource settings cr3 does not support EFA.",
            ],
        ),
        (
            {"queue_settings": "default"},
            {"compute_resource_settings": "cr2,cr4", "enable_efa": True, "disable_hyperthreading": True},
            None,
            [
                "EFA was enabled on queue 'default', but instance type 't2.micro' "
                "defined in compute resource settings cr2 does not support EFA.",
                "EFA was enabled on queue 'default', but instance type 'c4.xlarge' "
                "defined in compute resource settings cr4 does not support EFA.",
            ],
        ),
        (
            {"queue_settings": "default"},
            {"compute_resource_settings": "cr2,cr4", "enable_efa": True, "enable_efa_gdr": True},
            None,
            [
                "EFA was enabled on queue 'default', but instance type 't2.micro' "
                "defined in compute resource settings cr2 does not support EFA.",
                "EFA GDR was enabled on queue 'default', but instance type 't2.micro' "
                "defined in compute resource settings cr2 does not support EFA GDR.",
                "EFA was enabled on queue 'default', but instance type 'c4.xlarge' "
                "defined in compute resource settings cr4 does not support EFA.",
                "EFA GDR was enabled on queue 'default', but instance type 'c4.xlarge' "
                "defined in compute resource settings cr4 does not support EFA GDR.",
            ],
        ),
        (
            {"queue_settings": "default"},
            {"compute_resource_settings": "efa_instance", "enable_efa_gdr": True},
            ["The parameter 'enable_efa_gdr' can be used only in combination with 'enable_efa'"],
            None,
        ),
        ({"queue_settings": "default"}, {"compute_resource_settings": "cr1"}, None, None),
        (
            {"queue_settings": "default", "enable_efa": "compute", "disable_hyperthreading": True},
            {"compute_resource_settings": "cr1", "enable_efa": True, "disable_hyperthreading": True},
            [
                "Parameter 'enable_efa' can be used only in 'cluster' or in 'queue' section",
                "Parameter 'disable_hyperthreading' can be used only in 'cluster' or in 'queue' section",
            ],
            [
                "EFA was enabled on queue 'default', but instance type 't2.micro' "
                "defined in compute resource settings cr1 does not support EFA."
            ],
        ),
        (
            {
                "queue_settings": "default",
                "enable_efa": "compute",
                "enable_efa_gdr": "compute",
                "disable_hyperthreading": True,
            },
            {
                "compute_resource_settings": "cr1",
                "enable_efa": False,
                "enable_efa_gdr": False,
                "disable_hyperthreading": False,
            },
            [
                "Parameter 'enable_efa' can be used only in 'cluster' or in 'queue' section",
                "Parameter 'enable_efa_gdr' can be used only in 'cluster' or in 'queue' section",
                "Parameter 'disable_hyperthreading' can be used only in 'cluster' or in 'queue' section",
            ],
            None,
        ),
        (
            {"queue_settings": "default"},
            {"compute_resource_settings": "efa_instance", "enable_efa": True},
            None,
            None,
        ),
    ],
)
def test_queue_validator(cluster_dict, queue_dict, expected_error_messages, expected_warning_messages):
    config_parser_dict = {
        "cluster default": cluster_dict,
        "queue default": queue_dict,
        "compute_resource cr1": {"instance_type": "t2.micro"},
        "compute_resource cr2": {"instance_type": "t2.micro"},
        "compute_resource cr3": {"instance_type": "c4.xlarge"},
        "compute_resource cr4": {"instance_type": "c4.xlarge"},
        "compute_resource efa_instance": {"instance_type": "p3dn.24xlarge"},
    }

    config_parser = configparser.ConfigParser()
    config_parser.read_dict(config_parser_dict)

    pcluster_config = utils.init_pcluster_config_from_configparser(config_parser, False, auto_refresh=False)

    efa_instance_compute_resource = pcluster_config.get_section("compute_resource", "efa_instance")
    if efa_instance_compute_resource:
        # Override `enable_efa` and `enable_efa_gdr` default value for instance with efa support
        efa_instance_compute_resource.get_param("enable_efa").value = True
        efa_instance_compute_resource.get_param("enable_efa_gdr").value = True

    errors, warnings = queue_validator("queue", "default", pcluster_config)

    if expected_error_messages:
        assert_that(expected_error_messages).is_equal_to(errors)
    else:
        assert_that(errors).is_empty()

    if expected_warning_messages:
        assert_that(expected_warning_messages).is_equal_to(warnings)
    else:
        assert_that(warnings).is_empty()


@pytest.mark.parametrize(
    "param_value, expected_message",
    [
        (
            "section1!2",
            "Invalid label 'section1!2' in param 'queue_settings'. "
            "Section labels can only contain alphanumeric characters, dashes or underscores.",
        ),
        (
            "section!123456789abcdefghijklmnopqrstuvwxyz_123456789abcdefghijklmnopqrstuvwxyz_",
            "Invalid label 'section!123456789...' in param 'queue_settings'. "
            "Section labels can only contain alphanumeric characters, dashes or underscores.",
        ),
        ("section-1", None),
        ("section_1", None),
        (
            "section_123456789abcdefghijklmnopqrstuvwxyz_123456789abcdefghijklmnopqrstuvwxyz_",
            "Invalid label 'section_123456789...' in param 'queue_settings'. "
            "The maximum length allowed for section labels is 64 characters",
        ),
    ],
)
def test_settings_validator(param_value, expected_message):
    errors, warnings = settings_validator("queue_settings", param_value, None)
    if expected_message:
        assert_that(errors and len(errors) == 1).is_true()
        assert_that(errors[0]).is_equal_to(expected_message)
    else:
        assert_that(errors).is_empty()


@pytest.mark.parametrize(
    "cluster_section_dict, sections_dict, expected_message",
    [
        (
            {"vpc_settings": "vpc1, vpc2"},
            {"vpc vpc1": {}, "vpc vpc2": {}},
            "The value of 'vpc_settings' parameter is invalid. It can only contain a single vpc section label",
        ),
        (
            {"efs_settings": "efs1, efs2"},
            {"efs efs1": {}, "efs efs2": {}},
            "The value of 'efs_settings' parameter is invalid. It can only contain a single efs section label",
        ),
    ],
)
def test_single_settings_validator(mocker, cluster_section_dict, sections_dict, expected_message):
    config_parser_dict = {"cluster default": cluster_section_dict}
    if sections_dict:
        for key, section in sections_dict.items():
            config_parser_dict[key] = section
    utils.assert_param_validator(mocker, config_parser_dict, expected_message)


#########
#
# architecture validator tests
#
# Two things make it difficult to test validators that key on architecture in the same way that:
# 1) architecture is a derived parameter and cannot be configured directly via the config file
# 2) many validators key on the architecture, which makes it impossible to test some combinations of
#    parameters for validators that run later than others, because those run earlier will have
#    already raised exceptions.
#
# Thus, the following code mocks the pcluster_config object passed to the validator functions
# and calls those functions directly (as opposed to patching functions and instantiating a config
# as would be done when running `pcluster create/update`).
#
#########


def get_default_pcluster_sections_dict():
    """Return a dict similar in structure to that of a cluster config file."""
    default_pcluster_sections_dict = {}
    for section_default_dict in DefaultDict:
        if section_default_dict.name == "pcluster":  # Get rid of the extra layer in this case
            default_pcluster_sections_dict["cluster"] = section_default_dict.value.get("cluster")
        else:
            default_pcluster_sections_dict[section_default_dict.name] = section_default_dict.value
    return default_pcluster_sections_dict


def make_pcluster_config_mock(mocker, config_dict):
    """Mock the calls that made on a pcluster_config by validator functions."""
    cluster_config_dict = get_default_pcluster_sections_dict()
    for section_key in config_dict:
        cluster_config_dict = utils.merge_dicts(cluster_config_dict.get(section_key), config_dict.get(section_key))

    section_to_mocks = {}
    for section_key, section_dict in config_dict.items():
        section_mock = mocker.MagicMock()
        section_mock.get_param_value.side_effect = lambda param: section_dict.get(param)
        section_to_mocks[section_key] = section_mock

    pcluster_config_mock = mocker.MagicMock()
    pcluster_config_mock.get_section.side_effect = lambda section: section_to_mocks.get(section)
    return pcluster_config_mock


# TODO to be moved
def run_architecture_validator_test(
    mocker,
    config,
    constrained_param_section,
    constrained_param_name,
    param_name,
    param_val,
    validator,
    expected_messages,
):
    """Run a test for a validator that's concerned with the architecture param."""
    mocked_pcluster_config = make_pcluster_config_mock(mocker, config)
    errors, warnings = validator(param_name, param_val, mocked_pcluster_config)

    mocked_pcluster_config.get_section.assert_called_once_with(constrained_param_section)
    mocked_pcluster_config.get_section.side_effect(constrained_param_section).get_param_value.assert_called_with(
        constrained_param_name
    )
    assert_that(len(warnings)).is_equal_to(0)
    assert_that(len(errors)).is_equal_to(len(expected_messages))
    for error, expected_message in zip(errors, expected_messages):
        assert_that(error).matches(re.escape(expected_message))


@pytest.mark.parametrize(
    "enabled, architecture, expected_message",
    [
        (True, "x86_64", []),
        (True, "arm64", ["instance types and an AMI that support these architectures"]),
        (False, "x86_64", []),
        (False, "arm64", []),
    ],
)
def test_intel_hpc_architecture_validator(mocker, enabled, architecture, expected_message):
    """Verify that setting enable_intel_hpc_platform is invalid when architecture != x86_64."""
    config_dict = {"cluster": {"enable_intel_hpc_platform": enabled, "architecture": architecture}}
    run_architecture_validator_test(
        mocker,
        config_dict,
        "cluster",
        "architecture",
        "enable_intel_hpc_platform",
        enabled,
        intel_hpc_architecture_validator,
        expected_message,
    )


@pytest.mark.parametrize(
    "section_dict, bucket, num_calls, expected_error",
    [
        (
            {
                "fsx_backup_id": "backup-0ff8da96d57f3b4e3",
                "deployment_type": "PERSISTENT_1",
                "per_unit_storage_throughput": 50,
            },
            None,
            0,
            "When restoring an FSx Lustre file system from backup, 'deployment_type' cannot be specified.",
        ),
        (
            {"fsx_backup_id": "backup-0ff8da96d57f3b4e3", "storage_capacity": 7200},
            None,
            0,
            "When restoring an FSx Lustre file system from backup, 'storage_capacity' cannot be specified.",
        ),
        (
            {
                "fsx_backup_id": "backup-0ff8da96d57f3b4e3",
                "deployment_type": "PERSISTENT_1",
                "per_unit_storage_throughput": 100,
            },
            None,
            0,
            "When restoring an FSx Lustre file system from backup, 'per_unit_storage_throughput' cannot be specified.",
        ),
        (
            {
                "fsx_backup_id": "backup-0ff8da96d57f3b4e3",
                "imported_file_chunk_size": 1024,
                "export_path": "s3://test",
                "import_path": "s3://test",
            },
            {"Bucket": "test"},
            2,
            "When restoring an FSx Lustre file system from backup, 'imported_file_chunk_size' cannot be specified.",
        ),
        (
            {
                "fsx_backup_id": "backup-0ff8da96d57f3b4e3",
                "fsx_kms_key_id": "somekey",
                "deployment_type": "PERSISTENT_1",
                "per_unit_storage_throughput": 50,
            },
            None,
            0,
            "When restoring an FSx Lustre file system from backup, 'fsx_kms_key_id' cannot be specified.",
        ),
        (
            {
                "fsx_backup_id": "backup-00000000000000000",
                "deployment_type": "PERSISTENT_1",
                "per_unit_storage_throughput": 50,
            },
            None,
            0,
            "Failed to retrieve backup with Id 'backup-00000000000000000'",
        ),
    ],
)
def test_fsx_lustre_backup_validator(mocker, boto3_stubber, section_dict, bucket, num_calls, expected_error):
    valid_key_id = "backup-0ff8da96d57f3b4e3"
    describe_backups_response = {
        "Backups": [
            {
                "BackupId": valid_key_id,
                "Lifecycle": "AVAILABLE",
                "Type": "USER_INITIATED",
                "CreationTime": 1594159673.559,
                "FileSystem": {
                    "StorageCapacity": 7200,
                    "StorageType": "SSD",
                    "LustreConfiguration": {"DeploymentType": "PERSISTENT_1", "PerUnitStorageThroughput": 200},
                },
            }
        ]
    }

    if bucket:
        _head_bucket_stubber(mocker, boto3_stubber, bucket, num_calls)
    generate_describe_backups_error = section_dict.get("fsx_backup_id") != valid_key_id
    fsx_mocked_requests = [
        MockedBoto3Request(
            method="describe_backups",
            response=expected_error if generate_describe_backups_error else describe_backups_response,
            expected_params={"BackupIds": [section_dict.get("fsx_backup_id")]},
            generate_error=generate_describe_backups_error,
        )
    ]
    boto3_stubber("fsx", fsx_mocked_requests)

    if "fsx_kms_key_id" in section_dict:
        describe_key_response = {"KeyMetadata": {"KeyId": section_dict.get("fsx_kms_key_id")}}
        kms_mocked_requests = [
            MockedBoto3Request(
                method="describe_key",
                response=describe_key_response,
                expected_params={"KeyId": section_dict.get("fsx_kms_key_id")},
            )
        ]
        boto3_stubber("kms", kms_mocked_requests)

    config_parser_dict = {"cluster default": {"fsx_settings": "default"}, "fsx default": section_dict}
    utils.assert_param_validator(mocker, config_parser_dict, expected_error=expected_error)


#########
#
# ignored FSx params validator test
#
# Testing a validator that requires the fsx_fs_id parameter to be specified requires a lot of
# boto3 stubbing due to the complexity contained in the fsx_id_validator.
#
# Thus, the following code mocks the pcluster_config object passed to the validator functions
# and calls the validator directly.
#
#########


def test_ebs_allowed_values_all_have_volume_size_bounds():
    """Ensure that all known EBS volume types are accounted for by the volume size validator."""
    allowed_values_all_have_volume_size_bounds = set(ALLOWED_VALUES["volume_types"]) <= set(
        EBS_VOLUME_TYPE_TO_VOLUME_SIZE_BOUNDS.keys()
    )
    assert_that(allowed_values_all_have_volume_size_bounds).is_true()
