import mock
import unittest

from fleece.httperror import HTTPError
from fleece.raxauth import authenticate
from . import utils


def mock_validation(token):
    if token == utils.TEST_TOKEN:
        return utils.USER_DATA
    else:
        raise HTTPError(status=401)


@authenticate()
def authentication_test(token=None, userinfo=None):
    return "AUTHENTICATED"


class TestRaxAuth(unittest.TestCase):
    @mock.patch("fleece.raxauth.validate", side_effect=mock_validation)
    def test_raxauth(self, validation_function):
        result = authentication_test(token=utils.TEST_TOKEN, userinfo=None)
        self.assertEqual(result, "AUTHENTICATED")

    @mock.patch("fleece.raxauth.validate", side_effect=mock_validation)
    def test_unauthorized_empty(self, validation_function):
        self.assertRaisesRegex(
            HTTPError, "401: Unauthorized", authentication_test, token="bogus"
        )
