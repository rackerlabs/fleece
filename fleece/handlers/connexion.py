from __future__ import absolute_import

try:
    from cStringIO import cStringIO as StringIO
except ImportError:
    # Python 3
    from io import StringIO
import json
import os.path
try:
    from urllib import urlencode
except ImportError:
    # Python 3
    from urllib.parse import urlencode

import connexion
import six
import werkzeug.wrappers

from fleece.handlers.wsgi import build_wsgi_environ_from_event
from fleece import httperror
import fleece.log

_app_cache = {}

RESPONSE_CONTRACT_VIOLATION = 'Response body does not conform to specification'


class FleeceApp(connexion.App):
    """Wrapper around `connexion.App` with added helpers for Lambda."""

    def __init__(self, *args, **kwargs):
        """Create a FleeceApp.

        Parameters are identical to a `connexion.App, with the exception of the
        below keyword argument.

        :param logging.Logger logger:
            A Logger instance returned by `fleece.log.get_logger()` to be used
            for capturing details about errors.

            If `logger` is None, a default logger object will be created.
        """
        logger = kwargs.pop('logger', None)
        if logger is None:
            self.logger = fleece.log.get_logger(__name__)
        else:
            self.logger = logger

        super(FleeceApp, self).__init__(*args, **kwargs)

        # Capture and log any unexpected exceptions raise by handler code:
        def error_handler(exception):
            self.logger.exception(exception)
            # A `None` return value will not modify the response.
            # It's possible to return new types of responses from an error
            # handler.
            # To do so, simply return a new `werkzeug.wrappers.Response`
            # object.

        self.add_error_handler(Exception, error_handler)

    def call_api(self, event):
        """Make a request against the API defined by this app.

        Return any result from the API call as a JSON object/dict. In the event
        of a client or server error response from the API endpoint handler (4xx
        or 5xx), raise a :class:`fleece.httperror.HTTPError` containing some
        context about the error. Any unexpected exception encountered while
        executing an API endpoint handler will be appropriately raised as a
        generic 500 error with no error context (in order to not expose too
        much of the internals of the application).

        :param dict event:
            Dictionary containing the entire request payload passed to the
            Lambda function handler.
        :returns:
            JSON object (as a `list` or `dict`) containing the response data
            from the API endpoint.
        :raises:
            :class:`fleece.httperror.HTTPError` on 4xx or 5xx responses from
            the API endpoint handler, or a 500 response on an unexpected
            failure (due to a bug in handler code, for example).
        """
        try:
            environ = _build_wsgi_env(event, self.import_name)
            response = werkzeug.wrappers.Response.from_app(self, environ)
            response_dict = json.loads(response.get_data())

            if 400 <= response.status_code < 500:
                if ('error' in response_dict and
                        'message' in response_dict['error']):
                    # FIXME(larsbutler): If 'error' is not a collection
                    # (list/dict) and is a scalar such as an int, the check
                    # `message in response_dict['error']` will blow up and
                    # result in a generic 500 error. This check assumes too
                    # much about the format of error responses given by the
                    # handler. It might be good to allow this handling to
                    # support custom structures.
                    msg = response_dict['error']['message']
                elif 'detail' in response_dict:
                    # Likely this is a generated 400 response from Connexion.
                    # Reveal the 'detail' of the message to the user.
                    # NOTE(larsbutler): If your API handler explicitly returns
                    # a 'detail' key in in the response, be aware that this
                    # will be exposed to the client.
                    msg = response_dict['detail']
                else:
                    # Respond with a generic client error.
                    msg = 'Client Error'
                # FIXME(larsbutler): The logic above still assumes a lot about
                # the API response. That's not great. It would be nice to make
                # this more flexible and explicit.
                self.logger.error(
                    'Raising 4xx error',
                    http_status=response.status_code,
                    message=msg,
                )
                raise httperror.HTTPError(
                    status=response.status_code,
                    message=msg,
                )
            elif 500 <= response.status_code < 600:
                if response_dict['title'] == RESPONSE_CONTRACT_VIOLATION:
                    # This case is generally enountered if the API endpoint
                    # handler code does not conform to the contract dictated by
                    # the Swagger specification.
                    self.logger.error(
                        RESPONSE_CONTRACT_VIOLATION,
                        detail=response_dict['detail']
                    )
                else:
                    # This case will trigger if
                    # a) the handler code raises an unexpected exception
                    # or
                    # b) the handler code explicitly returns a 5xx error.
                    self.logger.error(
                        'Raising 5xx error',
                        response=response_dict,
                        http_status=response.status_code,
                    )
                raise httperror.HTTPError(status=response.status_code)
            else:
                return response_dict
        except httperror.HTTPError:
            self.logger.exception('HTTPError')
            raise
        except Exception:
            self.logger.exception('Unhandled exception')
            raise httperror.HTTPError(status=500)

    def call_proxy_api(self, event):
        """Make a request against the API defined by this app.

        Return any result from the API call as a dict that is expected by the
        AWS_PROXY type integration in API Gateway.

        :param dict event:
            Dictionary containing the entire request payload passed to the
            Lambda function handler.
        :returns:
            Dictionary containing the response data from the API endpoint.
        :raises:
            :class:`fleece.httperror.HTTPError` on 4xx or 5xx responses from
            the API endpoint handler, or a 500 response on an unexpected
            failure (due to a bug in handler code, for example).
        """
        try:
            environ = build_wsgi_environ_from_event(event)
            response = werkzeug.wrappers.Response.from_app(self, environ)
            return {
                'statusCode': response.status_code,
                'headers': {
                    header: value for header, value in response.headers.items()
                },
                'body': response.get_data(as_text=True),
            }
        except Exception:
            # We should actually never get here, because exceptions raised
            # within the application are handled by the error handlers, and the
            # default one will return a clean 500 error during the happy path
            # above.
            self.logger.exception('Unhandled exception')
            return {
                'statusCode': 500,
                'headers': {},
                'body': json.dumps({
                    'error': {
                        'message': 'Internal server error.',
                    },
                }),
            }


