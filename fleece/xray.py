"""This module bridges the gap of missing Python support in the AWS X-Ray
Lambda integration.

After enabling active tracing under Advanced settings on the Configuration tab
of your Lambda function in the AWS Console (or using the
`update_function_configuration` API call), you can mark any function or method
for tracing by using the `@trace_xray_subsegment` decorator.

This module also provides wrappers for boto and requests so that any AWS API
call, or HTTP request will be automatically traced by X-Ray, but you have to
explicitly allow this behavior by calling `monkey_patch_botocore_for_xray`
and/or `monkey_patch_requests_for_xray`. The best place to do this would be the
main handler module where the Lambda entry point is defined.
"""
from collections import namedtuple
import json
import os
import socket
import threading
import time
import uuid

from botocore.exceptions import ClientError
import wrapt

from fleece import log

LOGGER = log.get_logger('fleece.xray')

XRAY_DAEMON_HEADER = {'format': 'json', 'version': 1}

XRayDaemon = namedtuple('XRayDaemon', ['ip_address', 'port'])
XRayTraceID = namedtuple('XRayTraceID', ['trace_id', 'parent_id', 'sampled'])

ERROR_HANDLING_GENERIC = 'generic'
ERROR_HANDLING_BOTOCORE = 'botocore'

# Thread-local storage for parent IDs
threadlocal = threading.local()


class XRayDaemonNotFoundError(Exception):
    pass


class StringJSONEncoder(json.JSONEncoder):
    """Simple encoder that allows us to serialize everything into JSON."""

    def default(self, o):
        try:
            return super(StringJSONEncoder, self).default(o)
        except TypeError:
            return str(o)


def generate_subsegment_id():
    """Generate a random ID according to the X-Ray specs."""
    return uuid.uuid4().hex[:16]


def get_trace_id():
    """Parse X-Ray Trace ID environment variable.

    The value looks something like this:

        Root=1-5901e3bc-8da3814a5f3ccbc864b66ecc;Parent=328f72132deac0ce;Sampled=1

    `Root` is the main X-Ray Trace ID, `Parent` points to the top-level
    segment, and `Sampled` shows whether the current request should be traced
    or not.

    If the environment variable doesn't exist, just return an `XRayTraceID`
    instance with default values, which means that tracing will be skipped
    due to `sampled` being set to `False`.
    """
    raw_trace_id = os.environ.get('_X_AMZN_TRACE_ID', '')
    trace_id_parts = raw_trace_id.split(';')
    trace_kwargs = {
        'trace_id': None,
        'parent_id': None,
        'sampled': False,
    }
    if trace_id_parts[0] != '':
        # This means the trace ID environment variable is not empty
        for part in trace_id_parts:
            name, value = part.split('=')
            if name == 'Root':
                trace_kwargs['trace_id'] = value
            elif name == 'Parent':
                trace_kwargs['parent_id'] = value
            elif name == 'Sampled':
                trace_kwargs['sampled'] = bool(int(value))

    return XRayTraceID(**trace_kwargs)


def get_xray_daemon():
    """Parse X-Ray Daemon address environment variable.

    If the environment variable is not set, raise an exception to signal that
    we're unable to send data to X-Ray.
    """
    env_value = os.environ.get('AWS_XRAY_DAEMON_ADDRESS')
    if env_value is None:
        raise XRayDaemonNotFoundError()

    xray_ip, xray_port = env_value.split(':')
    return XRayDaemon(ip_address=xray_ip, port=int(xray_port))


