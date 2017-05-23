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
import werkzeug.wrappers

from fleece import httperror

_app_cache = {}


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
    body = json.dumps(request['body'])

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
                      validate_responses=True, cache_app=True):
    # Optionally cache application instances, because it takes a significant
    # amount of time to process the Swagger definition, and we shouldn't be
    # doing it on every single request.
    if app_name not in _app_cache or not cache_app:
        full_path_to_swagger_yaml = os.path.abspath(app_swagger_path)
        app = connexion.App(
            app_name,
            specification_dir=os.path.dirname(full_path_to_swagger_yaml),
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
    try:
        app = get_connexion_app(
            app_name=app_name,
            app_swagger_path=app_swagger_path,
            strict_validation=strict_validation,
            validate_responses=validate_responses,
            cache_app=cache_app,
        )
        environ = _build_wsgi_env(event, app_name)
        response = werkzeug.wrappers.Response.from_app(app, environ)
        response_dict = json.loads(response.get_data())

        if 400 <= response.status_code < 500:
            if ('error' in response_dict and
                    'message' in response_dict['error']):
                # Get the message from an error given by one of the endpoint
                # handlers.
                msg = response_dict['error']['message']
            else:
                # Get the message from the `connexion` plumbing, where the
                # message format is different.
                msg = response_dict['detail']
            logger.error(
                'Raising 4xx error',
                http_status=response.status_code,
                message=msg,
            )
            raise httperror.HTTPError(
                status=response.status_code,
                message=msg,
            )
        elif 500 <= response.status_code < 600:
            logger.error(
                'Raising 5xx error',
                response=response_dict,
                http_status=response.status_code,
            )
            raise httperror.HTTPError(status=response.status_code)
        else:
            return response_dict
    except httperror.HTTPError:
        logger.exception('HTTPError')
        raise
    except Exception:
        logger.exception('Unhandled exception')
        raise httperror.HTTPError(status=500)
