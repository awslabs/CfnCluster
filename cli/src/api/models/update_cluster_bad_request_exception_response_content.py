# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at http://aws.amazon.com/apache2.0/
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=R0801


from typing import List

from api import util
from api.models.base_model_ import Model
from api.models.change import Change
from api.models.config_validation_message import ConfigValidationMessage
from api.models.update_error import UpdateError


class UpdateClusterBadRequestExceptionResponseContent(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(
        self, configuration_validation_errors=None, message=None, update_validation_errors=None, change_set=None
    ):
        """UpdateClusterBadRequestExceptionResponseContent - a model defined in OpenAPI

        :param configuration_validation_errors: The configuration_validation_errors of this
        UpdateClusterBadRequestExceptionResponseContent.
        :type configuration_validation_errors: List[ConfigValidationMessage]
        :param message: The message of this UpdateClusterBadRequestExceptionResponseContent.
        :type message: str
        :param update_validation_errors: The update_validation_errors of this
        UpdateClusterBadRequestExceptionResponseContent.
        :type update_validation_errors: List[UpdateError]
        :param change_set: The change_set of this UpdateClusterBadRequestExceptionResponseContent.
        :type change_set: List[Change]
        """
        self.openapi_types = {
            "configuration_validation_errors": List[ConfigValidationMessage],
            "message": str,
            "update_validation_errors": List[UpdateError],
            "change_set": List[Change],
        }

        self.attribute_map = {
            "configuration_validation_errors": "configurationValidationErrors",
            "message": "message",
            "update_validation_errors": "updateValidationErrors",
            "change_set": "changeSet",
        }

        self._configuration_validation_errors = configuration_validation_errors
        self._message = message
        self._update_validation_errors = update_validation_errors
        self._change_set = change_set

    @classmethod
    def from_dict(cls, dikt) -> "UpdateClusterBadRequestExceptionResponseContent":
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The UpdateClusterBadRequestExceptionResponseContent of this
        UpdateClusterBadRequestExceptionResponseContent.
        :rtype: UpdateClusterBadRequestExceptionResponseContent
        """
        return util.deserialize_model(dikt, cls)

    @property
    def configuration_validation_errors(self):
        """Gets the configuration_validation_errors of this UpdateClusterBadRequestExceptionResponseContent.


        :return: The configuration_validation_errors of this UpdateClusterBadRequestExceptionResponseContent.
        :rtype: List[ConfigValidationMessage]
        """
        return self._configuration_validation_errors

    @configuration_validation_errors.setter
    def configuration_validation_errors(self, configuration_validation_errors):
        """Sets the configuration_validation_errors of this UpdateClusterBadRequestExceptionResponseContent.


        :param configuration_validation_errors: The configuration_validation_errors of this
        UpdateClusterBadRequestExceptionResponseContent.
        :type configuration_validation_errors: List[ConfigValidationMessage]
        """

        self._configuration_validation_errors = configuration_validation_errors

    @property
    def message(self):
        """Gets the message of this UpdateClusterBadRequestExceptionResponseContent.


        :return: The message of this UpdateClusterBadRequestExceptionResponseContent.
        :rtype: str
        """
        return self._message

    @message.setter
    def message(self, message):
        """Sets the message of this UpdateClusterBadRequestExceptionResponseContent.


        :param message: The message of this UpdateClusterBadRequestExceptionResponseContent.
        :type message: str
        """

        self._message = message

    @property
    def update_validation_errors(self):
        """Gets the update_validation_errors of this UpdateClusterBadRequestExceptionResponseContent.


        :return: The update_validation_errors of this UpdateClusterBadRequestExceptionResponseContent.
        :rtype: List[UpdateError]
        """
        return self._update_validation_errors

    @update_validation_errors.setter
    def update_validation_errors(self, update_validation_errors):
        """Sets the update_validation_errors of this UpdateClusterBadRequestExceptionResponseContent.


        :param update_validation_errors: The update_validation_errors of this
        UpdateClusterBadRequestExceptionResponseContent.
        :type update_validation_errors: List[UpdateError]
        """

        self._update_validation_errors = update_validation_errors

    @property
    def change_set(self):
        """Gets the change_set of this UpdateClusterBadRequestExceptionResponseContent.


        :return: The change_set of this UpdateClusterBadRequestExceptionResponseContent.
        :rtype: List[Change]
        """
        return self._change_set

    @change_set.setter
    def change_set(self, change_set):
        """Sets the change_set of this UpdateClusterBadRequestExceptionResponseContent.


        :param change_set: The change_set of this UpdateClusterBadRequestExceptionResponseContent.
        :type change_set: List[Change]
        """

        self._change_set = change_set
