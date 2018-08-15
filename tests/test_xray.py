import os
import time
import unittest

import mock

from fleece import xray


class GetTraceIDTestCase(unittest.TestCase):
    ENV_VARIABLE = '_X_AMZN_TRACE_ID'

    def test_no_environment_variable(self):
        trace_id = xray.get_trace_id()

        self.assertIsNone(trace_id.trace_id)
        self.assertIsNone(trace_id.parent_id)
        self.assertFalse(trace_id.sampled)

    @mock.patch.dict(
        os.environ,
        {
            ENV_VARIABLE: 'Root=1-5901e3bc-8da3814a5f3ccbc864b66ecc;Parent=328f72132deac0ce;Sampled=1',  # noqa
        }
    )
    def test_full_trace_id_sampled(self):
        trace_id = xray.get_trace_id()

        self.assertEqual(
            trace_id.trace_id, '1-5901e3bc-8da3814a5f3ccbc864b66ecc'
        )
        self.assertEqual(
            trace_id.parent_id, '328f72132deac0ce'
        )
        self.assertTrue(trace_id.sampled)

    @mock.patch.dict(
        os.environ,
        {
            ENV_VARIABLE: 'Root=1-5901e3bc-8da3814a5f3ccbc864b66ecc;Sampled=0',
        }
    )
    def test_partial_trace_id_not_sampled(self):
        trace_id = xray.get_trace_id()

        self.assertEqual(
            trace_id.trace_id, '1-5901e3bc-8da3814a5f3ccbc864b66ecc'
        )
        self.assertIsNone(trace_id.parent_id)
        self.assertFalse(trace_id.sampled)


class GetSampledTestCase(unittest.TestCase):
    FORCE_ENV_VARIABLE = 'FLEECE_XRAY_FORCE_SAMPLE'
    TRACE_ID_ENV_VARIABLE = '_X_AMZN_TRACE_ID'

    def test_no_environment_variables_set(self):
        self.assertFalse(xray.get_sampled())

    @mock.patch.dict(
        os.environ,
        {
            TRACE_ID_ENV_VARIABLE: 'Root=1-5901e3bc-8da3814a5f3ccbc864b66ecc;Sampled=0'  # noqa
        }
    )
    def test_trace_not_sampled(self):
        self.assertFalse(xray.get_sampled())

    @mock.patch.dict(
        os.environ,
        {
            TRACE_ID_ENV_VARIABLE: 'Root=1-5901e3bc-8da3814a5f3ccbc864b66ecc;Sampled=1'  # noqa
        }
    )
    def test_trace_sampled(self):
        self.assertTrue(xray.get_sampled())

    @mock.patch.dict(
        os.environ,
        {
            FORCE_ENV_VARIABLE: '1',
            TRACE_ID_ENV_VARIABLE: 'Root=1-5901e3bc-8da3814a5f3ccbc864b66ecc;Sampled=0',  # noqa
        }
    )
    def test_trace_force_sampled(self):
        self.assertTrue(xray.get_sampled())


class GetXRayDaemonTestCase(unittest.TestCase):
    ENV_VARIABLE = 'AWS_XRAY_DAEMON_ADDRESS'

    def test_no_environment_variable(self):
        self.assertRaises(xray.XRayDaemonNotFoundError, xray.get_xray_daemon)

    @mock.patch.dict(
        os.environ,
        {
            ENV_VARIABLE: '169.254.79.2:2000',
        }
    )
    def test_get_xray_daemon(self):
        xray_daemon = xray.get_xray_daemon()

        self.assertEqual(xray_daemon.ip_address, '169.254.79.2')
        self.assertEqual(xray_daemon.port, 2000)


class SendSubsegmentToXRayDaemonTestCase(unittest.TestCase):

    def setUp(self):
        self.patch_send_segment_document = mock.patch(
            'fleece.xray.send_segment_document_to_xray_daemon')
        self.mock_send_segment_document = self.patch_send_segment_document.start()  # noqa

    def tearDown(self):
        self.patch_send_segment_document.stop()

    def test_in_progress_subsegment(self):
        current_time = time.time()

        xray.send_subsegment_to_xray_daemon(
            subsegment_id='SUBSEGMENT_ID',
            parent_id='PARENT_ID',
            start_time=current_time,
        )

        self.mock_send_segment_document.assert_called_once()
        segment_document = self.mock_send_segment_document.call_args[0][0]

        self.assertEqual(segment_document['type'], 'subsegment')
        self.assertEqual(segment_document['id'], 'SUBSEGMENT_ID')
        self.assertEqual(segment_document['parent_id'], 'PARENT_ID')
        self.assertEqual(segment_document['start_time'], current_time)
        self.assertTrue(segment_document['in_progress'])

    def test_full_segment_document_with_extra_data(self):
        current_time = time.time()
        end_time = current_time + 3.0
        extra_data = {
            'foo': 'BAR',
        }

        xray.send_subsegment_to_xray_daemon(
            subsegment_id='SUBSEGMENT_ID',
            parent_id='PARENT_ID',
            start_time=current_time,
            end_time=end_time,
            name='NAME',
            extra_data=extra_data,
        )

        self.mock_send_segment_document.assert_called_once()
        segment_document = self.mock_send_segment_document.call_args[0][0]

        self.assertEqual(segment_document['type'], 'subsegment')
        self.assertEqual(segment_document['id'], 'SUBSEGMENT_ID')
        self.assertEqual(segment_document['parent_id'], 'PARENT_ID')
        self.assertEqual(segment_document['start_time'], current_time)
        self.assertNotIn('in_progress', segment_document)
        self.assertEqual(segment_document['end_time'], end_time)
        self.assertEqual(segment_document['name'], 'NAME')
        self.assertEqual(segment_document['foo'], 'BAR')
