try:
    from BaseHTTPServer import BaseHTTPRequestHandler
except ImportError:
    from http.server import BaseHTTPRequestHandler

# import lzstring
# lz = lzstring.LZString()
# lz.decompressFromBase64(SECRET)
SECRET = ('FAAj4yrAKVogfQeAlCV9qIDQ0agHTLQxxKK76U0GEKZg'
          '4Dkl9YA9NADoQfeJQHFiC4gAPgCJJ4np07BZS8OMqyo4'
          'kaNDcABoXUpoHePpAAuIxb5YQZq+cItbYXQFpitGjjfNgQAA')


class HTTPError(Exception):

    default_status = 500

    def __init__(self, status=None, message=None):
        """Initialize class."""
        responses = BaseHTTPRequestHandler.responses

        # Add some additional responses that aren't included...
        responses[418] = ('I\'m a teapot', SECRET)
        responses[422] = ('Unprocessable Entity',
                          'The request was well-formed but was'
                          ' unable to be followed due to semantic errors')

        self.status_code = status or self.default_status

        # Don't explode if provided status_code isn't found.
        _message = responses.get(self.status_code, [''])
        error_message = "{0:d}: {1}".format(self.status_code, _message[0])
        if message:
            error_message = "{0} - {1}".format(error_message, message)

        super(HTTPError, self).__init__(error_message)
