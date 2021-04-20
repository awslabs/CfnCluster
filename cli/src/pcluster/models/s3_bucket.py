# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.
#
# This module contains all the classes representing the Resources objects.
# These objects are obtained from the configuration file through a conversion based on the Schema classes.
#
import hashlib
import json
import logging
import os
from enum import Enum

import yaml

from common.aws.aws_api import AWSApi
from common.boto3.common import AWSClientError
from pcluster.constants import PCLUSTER_S3_BUCKET_VERSION
from pcluster.utils import get_partition, get_region, zip_dir

LOGGER = logging.getLogger(__name__)


class S3FileFormat(Enum):
    """Define S3 file format."""

    YAML = "yaml"
    JSON = "json"
    TEXT = "text"


class S3FileType(Enum):
    """Define S3 file types."""

    CONFIGS = "configs"
    TEMPLATES = "templates"
    CUSTOM_RESOURCES = "custom_resources"


class S3Bucket:
    """Represent the s3 bucket configuration."""

    def __init__(
        self,
        service_name: str,
        stack_name: str,
        artifact_directory: str,
        cleanup_on_deletion: bool = True,
        name: str = None,
        is_custom_bucket: bool = False,
    ):
        super().__init__()
        self._service_name = service_name
        self._stack_name = stack_name
        self._cleanup_on_deletion = cleanup_on_deletion
        self._root_directory = "parallelcluster"
        self._bootstrapped_file_name = ".bootstrapped"
        self.artifact_directory = artifact_directory
        self._is_custom_bucket = is_custom_bucket
        self.__partition = None
        self.__region = None
        self.__account_id = None
        self.__name = name

    @property
    def name(self):
        """Return bucket name."""
        if self.__name is None:
            self.__name = self.get_bucket_name(self.account_id, self.region)
        return self.__name

    @property
    def partition(self):
        """Return partition."""
        if self.__partition is None:
            self.__partition = get_partition()
        return self.__partition

    @property
    def region(self):
        """Return bucket region."""
        if self.__region is None:
            self.__region = get_region()
        return self.__region

    @property
    def account_id(self):
        """Return account id."""
        if self.__account_id is None:
            self.__account_id = AWSApi.instance().sts.get_account_id()
        return self.__account_id

    # --------------------------------------- S3 bucket utils --------------------------------------- #

    @staticmethod
    def get_bucket_name(account_id, region):
        """
        Get ParallelCluster bucket name.

        :param account_id
        :param region
        :return ParallelCluster bucket name e.g. parallelcluster-b9033160b61390ef-v1-do-not-delete
        """
        return "-".join(
            [
                "parallelcluster",
                S3Bucket.generate_s3_bucket_hash_suffix(account_id, region),
                PCLUSTER_S3_BUCKET_VERSION,
                "do",
                "not",
                "delete",
            ]
        )

    @staticmethod
    def generate_s3_bucket_hash_suffix(account_id, region):
        """
        Generate 16 characters hash suffix for ParallelCluster s3 bucket.

        :param account_id
        :param region
        :return: 16 chars string e.g. 2238a84ac8a74529
        """
        return hashlib.sha256((account_id + region).encode()).hexdigest()[0:16]

    def check_bucket_exists(self):
        """Check bucket existence by bucket name."""
        AWSApi.instance().s3.head_bucket(bucket_name=self.name)

    def create_bucket(self):
        """Create a new S3 bucket."""
        AWSApi.instance().s3.create_bucket(bucket_name=self.name, region=self.region)

    def configure_s3_bucket(self):
        """Configure s3 bucket to satisfy pcluster setting."""
        AWSApi.instance().s3.put_bucket_versioning(bucket_name=self.name, configuration={"Status": "Enabled"})
        AWSApi.instance().s3.put_bucket_encryption(
            bucket_name=self.name,
            configuration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
        )
        deny_http_policy = (
            '{{"Id":"DenyHTTP","Version":"2012-10-17","Statement":[{{"Sid":"AllowSSLRequestsOnly","Action":"s3:*",'
            '"Effect":"Deny","Resource":["arn:{partition}:s3:::{bucket_name}","arn:{partition}:s3:::{bucket_name}/*"],'
            '"Condition":{{"Bool":{{"aws:SecureTransport":"false"}}}},"Principal":"*"}}]}}'
        ).format(bucket_name=self.name, partition=self.partition)
        AWSApi.instance().s3.put_bucket_policy(bucket_name=self.name, policy=deny_http_policy)

    # --------------------------------------- S3 objects utils --------------------------------------- #

    def get_object_key(self, object_type, object_name):
        """Get object key of an artifact."""
        return "/".join([self.artifact_directory, object_type, object_name])

    def delete_s3_artifacts(self):
        """Cleanup S3 bucket artifact directory."""
        LOGGER.debug(
            "Cleaning up S3 resources bucket_name=%s, service_name=%s, remove_artifact=%s",
            self.name,
            self._service_name,
            self._cleanup_on_deletion,
        )
        if self.artifact_directory and self._cleanup_on_deletion:
            try:
                LOGGER.info("Deleting artifacts under %s/%s", self.name, self.artifact_directory)
                AWSApi.instance().s3_resource.delete_object(bucket_name=self.name, prefix=f"{self.artifact_directory}/")
                AWSApi.instance().s3_resource.delete_object_versions(
                    bucket_name=self.name, prefix=f"{self.artifact_directory}/"
                )
            except AWSClientError as e:
                LOGGER.warning(
                    "Failed to delete S3 artifact under %s/%s with error %s. Please delete them manually.",
                    self.name,
                    self.artifact_directory,
                    str(e),
                )

    def upload_bootstrapped_file(self):
        """Upload bootstrapped file to identify bucket is configured successfully."""
        AWSApi.instance().s3.put_object(
            bucket_name=self.name,
            body="bucket is configured successfully.",
            key="/".join([self._root_directory, self._bootstrapped_file_name]),
        )

    def check_bucket_is_bootstrapped(self):
        """Check bucket is configured successfully or not by bootstrapped file."""
        AWSApi.instance().s3.head_object(
            bucket_name=self.name, object_name="/".join([self._root_directory, self._bootstrapped_file_name])
        )

    def upload_config(self, config, config_name, format=S3FileFormat.YAML):
        """Upload config file to S3 bucket."""
        return self._upload_file(
            file_type=S3FileType.CONFIGS.value, content=config, file_name=config_name, format=format
        )

    def upload_cfn_template(self, template_body, template_name, format=S3FileFormat.YAML):
        """Upload cloudformation template to S3 bucket."""
        return self._upload_file(
            file_type=S3FileType.TEMPLATES.value, content=template_body, file_name=template_name, format=format
        )

    def upload_resources(self, resource_dir, custom_artifacts_name):
        """
        Upload custom resources to S3 bucket.

        All dirs contained in resource dir will be uploaded as zip files to
        {bucket_name}/parallelcluster/clusters/{cluster_name}/{resource_dir}/artifacts.zip.
        or {bucket_name}/parallelcluster/imagebuilders/{image_name}/{resource_dir}/artifacts.zip.
        All files contained in root dir will be uploaded to
        {bucket_name}/parallelcluster/clusters/{cluster_name}/{resource_dir}/artifact.
        or {bucket_name}/parallelcluster/imagebuilders/{image_name}/{resource_dir}/artifacts
        :param resource_dir: resource directory containing the resources to upload.
        :param custom_artifacts_name: custom_artifacts_name for zipped dir
        """
        for res in os.listdir(resource_dir):
            path = os.path.join(resource_dir, res)
            if os.path.isdir(path):
                AWSApi.instance().s3.upload_fileobj(
                    file_obj=zip_dir(os.path.join(resource_dir, res)),
                    bucket_name=self.name,
                    key=self.get_object_key(S3FileType.CUSTOM_RESOURCES.value, custom_artifacts_name),
                )
            elif os.path.isfile(path):
                AWSApi.instance().s3.upload_file(
                    file_path=os.path.join(resource_dir, res),
                    bucket_name=self.name,
                    key=self.get_object_key(S3FileType.CUSTOM_RESOURCES.value, res),
                )

    def get_config(self, config_name, version_id=None, format=S3FileFormat.YAML):
        """Get config file from S3 bucket."""
        return self._get_file(
            file_type=S3FileType.CONFIGS.value, file_name=config_name, version_id=version_id, format=format
        )

    def get_config_url(self, config_name):
        """Get config file http url from S3 bucket."""
        return self._get_file_url(file_name=config_name, file_type=S3FileType.CONFIGS.value)

    def get_cfn_template(self, template_name, version_id=None, format=S3FileFormat.YAML):
        """Get cfn template from S3 bucket."""
        return self._get_file(
            file_type=S3FileType.TEMPLATES.value, file_name=template_name, version_id=version_id, format=format
        )

    def get_cfn_template_url(self, template_name):
        """Get cfn template http url from S3 bucket."""
        return self._get_file_url(file_type=S3FileType.TEMPLATES.value, file_name=template_name)

    def get_resource_url(self, resource_name):
        """Get custom resource http url from S3 bucket."""
        return self._get_file_url(file_type=S3FileType.CUSTOM_RESOURCES.value, file_name=resource_name)

    # --------------------------------------- S3 private functions --------------------------------------- #

    def _upload_file(self, content, file_name, file_type, format=S3FileFormat.YAML):
        """Upload file to S3 bucket."""
        if format == S3FileFormat.YAML:
            result = AWSApi.instance().s3.put_object(
                bucket_name=self.name,
                body=yaml.dump(content),
                key=self.get_object_key(file_type, file_name),
            )
        elif format == S3FileFormat.JSON:
            result = AWSApi.instance().s3.put_object(
                bucket_name=self.name,
                body=json.dumps(content),
                key=self.get_object_key(file_type, file_name),
            )
        else:
            result = AWSApi.instance().s3.put_object(
                bucket_name=self.name,
                body=content,
                key=self.get_object_key(file_type, file_name),
            )
        return result

    def _get_file(self, file_name, file_type, version_id=None, format=S3FileFormat.YAML):
        """Get file from S3 bucket."""
        result = AWSApi.instance().s3.get_object(
            bucket_name=self.name, key=self.get_object_key(file_type, file_name), version_id=version_id
        )

        file_content = result["Body"].read().decode("utf-8")

        if format == S3FileFormat.YAML:
            file = yaml.safe_load(file_content)
        elif format == S3FileFormat.JSON:
            file = json.loads(file_content)
        else:
            file = file_content
        return file

    def _get_file_url(self, file_name, file_type):
        """Get file url from S3 bucket."""
        url = "https://{bucket_name}.s3.{region}.amazonaws.com{partition_suffix}/{config_key}".format(
            bucket_name=self.name,
            region=self.region,
            partition_suffix=".cn" if self.region.startswith("cn") else "",
            config_key=self.get_object_key(file_type, file_name),
        )
        return url


