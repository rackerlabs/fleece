import mock
import unittest

from fleece import requests


class RequestsTests(unittest.TestCase):
    def setUp(self):
        self.session_request_patch = mock.patch("fleece.requests._Session.request")
        self.session_mount_patch = mock.patch("fleece.requests._Session.mount")
        self.session_request = self.session_request_patch.start()
        self.session_mount = self.session_mount_patch.start()

    def tearDown(self):
        self.session_request_patch.stop()
        self.session_mount_patch.stop()

    def _get_mount(self, pattern):
        ret = None
        for call in self.session_mount.mock_calls:
            if len(call[1]) == 2 and call[1][0] == pattern:
                ret = call[1][1]
        return ret

    def test_passthrough(self):
        requests.get("http://foo.com")
        self.session_request.assert_called_with(
            allow_redirects=True,
            method="get",
            params=None,
            timeout=(None, None),
            url="http://foo.com",
        )

    def test_timeout(self):
        requests.get("http://foo.com", timeout=10)
        self.session_request.assert_called_with(
            allow_redirects=True,
            method="get",
            params=None,
            timeout=10,
            url="http://foo.com",
        )

        requests.get("http://foo.com", timeout=(10, 15))
        self.session_request.assert_called_with(
            allow_redirects=True,
            method="get",
            params=None,
            timeout=(10, 15),
            url="http://foo.com",
        )

    def test_retries(self):
        requests.get("http://foo.com", retries=10)
        self.session_request.assert_called_with(
            allow_redirects=True,
            method="get",
            params=None,
            timeout=(None, None),
            url="http://foo.com",
        )
        adapter = self._get_mount("http://")
        self.assertEqual(adapter.max_retries.total, 10)
        adapter = self._get_mount("https://")
        self.assertEqual(adapter.max_retries.total, 10)

        requests.get("http://foo.com", retries={"total": 5})
        self.session_request.assert_called_with(
            allow_redirects=True,
            method="get",
            params=None,
            timeout=(None, None),
            url="http://foo.com",
        )
        adapter = self._get_mount("http://")
        self.assertEqual(adapter.max_retries.total, 5)
        adapter = self._get_mount("https://")
        self.assertEqual(adapter.max_retries.total, 5)

        requests.get("http://foo.com", retries={"read": 2, "backoff_factor": 2})
        self.session_request.assert_called_with(
            allow_redirects=True,
            method="get",
            params=None,
            timeout=(None, None),
            url="http://foo.com",
        )
        adapter = self._get_mount("http://")
        self.assertEqual(adapter.max_retries.read, 2)
        self.assertEqual(adapter.max_retries.connect, None)
        adapter = self._get_mount("https://")
        self.assertEqual(adapter.max_retries.read, 2)
        self.assertEqual(adapter.max_retries.connect, None)

    def test_default_timeout(self):
        try:
            requests.set_default_timeout(5)
            requests.get("http://foo.com")
            self.session_request.assert_called_with(
                allow_redirects=True,
                method="get",
                params=None,
                timeout=(5, 5),
                url="http://foo.com",
            )
        finally:
            requests.set_default_timeout(None)

    def test_default_retries(self):
        try:
            requests.set_default_retries(3)
            requests.get("http://foo.com")
            adapter = self._get_mount("https://")
            self.assertEqual(adapter.max_retries.total, 3)

            requests.set_default_retries(total=3)
            requests.get("http://foo.com")
            adapter = self._get_mount("https://")
            self.assertEqual(adapter.max_retries.total, 3)

            requests.set_default_retries(connect=3)
            requests.get("http://foo.com")
            adapter = self._get_mount("https://")
            self.assertEqual(adapter.max_retries.connect, 3)
            self.assertEqual(adapter.max_retries.read, None)
        finally:
            requests.set_default_retries()
