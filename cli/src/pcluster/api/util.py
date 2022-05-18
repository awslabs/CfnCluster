# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at http://aws.amazon.com/apache2.0/
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.

# Generated by OpenAPI Generator (python-flask)

import datetime
import logging
import shutil
import subprocess

import six
from pkg_resources import packaging

from pcluster.api import typing_utils
from pcluster.constants import NODEJS_INCOMPATIBLE_VERSION_RANGE, NODEJS_MIN_VERSION

LOGGER = logging.getLogger(__name__)


def _deserialize(data, klass):
    """Deserializes dict, list, str into an object.

    :param data: dict, list or str.
    :param klass: class literal, or string of class name.

    :return: object.
    """
    if data is None:
        return None

    if klass in six.integer_types or klass in (float, str, bool, bytearray):
        return _deserialize_primitive(data, klass)
    if klass == object:
        return _deserialize_object(data)
    if klass == datetime.date:
        return deserialize_date(data)
    if klass == datetime.datetime:
        return deserialize_datetime(data)
    if typing_utils.is_generic(klass):
        if typing_utils.is_list(klass):
            return _deserialize_list(data, klass.__args__[0])
        if typing_utils.is_dict(klass):
            return _deserialize_dict(data, klass.__args__[1])

    return deserialize_model(data, klass)


def _deserialize_primitive(data, klass):
    """Deserializes to primitive type.

    :param data: data to deserialize.
    :param klass: class literal.

    :return: int, long, float, str, bool.
    :rtype: int | long | float | str | bool
    """
    try:
        value = klass(data)
    except UnicodeEncodeError:
        value = six.u(data)
    except TypeError:
        value = data
    return value


def _deserialize_object(value):
    """Return an original value.

    :return: object.
    """
    return value


def deserialize_date(string):
    """Deserializes string to date.

    :param string: str.
    :type string: str
    :return: date.
    :rtype: date
    """
    try:
        from dateutil.parser import parse  # pylint: disable=C0415

        return parse(string).date()
    except ImportError:
        return string


def deserialize_datetime(string):
    """Deserializes string to datetime.

    The string should be in iso8601 datetime format.

    :param string: str.
    :type string: str
    :return: datetime.
    :rtype: datetime
    """
    try:
        from dateutil.parser import parse  # pylint: disable=C0415

        return parse(string)
    except ImportError:
        return string


def deserialize_model(data, klass):
    """Deserializes list or dict to model.

    :param data: dict, list.
    :type data: dict | list
    :param klass: class literal.
    :return: model object.
    """
    instance = klass()

    if not instance.openapi_types:
        return data

    for attr, attr_type in six.iteritems(instance.openapi_types):
        if data is not None and instance.attribute_map[attr] in data and isinstance(data, (list, dict)):
            value = data[instance.attribute_map[attr]]
            setattr(instance, attr, _deserialize(value, attr_type))

    return instance


def _deserialize_list(data, boxed_type):
    """Deserializes a list and its elements.

    :param data: list to deserialize.
    :type data: list
    :param boxed_type: class literal.

    :return: deserialized list.
    :rtype: list
    """
    return [_deserialize(sub_data, boxed_type) for sub_data in data]


def _deserialize_dict(data, boxed_type):
    """Deserializes a dict and its elements.

    :param data: dict to deserialize.
    :type data: dict
    :param boxed_type: class literal.

    :return: deserialized dict.
    :rtype: dict
    """
    return {k: _deserialize(v, boxed_type) for k, v in six.iteritems(data)}


def assert_valid_node_js():
    _assert_node_executable()
    _assert_node_version()


def _assert_node_executable():
    node_exe = shutil.which("node")
    LOGGER.debug("Found Node.js executable in %s", node_exe)
    if not node_exe:
        message = (
            "Unable to find node executable. Node.js is required by the AWS CDK library used by ParallelCluster, "
            "see installation instructions here: https://docs.aws.amazon.com/parallelcluster/latest/ug/install-v3.html"
        )
        LOGGER.critical(message)
        raise Exception(message)


def _assert_node_version():
    try:
        # A nosec comment is appended to the following line in order to disable the B607 and B603 checks.
        # [B607:start_process_with_partial_path] Is suppressed because location of executable is retrieved from env PATH
        # [B603:subprocess_without_shell_equals_true] Is suppressed because input of check_output is not coming from
        #   untrusted source
        node_version = subprocess.check_output(  # nosec
            ["node", "--version"], stderr=subprocess.STDOUT, shell=False, encoding="utf-8"
        )
        LOGGER.debug("Found Node.js version (%s)", node_version)
    except Exception:
        message = "Unable to check Node.js version"
        LOGGER.critical(message)
        raise Exception(message)

    if packaging.version.parse(node_version) < packaging.version.parse(NODEJS_MIN_VERSION):
        message = (
            f"AWS CDK library used by ParallelCluster requires Node.js version >= {NODEJS_MIN_VERSION},"
            " see installation instructions here: https://docs.aws.amazon.com/parallelcluster/latest/ug/install-v3.html"
        )
        LOGGER.critical(message)
        raise Exception(message)
    if (
        packaging.version.parse(NODEJS_INCOMPATIBLE_VERSION_RANGE[0])
        <= packaging.version.parse(node_version)
        <= packaging.version.parse(NODEJS_INCOMPATIBLE_VERSION_RANGE[1])
    ):
        message = (
            f"AWS CDK library used by ParallelCluster requires Node.js to not be in the range"
            f" {NODEJS_INCOMPATIBLE_VERSION_RANGE}, but installed Node.js version {node_version} is within this range,"
            f" see https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html"
        )
        LOGGER.critical(message)
        raise Exception(message)
