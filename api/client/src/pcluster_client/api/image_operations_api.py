"""
    ParallelCluster

    ParallelCluster API  # noqa: E501

    The version of the OpenAPI document: 3.2.0
    Generated by: https://openapi-generator.tech
"""


import re  # noqa: F401
import sys  # noqa: F401

from pcluster_client.api_client import ApiClient, Endpoint as _Endpoint
from pcluster_client.model_utils import (  # noqa: F401
    check_allowed_values,
    check_validations,
    date,
    datetime,
    file_type,
    none_type,
    validate_and_convert_types
)
from pcluster_client.model.bad_request_exception_response_content import BadRequestExceptionResponseContent
from pcluster_client.model.build_image_bad_request_exception_response_content import BuildImageBadRequestExceptionResponseContent
from pcluster_client.model.build_image_request_content import BuildImageRequestContent
from pcluster_client.model.build_image_response_content import BuildImageResponseContent
from pcluster_client.model.conflict_exception_response_content import ConflictExceptionResponseContent
from pcluster_client.model.delete_image_response_content import DeleteImageResponseContent
from pcluster_client.model.describe_image_response_content import DescribeImageResponseContent
from pcluster_client.model.dryrun_operation_exception_response_content import DryrunOperationExceptionResponseContent
from pcluster_client.model.image_status_filtering_option import ImageStatusFilteringOption
from pcluster_client.model.internal_service_exception_response_content import InternalServiceExceptionResponseContent
from pcluster_client.model.limit_exceeded_exception_response_content import LimitExceededExceptionResponseContent
from pcluster_client.model.list_images_response_content import ListImagesResponseContent
from pcluster_client.model.list_official_images_response_content import ListOfficialImagesResponseContent
from pcluster_client.model.not_found_exception_response_content import NotFoundExceptionResponseContent
from pcluster_client.model.unauthorized_client_error_response_content import UnauthorizedClientErrorResponseContent
from pcluster_client.model.validation_level import ValidationLevel


