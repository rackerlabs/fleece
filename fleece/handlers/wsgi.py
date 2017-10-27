from werkzeug.test import EnvironBuilder


def build_wsgi_environ_from_event(event):
    """Create a WSGI environment from the proxy integration event."""
    params = event.get('queryStringParameters')
    environ = EnvironBuilder(method=event.get('httpMethod') or 'GET',
                             path=event.get('path') or '/',
                             headers=event.get('headers') or {},
                             data=event.get('body') or b'',
                             query_string=params or {}).get_environ()
    environ['SERVER_PORT'] = 443
    if 'execute-api' in environ['HTTP_HOST']:
        # this is the API-Gateway hostname, which takes the stage as the first
        # script path component
        environ['SCRIPT_NAME'] = '/' + event['requestContext'].get('stage')
    else:
        # we are using our own hostname, nothing gets added to the script path
        environ['SCRIPT_NAME'] = ''
    environ['wsgi.url_scheme'] = 'https'
    environ['lambda.event'] = event
    return environ


def wsgi_handler(event, context, app, logger):
    """lambda handler function.
    This function runs the WSGI app with it and collects its response, then
    translates the response back into the format expected by the API Gateway
    proxy integration.
    """

    environ = build_wsgi_environ_from_event(event)
    wsgi_status = []
    wsgi_headers = []

    logger.info('Processing {} request'.format(environ['REQUEST_METHOD']))

    def start_response(status, headers):
        if len(wsgi_status) or len(wsgi_headers):
            raise RuntimeError('start_response called more than once!')
        wsgi_status.append(status)
        wsgi_headers.append(headers)

    resp = list(app(environ, start_response))
    proxy = {'statusCode': int(wsgi_status[0].split()[0]),
             'headers': {h[0]: h[1] for h in wsgi_headers[0]},
             'body': b''.join(resp).decode('utf-8')}

    logger.info("Returning {}".format(proxy['statusCode']),
                http_status=proxy['statusCode'])

    return proxy
