import unittest

from fleece import httperror


class HTTPErrorTests(unittest.TestCase):
    """Tests for :class:`fleece.httperror.HTTPError`."""

    def test_error_msg_format(self):
        with self.assertRaises(httperror.HTTPError) as err:
            raise httperror.HTTPError(status=404)
        self.assertEqual("404: Not Found", str(err.exception))

    def test_error_msg_format_custom_message(self):
        with self.assertRaises(httperror.HTTPError) as err:
            raise httperror.HTTPError(status=404, message="Nothing Here")
        self.assertEqual("404: Not Found - Nothing Here", str(err.exception))