def _build_wsgi_env(event, app_name):
    """Turn the Lambda/API Gateway request event into a WSGI environment dict.

    :param dict event:
        The event parameters passed to the Lambda function entrypoint.
    :param str app_name:
        Name of the API application.
    """
    gateway = event['parameters']['gateway']
    request = event['parameters']['request']
    ctx = event['rawContext']
    headers = request['header']
    body = six.text_type(json.dumps(request['body']))

    # Render the path correctly so connexion/flask will pass the path params to
    # the handler function correctly.
    # Basically, this replaces "/foo/{param1}/bar/{param2}" with
    # "/foo/123/bar/456".
    path = gateway['resource-path'].format(
        **event['parameters']['request']['path']
    )
    environ = {
        'PATH_INFO': path,
        'QUERY_STRING': urlencode(request['querystring']),
        'REMOTE_ADDR': ctx['identity']['sourceIp'],
        'REQUEST_METHOD': ctx['httpMethod'],
        'SCRIPT_NAME': app_name,
        'SERVER_NAME': app_name,
        'SERVER_PORT': headers.get('X-Forwarded-Port', '80'),
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': headers.get('X-Forwarded-Proto', 'http'),
        'wsgi.input': StringIO(body),
        'wsgi.errors': StringIO(),
        'wsgi.multiprocess': False,
        'wsgi.multithread': False,
        'wsgi.run_once': False,
        'CONTENT_TYPE': headers.get('Content-Type', 'application/json'),
    }
    if ctx['httpMethod'] in ['POST', 'PUT', 'PATCH']:
        environ['CONTENT_LENGTH'] = str(len(body))

    for header_name, header_value in headers.items():
        wsgi_name = 'HTTP_{}'.format(header_name.upper().replace('-', '_'))
        environ[wsgi_name] = str(header_value)

    return environ


def get_connexion_app(app_name, app_swagger_path, strict_validation=True,
                      validate_responses=True, cache_app=True, logger=None):
    # Optionally cache application instances, because it takes a significant
    # amount of time to process the Swagger definition, and we shouldn't be
    # doing it on every single request.
    if app_name not in _app_cache or not cache_app:
        full_path_to_swagger_yaml = os.path.abspath(app_swagger_path)
        app = FleeceApp(
            app_name,
            specification_dir=os.path.dirname(full_path_to_swagger_yaml),
            logger=logger,
        )
        app.add_api(
            os.path.basename(full_path_to_swagger_yaml),
            strict_validation=strict_validation,
            validate_responses=validate_responses,
        )
        _app_cache[app_name] = app

    return _app_cache[app_name]


def call_api(event, app_name, app_swagger_path, logger, strict_validation=True,
             validate_responses=True, cache_app=True):
    """Wire up the incoming Lambda/API Gateway request to an application.

    :param dict event:
        Dictionary containing the entire request template. This can vary wildly
        depending on the template structure and contents.
    :param str app_name:
        Name of the API application.
    :param str app_swagger_path:
        Local path to the Swagger API YAML file.
    :param logging.Logger logger:
        A Logger instance returned by `fleece.log.get_logger()` to be used for
        capturing details about errors.
    :param bool strict_validation:
        Toggle to enable/disable Connexion's parameter validation.
    :param bool validate_responses:
        Toggle to enable/disable Connexion's response validation.
    :param bool cache_app:
        Toggle to enable/disable the caching of the Connextion/Flask app
        instance. It's on by default, because it provides a significant
        performance improvement in the Lambda runtime environment.
    """
    app = get_connexion_app(
        app_name=app_name,
        app_swagger_path=app_swagger_path,
        strict_validation=strict_validation,
        validate_responses=validate_responses,
        cache_app=cache_app,
    )
    return app.call_api(event)


def call_proxy_api(event, app_name, app_swagger_path, logger,
                   strict_validation=True, validate_responses=True,
                   cache_app=True):
    """Wire up the incoming Lambda/API Gateway request to an application.

    Integration type of the resource must be AWS_LAMBDA in order for this to
    work.

    :param dict event:
        Dictionary containing the entire request template. This can vary wildly
        depending on the template structure and contents.
    :param str app_name:
        Name of the API application.
    :param str app_swagger_path:
        Local path to the Swagger API YAML file.
    :param logging.Logger logger:
        A Logger instance returned by `fleece.log.get_logger()` to be used for
        capturing details about errors.
    :param bool strict_validation:
        Toggle to enable/disable Connexion's parameter validation.
    :param bool validate_responses:
        Toggle to enable/disable Connexion's response validation.
    :param bool cache_app:
        Toggle to enable/disable the caching of the Connextion/Flask app
        instance. It's on by default, because it provides a significant
        performance improvement in the Lambda runtime environment.
    """
    app = get_connexion_app(
        app_name=app_name,
        app_swagger_path=app_swagger_path,
        strict_validation=strict_validation,
        validate_responses=validate_responses,
        cache_app=cache_app,
    )
    return app.call_proxy_api(event)
