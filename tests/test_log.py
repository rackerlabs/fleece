import logging
import mock
import unittest
import uuid

from fleece.log import setup_root_logger, get_logger, RetryHandler

setup_root_logger()


class LogHandler(logging.Handler):
    def __init__(self, fail=1):
        super(LogHandler, self).__init__()
        self.fail = fail
        self.attempt = 0
        self.log = []

    def emit(self, record):
        self.attempt += 1
        if self.attempt <= self.fail:
            raise RuntimeError(str(self.attempt))
        record.msg = record.msg.replace("foo", "foo-" + str(self.attempt))
        self.log.append(record)


class LogTests(unittest.TestCase):
    def setUp(self):
        self.logger = get_logger(uuid.uuid4().hex)

    def test_retry_handler_with_retries(self):
        h = LogHandler(fail=2)
        self.logger.addHandler(RetryHandler(h, max_retries=5))
        self.logger.error("foo")
        self.assertEqual(len(h.log), 1)
        self.assertIn('event": "foo-3"', h.log[0].getMessage())

    @mock.patch("fleece.log.time.sleep")
    @mock.patch("fleece.log.random", return_value=1)
    def test_retry_handler_with_max_retries(self, mock_random, mock_sleep):
        h = LogHandler(fail=3)
        self.logger.addHandler(RetryHandler(h, max_retries=2))
        self.logger.error("foo")
        self.assertEqual(h.log, [])
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(mock_sleep.call_args_list[0], mock.call(0.1))
        self.assertEqual(mock_sleep.call_args_list[1], mock.call(0.2))

    def test_retry_handler_with_max_retries_and_raise(self):
        h = LogHandler(fail=3)
        self.logger.addHandler(RetryHandler(h, max_retries=2, ignore_errors=False))
        with self.assertRaises(RuntimeError) as r:
            self.logger.error("foo")
        self.assertEqual(str(r.exception), "1")
        self.assertEqual(h.log, [])

    def test_retry_handler_no_retries(self):
        h = LogHandler(fail=1)
        self.logger.addHandler(RetryHandler(h, max_retries=0))
        self.logger.error("foo")
        self.assertEqual(h.log, [])

    def test_retry_handler_no_retries_and_raise(self):
        h = LogHandler(fail=1)
        self.logger.addHandler(RetryHandler(h, max_retries=0, ignore_errors=False))
        with self.assertRaises(RuntimeError) as r:
            self.logger.error("foo")
        self.assertEqual(str(r.exception), "1")
        self.assertEqual(h.log, [])

    @mock.patch("fleece.log.time.sleep")
    @mock.patch("fleece.log.random", return_value=1)
    def test_retry_handler_with_custom_backoff(self, mock_random, mock_sleep):
        h = LogHandler(fail=4)
        self.logger.addHandler(
            RetryHandler(h, max_retries=4, backoff_base=0.4, backoff_cap=1.2)
        )
        self.logger.error("foo")
        self.assertEqual(len(h.log), 1)
        self.assertIn('event": "foo-5"', h.log[0].getMessage())
        self.assertEqual(mock_sleep.call_count, 4)
        self.assertEqual(mock_sleep.call_args_list[0], mock.call(0.4))
        self.assertEqual(mock_sleep.call_args_list[1], mock.call(0.8))
        self.assertEqual(mock_sleep.call_args_list[2], mock.call(1.2))
        self.assertEqual(mock_sleep.call_args_list[3], mock.call(1.2))
