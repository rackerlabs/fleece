import mock
import unittest

from fleece.httperror import HTTPError
from fleece.raxauth import authenticate

# This isn't a real token - go away.
TEST_TOKEN = ('gAAAAABWq9MR30nr8Zx_-bgyAzBnWgFxnsxbup_cN01G7aoM66c7wEwz4r'
              'QtTmniRVOhkVaF9a0Rt11IPMEqZ0mFk3bS7a4v4gAvmNa0-zE27UkuG58S'
              'bRqe8zpyzRzyVEZsjR4fnza5')


def mock_validation(token):
    if token == TEST_TOKEN:
        return
    else:
        raise HTTPError(status=401)


@authenticate()
def authentication_test(token=None):
    return "AUTHENTICATED"


class TestRaxAuth(unittest.TestCase):

    @mock.patch('fleece.raxauth.validate', side_effect=mock_validation)
    def test_raxauth(self, validation_function):
        result = authentication_test(token=TEST_TOKEN)
        self.assertEqual(result, 'AUTHENTICATED')

    @mock.patch('fleece.raxauth.validate', side_effect=mock_validation)
    def test_unauthorized_empty(self, validation_function):
        self.assertRaisesRegexp(HTTPError, '401: Unauthorized',
                                authentication_test, token='bogus')