class ImageOperationsApi(object):
    """NOTE: This class is auto generated by OpenAPI Generator
    Ref: https://openapi-generator.tech

    Do not edit the class manually.
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client
        self.build_image_endpoint = _Endpoint(
            settings={
                'response_type': (BuildImageResponseContent,),
                'auth': [
                    'aws.auth.sigv4'
                ],
                'endpoint_path': '/v3/images/custom',
                'operation_id': 'build_image',
                'http_method': 'POST',
                'servers': None,
            },
            params_map={
                'all': [
                    'build_image_request_content',
                    'suppress_validators',
                    'validation_failure_level',
                    'dryrun',
                    'rollback_on_failure',
                    'region',
                ],
                'required': [
                    'build_image_request_content',
                ],
                'nullable': [
                ],
                'enum': [
                ],
                'validation': [
                    'suppress_validators',
                ]
            },
            root_map={
                'validations': {
                    ('suppress_validators',): {

                    },
                },
                'allowed_values': {
                },
                'openapi_types': {
                    'build_image_request_content':
                        (BuildImageRequestContent,),
                    'suppress_validators':
                        ([str],),
                    'validation_failure_level':
                        (ValidationLevel,),
                    'dryrun':
                        (bool,),
                    'rollback_on_failure':
                        (bool,),
                    'region':
                        (str,),
                },
                'attribute_map': {
                    'suppress_validators': 'suppressValidators',
                    'validation_failure_level': 'validationFailureLevel',
                    'dryrun': 'dryrun',
                    'rollback_on_failure': 'rollbackOnFailure',
                    'region': 'region',
                },
                'location_map': {
                    'build_image_request_content': 'body',
                    'suppress_validators': 'query',
                    'validation_failure_level': 'query',
                    'dryrun': 'query',
                    'rollback_on_failure': 'query',
                    'region': 'query',
                },
                'collection_format_map': {
                    'suppress_validators': 'multi',
                }
            },
            headers_map={
                'accept': [
                    'application/json'
                ],
                'content_type': [
                    'application/json'
                ]
            },
            api_client=api_client
        )
        self.delete_image_endpoint = _Endpoint(
            settings={
                'response_type': (DeleteImageResponseContent,),
                'auth': [
                    'aws.auth.sigv4'
                ],
                'endpoint_path': '/v3/images/custom/{imageId}',
                'operation_id': 'delete_image',
                'http_method': 'DELETE',
                'servers': None,
            },
            params_map={
                'all': [
                    'image_id',
                    'region',
                    'force',
                ],
                'required': [
                    'image_id',
                ],
                'nullable': [
                ],
                'enum': [
                ],
                'validation': [
                    'image_id',
                ]
            },
            root_map={
                'validations': {
                    ('image_id',): {

                        'regex': {
                            'pattern': r'^[a-zA-Z][a-zA-Z0-9-]+$',  # noqa: E501
                        },
                    },
                },
                'allowed_values': {
                },
                'openapi_types': {
                    'image_id':
                        (str,),
                    'region':
                        (str,),
                    'force':
                        (bool,),
                },
                'attribute_map': {
                    'image_id': 'imageId',
                    'region': 'region',
                    'force': 'force',
                },
                'location_map': {
                    'image_id': 'path',
                    'region': 'query',
                    'force': 'query',
                },
                'collection_format_map': {
                }
            },
            headers_map={
                'accept': [
                    'application/json'
                ],
                'content_type': [],
            },
            api_client=api_client
        )
        self.describe_image_endpoint = _Endpoint(
            settings={
                'response_type': (DescribeImageResponseContent,),
                'auth': [
                    'aws.auth.sigv4'
                ],
                'endpoint_path': '/v3/images/custom/{imageId}',
                'operation_id': 'describe_image',
                'http_method': 'GET',
                'servers': None,
            },
            params_map={
                'all': [
                    'image_id',
                    'region',
                ],
                'required': [
                    'image_id',
                ],
                'nullable': [
                ],
                'enum': [
                ],
                'validation': [
                    'image_id',
                ]
            },
            root_map={
                'validations': {
                    ('image_id',): {

                        'regex': {
                            'pattern': r'^[a-zA-Z][a-zA-Z0-9-]+$',  # noqa: E501
                        },
                    },
                },
                'allowed_values': {
                },
                'openapi_types': {
                    'image_id':
                        (str,),
                    'region':
                        (str,),
                },
                'attribute_map': {
                    'image_id': 'imageId',
                    'region': 'region',
                },
                'location_map': {
                    'image_id': 'path',
                    'region': 'query',
                },
                'collection_format_map': {
                }
            },
            headers_map={
                'accept': [
                    'application/json'
                ],
                'content_type': [],
            },
            api_client=api_client
        )
        self.list_images_endpoint = _Endpoint(
            settings={
                'response_type': (ListImagesResponseContent,),
                'auth': [
                    'aws.auth.sigv4'
                ],
                'endpoint_path': '/v3/images/custom',
                'operation_id': 'list_images',
                'http_method': 'GET',
                'servers': None,
            },
            params_map={
                'all': [
                    'image_status',
                    'region',
                    'next_token',
                ],
                'required': [
                    'image_status',
                ],
                'nullable': [
                ],
                'enum': [
                ],
                'validation': [
                ]
            },
            root_map={
                'validations': {
                },
                'allowed_values': {
                },
                'openapi_types': {
                    'image_status':
                        (ImageStatusFilteringOption,),
                    'region':
                        (str,),
                    'next_token':
                        (str,),
                },
                'attribute_map': {
                    'image_status': 'imageStatus',
                    'region': 'region',
                    'next_token': 'nextToken',
                },
                'location_map': {
                    'image_status': 'query',
                    'region': 'query',
                    'next_token': 'query',
                },
                'collection_format_map': {
                }
            },
            headers_map={
                'accept': [
                    'application/json'
                ],
                'content_type': [],
            },
            api_client=api_client
        )
        self.list_official_images_endpoint = _Endpoint(
            settings={
                'response_type': (ListOfficialImagesResponseContent,),
                'auth': [
                    'aws.auth.sigv4'
                ],
                'endpoint_path': '/v3/images/official',
                'operation_id': 'list_official_images',
                'http_method': 'GET',
                'servers': None,
            },
            params_map={
                'all': [
                    'region',
                    'os',
                    'architecture',
                ],
                'required': [],
                'nullable': [
                ],
                'enum': [
                ],
                'validation': [
                ]
            },
            root_map={
                'validations': {
                },
                'allowed_values': {
                },
                'openapi_types': {
                    'region':
                        (str,),
                    'os':
                        (str,),
                    'architecture':
                        (str,),
                },
                'attribute_map': {
                    'region': 'region',
                    'os': 'os',
                    'architecture': 'architecture',
                },
                'location_map': {
                    'region': 'query',
                    'os': 'query',
                    'architecture': 'query',
                },
                'collection_format_map': {
                }
            },
            headers_map={
                'accept': [
                    'application/json'
                ],
                'content_type': [],
            },
            api_client=api_client
        )

    def build_image(
        self,
        build_image_request_content,
        **kwargs
    ):
        """build_image  # noqa: E501

        Create a custom ParallelCluster image in a given region.  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.build_image(build_image_request_content, async_req=True)
        >>> result = thread.get()

        Args:
            build_image_request_content (BuildImageRequestContent):

        Keyword Args:
            suppress_validators ([str]): Identifies one or more config validators to suppress. Format: (ALL|type:[A-Za-z0-9]+). [optional]
            validation_failure_level (ValidationLevel): Min validation level that will cause the creation to fail. (Defaults to 'ERROR'.). [optional]
            dryrun (bool): Only perform request validation without creating any resource. It can be used to validate the image configuration. (Defaults to 'false'.). [optional]
            rollback_on_failure (bool): When set, will automatically initiate an image stack rollback on failure. (Defaults to 'false'.). [optional]
            region (str): AWS Region that the operation corresponds to.. [optional]
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            _request_auths (list): set to override the auth_settings for an a single
                request; this effectively ignores the authentication
                in the spec for a single request.
                Default is None
            async_req (bool): execute request asynchronously

        Returns:
            BuildImageResponseContent
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs['async_req'] = kwargs.get(
            'async_req', False
        )
        kwargs['_return_http_data_only'] = kwargs.get(
            '_return_http_data_only', True
        )
        kwargs['_preload_content'] = kwargs.get(
            '_preload_content', True
        )
        kwargs['_request_timeout'] = kwargs.get(
            '_request_timeout', None
        )
        kwargs['_check_input_type'] = kwargs.get(
            '_check_input_type', True
        )
        kwargs['_check_return_type'] = kwargs.get(
            '_check_return_type', True
        )
        kwargs['_spec_property_naming'] = kwargs.get(
            '_spec_property_naming', False
        )
        kwargs['_content_type'] = kwargs.get(
            '_content_type')
        kwargs['_host_index'] = kwargs.get('_host_index')
        kwargs['_request_auths'] = kwargs.get('_request_auths', None)
        kwargs['build_image_request_content'] = \
            build_image_request_content
        return self.build_image_endpoint.call_with_http_info(**kwargs)

    def delete_image(
        self,
        image_id,
        **kwargs
    ):
        """delete_image  # noqa: E501

        Initiate the deletion of the custom ParallelCluster image.  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.delete_image(image_id, async_req=True)
        >>> result = thread.get()

        Args:
            image_id (str): Id of the image.

        Keyword Args:
            region (str): AWS Region that the operation corresponds to.. [optional]
            force (bool): Force deletion in case there are instances using the AMI or in case the AMI is shared. (Defaults to 'false'.). [optional]
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            _request_auths (list): set to override the auth_settings for an a single
                request; this effectively ignores the authentication
                in the spec for a single request.
                Default is None
            async_req (bool): execute request asynchronously

        Returns:
            DeleteImageResponseContent
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs['async_req'] = kwargs.get(
            'async_req', False
        )
        kwargs['_return_http_data_only'] = kwargs.get(
            '_return_http_data_only', True
        )
        kwargs['_preload_content'] = kwargs.get(
            '_preload_content', True
        )
        kwargs['_request_timeout'] = kwargs.get(
            '_request_timeout', None
        )
        kwargs['_check_input_type'] = kwargs.get(
            '_check_input_type', True
        )
        kwargs['_check_return_type'] = kwargs.get(
            '_check_return_type', True
        )
        kwargs['_spec_property_naming'] = kwargs.get(
            '_spec_property_naming', False
        )
        kwargs['_content_type'] = kwargs.get(
            '_content_type')
        kwargs['_host_index'] = kwargs.get('_host_index')
        kwargs['_request_auths'] = kwargs.get('_request_auths', None)
        kwargs['image_id'] = \
            image_id
        return self.delete_image_endpoint.call_with_http_info(**kwargs)

    def describe_image(
        self,
        image_id,
        **kwargs
    ):
        """describe_image  # noqa: E501

        Get detailed information about an existing image.  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.describe_image(image_id, async_req=True)
        >>> result = thread.get()

        Args:
            image_id (str): Id of the image.

        Keyword Args:
            region (str): AWS Region that the operation corresponds to.. [optional]
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            _request_auths (list): set to override the auth_settings for an a single
                request; this effectively ignores the authentication
                in the spec for a single request.
                Default is None
            async_req (bool): execute request asynchronously

        Returns:
            DescribeImageResponseContent
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs['async_req'] = kwargs.get(
            'async_req', False
        )
        kwargs['_return_http_data_only'] = kwargs.get(
            '_return_http_data_only', True
        )
        kwargs['_preload_content'] = kwargs.get(
            '_preload_content', True
        )
        kwargs['_request_timeout'] = kwargs.get(
            '_request_timeout', None
        )
        kwargs['_check_input_type'] = kwargs.get(
            '_check_input_type', True
        )
        kwargs['_check_return_type'] = kwargs.get(
            '_check_return_type', True
        )
        kwargs['_spec_property_naming'] = kwargs.get(
            '_spec_property_naming', False
        )
        kwargs['_content_type'] = kwargs.get(
            '_content_type')
        kwargs['_host_index'] = kwargs.get('_host_index')
        kwargs['_request_auths'] = kwargs.get('_request_auths', None)
        kwargs['image_id'] = \
            image_id
        return self.describe_image_endpoint.call_with_http_info(**kwargs)

    def list_images(
        self,
        image_status,
        **kwargs
    ):
        """list_images  # noqa: E501

        Retrieve the list of existing custom images.  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.list_images(image_status, async_req=True)
        >>> result = thread.get()

        Args:
            image_status (ImageStatusFilteringOption): Filter images by the status provided.

        Keyword Args:
            region (str): List images built in a given AWS Region.. [optional]
            next_token (str): Token to use for paginated requests.. [optional]
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            _request_auths (list): set to override the auth_settings for an a single
                request; this effectively ignores the authentication
                in the spec for a single request.
                Default is None
            async_req (bool): execute request asynchronously

        Returns:
            ListImagesResponseContent
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs['async_req'] = kwargs.get(
            'async_req', False
        )
        kwargs['_return_http_data_only'] = kwargs.get(
            '_return_http_data_only', True
        )
        kwargs['_preload_content'] = kwargs.get(
            '_preload_content', True
        )
        kwargs['_request_timeout'] = kwargs.get(
            '_request_timeout', None
        )
        kwargs['_check_input_type'] = kwargs.get(
            '_check_input_type', True
        )
        kwargs['_check_return_type'] = kwargs.get(
            '_check_return_type', True
        )
        kwargs['_spec_property_naming'] = kwargs.get(
            '_spec_property_naming', False
        )
        kwargs['_content_type'] = kwargs.get(
            '_content_type')
        kwargs['_host_index'] = kwargs.get('_host_index')
        kwargs['_request_auths'] = kwargs.get('_request_auths', None)
        kwargs['image_status'] = \
            image_status
        return self.list_images_endpoint.call_with_http_info(**kwargs)

    def list_official_images(
        self,
        **kwargs
    ):
        """list_official_images  # noqa: E501

        List Official ParallelCluster AMIs.  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.list_official_images(async_req=True)
        >>> result = thread.get()


        Keyword Args:
            region (str): AWS Region that the operation corresponds to.. [optional]
            os (str): Filter by OS distribution (Default is to not filter.). [optional]
            architecture (str): Filter by architecture (Default is to not filter.). [optional]
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            _request_auths (list): set to override the auth_settings for an a single
                request; this effectively ignores the authentication
                in the spec for a single request.
                Default is None
            async_req (bool): execute request asynchronously

        Returns:
            ListOfficialImagesResponseContent
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs['async_req'] = kwargs.get(
            'async_req', False
        )
        kwargs['_return_http_data_only'] = kwargs.get(
            '_return_http_data_only', True
        )
        kwargs['_preload_content'] = kwargs.get(
            '_preload_content', True
        )
        kwargs['_request_timeout'] = kwargs.get(
            '_request_timeout', None
        )
        kwargs['_check_input_type'] = kwargs.get(
            '_check_input_type', True
        )
        kwargs['_check_return_type'] = kwargs.get(
            '_check_return_type', True
        )
        kwargs['_spec_property_naming'] = kwargs.get(
            '_spec_property_naming', False
        )
        kwargs['_content_type'] = kwargs.get(
            '_content_type')
        kwargs['_host_index'] = kwargs.get('_host_index')
        kwargs['_request_auths'] = kwargs.get('_request_auths', None)
        return self.list_official_images_endpoint.call_with_http_info(**kwargs)