def send_data_on_udp(ip_address, port, data):
    """Helper function to send a string over UDP to a specific IP/port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(data.encode('utf-8'), (ip_address, port))
    except:
        LOGGER.exception('Failed to send trace to X-Ray Daemon')
    finally:
        sock.close()


def send_segment_document_to_xray_daemon(segment_document):
    """Format and send document to the X-Ray Daemon."""
    try:
        xray_daemon = get_xray_daemon()
    except XRayDaemonNotFoundError:
        LOGGER.error('X-Ray Daemon not running, skipping send')
        return

    message = u'{header}\n{document}'.format(
        header=json.dumps(XRAY_DAEMON_HEADER),
        document=json.dumps(
            segment_document,
            ensure_ascii=False,
            cls=StringJSONEncoder,
        ),
    )

    send_data_on_udp(
        ip_address=xray_daemon.ip_address,
        port=xray_daemon.port,
        data=message,
    )


def send_subsegment_to_xray_daemon(subsegment_id, parent_id,
                                   start_time, end_time=None, name=None,
                                   namespace='remote', extra_data=None):
    """High level function to send data to the X-Ray Daemon.

    If `end_time` is set to `None` (which is the default), a partial subsegment
    will be sent to X-Ray, which has to be completed by a subsequent call to
    this function after the underlying operation finishes.

    The `namespace` argument can either be `aws` or `remote` (`local` is used
    as a default, but  it's not officially supported by X-Ray).

    The `extra_data` argument must be a `dict` that is used for updating the
    segment document with arbitrary data.
    """
    extra_data = extra_data or {}
    trace_id = get_trace_id()
    segment_document = {
        'type': 'subsegment',
        'id': subsegment_id,
        'trace_id': trace_id.trace_id,
        'parent_id': parent_id,
        'start_time': start_time,
    }
    if end_time is None:
        segment_document['in_progress'] = True
    else:
        segment_document.update({
            'end_time': end_time,
            'name': name,
            'namespace': namespace,
        })
        segment_document.update(extra_data)

    LOGGER.debug(
        'Prepared segment document for X-Ray Daemon',
        segment_document=segment_document,
    )
    send_segment_document_to_xray_daemon(segment_document)


def get_parent_id():
    """Retrieve the parent ID from the thread-local storage."""
    return getattr(threadlocal, 'parent_id', None)


def get_parent_id_from_trace_id():
    """Retrieve the parent ID from the trace ID environment variable."""
    trace_id = get_trace_id()
    return trace_id.parent_id


def set_parent_id(parent_id):
    """Store parent ID in the thread-local storage."""
    threadlocal.parent_id = parent_id


def get_function_name(wrapped, instance, args, kwargs):
    """Return the wrapped function's name."""
    return wrapped.__name__


def generic_xray_wrapper(wrapped, instance, args, kwargs, name, namespace,
                         metadata_extractor,
                         error_handling_type=ERROR_HANDLING_GENERIC):
    """Wrapper function around existing calls to send traces to X-Ray.

    `wrapped` is the original function, `instance` is the original instance,
    if the function is an instance method (otherwise it'll be `None`), `args`
    and `kwargs` are the positional and keyword arguments the original function
    was called with.

    The `name` argument can either be a `string` or a callable. In the latter
    case the function must accept the following arguments:

        def callback(wrapped, instance, args, kwargs):
            pass

    The `metadata_extractor` argument has to be a function with the following
    definition:

        def callback(wrapped, instance, args, kwargs, return_value):
            pass

    It has to return a `dict` that will be used to extend the segment document.

    The `error_handling_type` determines how exceptions raised by the wrapped
    function are handled. Currently `botocore` requires some special care.
    """
    if not get_trace_id().sampled:
        # Request not sampled by X-Ray, let's get to the call
        # immediately.
        LOGGER.debug('Request not sampled by X-Ray, skipping trace')
        return wrapped(*args, **kwargs)

    start_time = time.time()
    error = False
    cause = None

    # Fetch the parent ID from the current thread, and set it to the current
    # subsegment, so that downstream subsegments will be correctly nested.
    original_parent_id = get_parent_id()
    # If not parent ID exists in the thread-local storage, it means we're at
    # the topmost level, so we have to retrieve the parent ID from the trace ID
    # environment variable.
    parent_id = original_parent_id or get_parent_id_from_trace_id()
    subsegment_id = generate_subsegment_id()
    set_parent_id(subsegment_id)
    # Send partial subsegment to X-Ray, so that it'll know about the relations
    # upfront (otherwise we'll lose data, since downstream subsegments will
    # have invalid parent IDs).
    send_subsegment_to_xray_daemon(
        subsegment_id=subsegment_id,
        parent_id=parent_id,
        start_time=start_time,
    )
    try:
        return_value = wrapped(*args, **kwargs)
    except Exception as exc:
        error = True
        cause = {
            'exceptions': [
                {
                    'message': str(exc),
                    'type': '{}.{}'.format(
                        type(exc).__module__,
                        type(exc).__name__,
                    ),
                }
            ]
        }
        if error_handling_type == ERROR_HANDLING_GENERIC:
            return_value = None
        elif error_handling_type == ERROR_HANDLING_BOTOCORE:
            if isinstance(exc, ClientError):
                return_value = exc.response
            else:
                return_value = {}
        raise
    finally:
        end_time = time.time()
        extra_data = metadata_extractor(
            wrapped=wrapped,
            instance=instance,
            args=args,
            kwargs=kwargs,
            return_value=return_value,
        )
        extra_data['error'] = error
        if error:
            extra_data['cause'] = cause
        # We allow the name to be determined dynamically when a function is
        # passed in as the `name` argument.
        if callable(name):
            name = name(wrapped, instance, args, kwargs)
        send_subsegment_to_xray_daemon(
            subsegment_id=subsegment_id,
            parent_id=parent_id,
            start_time=start_time,
            end_time=end_time,
            name=name,
            namespace=namespace,
            extra_data=extra_data,
        )
        # After done with reporting the current subsegment, reset parent
        # ID to the original one.
        set_parent_id(original_parent_id)

    return return_value


def noop_function_metadata(wrapped, instance, args, kwargs, return_value):
    """Make sure that metadata is not changed."""
    return {}


def extract_function_metadata(wrapped, instance, args, kwargs, return_value):
    """Stash the `args` and `kwargs` into the metadata of the subsegment."""
    LOGGER.debug(
        'Extracting function call metadata',
        args=args,
        kwargs=kwargs,
    )
    return {
        'metadata': {
            'args': args,
            'kwargs': kwargs,
        },
    }


def trace_xray_subsegment(skip_args=False):
    """Can be applied to any function or method to be traced by X-Ray.

    If `skip_args` is True, the arguments of the function won't be sent to
    X-Ray.
    """
    @wrapt.decorator
    def wrapper(wrapped, instance, args, kwargs):
        metadata_extractor = (
            noop_function_metadata
            if skip_args
            else extract_function_metadata
        )
        return generic_xray_wrapper(
            wrapped, instance, args, kwargs,
            name=get_function_name,
            namespace='local',
            metadata_extractor=metadata_extractor,
        )

    return wrapper


def get_service_name(wrapped, instance, args, kwargs):
    """Return the AWS service name the client is communicating with."""
    if 'serviceAbbreviation' not in instance._service_model.metadata:
        return instance._service_model.metadata['endpointPrefix']
    return instance._service_model.metadata['serviceAbbreviation']


def extract_aws_metadata(wrapped, instance, args, kwargs, return_value):
    """Provide AWS metadata for improved visualization.

    See documentation for this data structure:
    http://docs.aws.amazon.com/xray/latest/devguide/xray-api-segmentdocuments.html#api-segmentdocuments-aws
    """
    response = return_value
    LOGGER.debug(
        'Extracting AWS metadata',
        args=args,
        kwargs=kwargs,
    )
    if 'operation_name' in kwargs:
        operation_name = kwargs['operation_name']
    else:
        operation_name = args[0]

    # Most of the time the actual keyword arguments to the client call are
    # passed in as a positial argument after the operation name.
    if len(kwargs) == 0 and len(args) == 2:
        kwargs = args[1]

    region_name = instance._client_config.region_name

    response_metadata = response.get('ResponseMetadata')

    metadata = {
        'aws': {
            'operation': operation_name,
            'region': region_name,
        }
    }

    if 'TableName' in kwargs:
        metadata['aws']['table_name'] = kwargs['TableName']
    if 'QueueUrl' in kwargs:
        metadata['aws']['queue_url'] = kwargs['QueueUrl']

    if response_metadata is not None:
        metadata['http'] = {
            'response': {
                'status': response_metadata['HTTPStatusCode'],
            },
        }
        metadata['aws']['request_id'] = response_metadata['RequestId']

    return metadata


def xray_botocore_api_call(wrapped, instance, args, kwargs):
    """Wrapper around botocore's base client API call method."""
    return generic_xray_wrapper(
        wrapped, instance, args, kwargs,
        name=get_service_name,
        namespace='aws',
        metadata_extractor=extract_aws_metadata,
        error_handling_type=ERROR_HANDLING_BOTOCORE,
    )


def monkey_patch_botocore_for_xray():
    """Explicit way to monkey-patch botocore to trace AWS API calls."""
    wrapt.wrap_function_wrapper(
        'botocore.client',
        'BaseClient._make_api_call',
        xray_botocore_api_call,
    )


def extract_http_metadata(wrapped, instance, args, kwargs, return_value):
    """Provide HTTP request metadata for improved visualization.

    See documentation for this data structure:
    http://docs.aws.amazon.com/xray/latest/devguide/xray-api-segmentdocuments.html#api-segmentdocuments-http
    """
    response = return_value
    LOGGER.debug(
        'Extracting HTTP metadata',
        args=args,
        kwargs=kwargs,
    )
    if 'request' in kwargs:
        request = kwargs['request']
    else:
        request = args[0]

    metadata = {
        'http': {
            'request': {
                'method': request.method.upper(),
                'url': request.url,
            },
        },
    }
    if response is not None:
        metadata['http']['response'] = {
            'status': response.status_code,
        }

    return metadata


def xray_requests_send(wrapped, instance, args, kwargs):
    """Wrapper around the requests library's low-level send method."""
    return generic_xray_wrapper(
        wrapped, instance, args, kwargs,
        name='requests',
        namespace='remote',
        metadata_extractor=extract_http_metadata,
    )


def monkey_patch_requests_for_xray():
    """Explicit way to monkey-patch requests to trace HTTP requests."""
    wrapt.wrap_function_wrapper(
        'requests.sessions',
        'Session.send',
        xray_requests_send,
    )
