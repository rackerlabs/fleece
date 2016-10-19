from __future__ import absolute_import

from requests import *  # noqa
from requests.packages.urllib3.util import Retry
from requests.adapters import HTTPAdapter
from requests import Session as _Session

DEFAULT_CONNECT_TIMEOUT = None
DEFAULT_READ_TIMEOUT = None
DEFAULT_RETRY_ARGS = {}


def set_default_timeout(timeout=None, connect_timeout=None, read_timeout=None):
    """
    The purpose of this function is to install default socket timeouts and
    retry policy for requests calls. Any requests issued through the requests
    wrappers defined in this module will have these automatically set, unless
    explicitly overriden.

    The default timeouts and retries set through this option apply to the
    entire process. For that reason, it is recommended that this function is
    only called once during startup, and from the main thread, before any
    other threads are spawned.

    :param timeout timeout for socket connections and reads in seconds. This is
                   a convenience argument that applies the same default to both
                   connection and read timeouts.
    :param connect_timeout timeout for socket connections in seconds.
    :param read_timeout timeout for socket reads in seconds.
    """
    global DEFAULT_CONNECT_TIMEOUT
    global DEFAULT_READ_TIMEOUT
    DEFAULT_CONNECT_TIMEOUT = connect_timeout if connect_timeout is not None \
        else timeout
    DEFAULT_READ_TIMEOUT = read_timeout if read_timeout is not None \
        else timeout


def set_default_retries(*args, **kwargs):
    """
    This function installs a default retry mechanism to be used in requests
    calls. The arguments are those of urllib3's `Retry` object (see
    http://urllib3.readthedocs.io/en/latest/reference/urllib3.util.html#urllib3.util.retry.Retry).

    Examples:

        # use 3 retries, for default conditions only (network errors/timeouts)
        set_default_retries(total=3)
        set_default_retries(3)  # total can be given as a positional argument

        # use 5 retries, and add 429 and 503 responses to the list of
        # retryable conditions
        set_default_retries(5, status_forcelist=[429, 503])

        # use 5 retries with an exponential backoff factor of 1
        set_default_retries(5, backoff_factor=1)
    """
    global DEFAULT_RETRY_ARGS
    DEFAULT_RETRY_ARGS = kwargs
    if len(args) > 1:
        ValueError('too many arguments')
    elif len(args) == 1:
        DEFAULT_RETRY_ARGS['total'] = args[0]


class Session(_Session):
    """
    This is a wrapper for requests's `Session` class that adds support for
    injecting a retry mechanism into all outgoing requests.

    :param retries The retry mechanism to use. If `None`, the default retry
                   arguments are used. If an `int`, retry as many times, using
                   the default retry arguments. If a `dict`, use as arguments
                   to a urllib3 `Retry` object. If none of the above types,
                   then it is assumed to be a `urllib3.Retry` instance.
    """
    def __init__(self, timeout=None, retries=None):
        super(Session, self).__init__()
        self.timeout = timeout
        if retries is None:
            retry = Retry(**DEFAULT_RETRY_ARGS)
        elif isinstance(retries, int):
            args = DEFAULT_RETRY_ARGS.copy()
            args.pop('total', None)
            retry = Retry(total=retries, **args)
        elif isinstance(retries, dict):
            retry = Retry(**retries)
        self.mount('http://', HTTPAdapter(max_retries=retry))
        self.mount('https://', HTTPAdapter(max_retries=retry))

    def request(self, method, url, **kwargs):
        """
        Send a request.
        If timeout is not explicitly given, use the default timeouts.
        """
        if 'timeout' not in kwargs:
            if self.timeout is not None:
                kwargs['timeout'] = self.timeout
            else:
                kwargs['timeout'] = (DEFAULT_CONNECT_TIMEOUT,
                                     DEFAULT_READ_TIMEOUT)
        return super(Session, self).request(method=method, url=url, **kwargs)


def request(method, url, **kwargs):
    """
    Wrapper for the `requests.request()` function.
    It accepts the same arguments as the original, plus an optional `retries`
    that overrides the default retry mechanism.
    """
    retries = kwargs.pop('retries', None)
    with Session(retries=retries) as session:
        return session.request(method=method, url=url, **kwargs)


def get(url, params=None, **kwargs):
    """Sends a GET request.
    :param url: URL for the new :class:`Request` object.
    :param params: (optional) Dictionary or bytes to be sent in the query
                   string for the :class:`Request`.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """
    kwargs.setdefault('allow_redirects', True)
    return request('get', url, params=params, **kwargs)


def options(url, **kwargs):
    """Sends a OPTIONS request.
    :param url: URL for the new :class:`Request` object.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """
    kwargs.setdefault('allow_redirects', True)
    return request('options', url, **kwargs)


def head(url, **kwargs):
    """Sends a HEAD request.
    :param url: URL for the new :class:`Request` object.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """
    kwargs.setdefault('allow_redirects', False)
    return request('head', url, **kwargs)


def post(url, data=None, json=None, **kwargs):
    """Sends a POST request.
    :param url: URL for the new :class:`Request` object.
    :param data: (optional) Dictionary, bytes, or file-like object to send in
                 the body of the :class:`Request`.
    :param json: (optional) json data to send in the body of the
                 :class:`Request`.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """
    return request('post', url, data=data, json=json, **kwargs)


def put(url, data=None, **kwargs):
    """Sends a PUT request.
    :param url: URL for the new :class:`Request` object.
    :param data: (optional) Dictionary, bytes, or file-like object to send in
                 the body of the :class:`Request`.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """
    return request('put', url, data=data, **kwargs)


def patch(url, data=None, **kwargs):
    """Sends a PATCH request.
    :param url: URL for the new :class:`Request` object.
    :param data: (optional) Dictionary, bytes, or file-like object to send in
                 the body of the :class:`Request`.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """
    return request('patch', url,  data=data, **kwargs)


def delete(url, **kwargs):
    """Sends a DELETE request.
    :param url: URL for the new :class:`Request` object.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """
    return request('delete', url, **kwargs)