class S3BucketFactory:
    """S3 bucket factory to return a bucket object with existence check and creation."""

    @classmethod
    def init_s3_bucket(cls, service_name: str, artifact_directory: str, stack_name: str, custom_s3_bucket: str):
        """Initialize the s3 bucket."""
        if custom_s3_bucket:
            bucket = cls._check_custom_bucket(service_name, custom_s3_bucket, artifact_directory, stack_name)
        else:
            bucket = cls._check_default_bucket(service_name, artifact_directory, stack_name)

        return bucket

    @classmethod
    def _check_custom_bucket(cls, service_name: str, custom_s3_bucket: str, artifact_directory: str, stack_name: str):
        bucket = S3Bucket(
            service_name=service_name,
            name=custom_s3_bucket,
            artifact_directory=artifact_directory,
            stack_name=stack_name,
            is_custom_bucket=True,
        )
        try:
            bucket.check_bucket_exists()
        except AWSClientError as e:
            raise AWSClientError(
                "check_bucket_exists", f"Unable to access config-specified S3 bucket {bucket.name}. Due to {str(e)}"
            )

        return bucket

    @classmethod
    def _check_default_bucket(cls, service_name: str, artifact_directory: str, stack_name: str):
        bucket = S3Bucket(service_name=service_name, artifact_directory=artifact_directory, stack_name=stack_name)
        try:
            bucket.check_bucket_exists()
        except AWSClientError as e:
            cls._create_bucket(bucket, e)

        try:
            bucket.check_bucket_is_bootstrapped()
        except AWSClientError as e:
            cls._configure_bucket(bucket, e)

        return bucket

    @classmethod
    def _create_bucket(cls, bucket: S3Bucket, e: AWSClientError):
        if e.error_code == "404":
            try:
                bucket.create_bucket()
            except AWSClientError as error:
                LOGGER.error("Unable to create S3 bucket %s.", bucket.name)
                raise error
        else:
            LOGGER.error("Unable to check S3 bucket %s existence.", bucket.name)
            raise e

    @classmethod
    def _configure_bucket(cls, bucket: S3Bucket, e: AWSClientError):
        if e.error_code == "404":
            try:
                bucket.configure_s3_bucket()
                bucket.upload_bootstrapped_file()
            except AWSClientError as error:
                LOGGER.error("Configure S3 bucket %s failed.", bucket.name)
                raise error
        else:
            LOGGER.error("Unable to check S3 bucket %s is configured properly.", bucket.name)
            raise e
