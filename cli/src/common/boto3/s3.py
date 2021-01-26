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

from common.boto3.common import AWSExceptionHandler, Boto3Client

# TODO move s3_factory.py and awsbatch/utils.py here


class S3Client(Boto3Client):
    """S3 Boto3 client."""

    def __init__(self):
        super().__init__("s3")

    @AWSExceptionHandler.handle_client_exception
    def download_file(self, bucket_name, object_name, file_name):
        """Download generic file from S3."""
        self._client.download_file(bucket_name, object_name, file_name)

    @AWSExceptionHandler.handle_client_exception
    def head_object(self, bucket_name, object_name):
        """Retrieve metadata from an object without returning the object itself."""
        return self._client.head_object(Bucket=bucket_name, Key=object_name)
