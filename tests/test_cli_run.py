import os
import unittest

from moto import mock_sts
import six
import yaml

from fleece.cli.run import run
from . import utils

if six.PY2:
    import mock
else:
    from unittest import mock


class TestCLIRun(unittest.TestCase):

    def setUp(self):
        self.aws_credentials = {
            'credential': {
                'accessKeyId': '123456',
                'secretAccessKey': '987654',
                'sessionToken': '456789',
            }
        }
        self.account = '123456789012'
        self.role = 'LambdaDeployRole'
        self.environment = 'foo'
        self.config = 'environments:\n  - name: {}\n    account: "{}"'.format(
            self.environment, self.account)

    def test_environment_or_account(self):
        args = [
            '--account',
            self.account,
            '--environment',
            self.environment,
            'wat'
        ]

        with self.assertRaises(SystemExit) as exc:
            run.main(args)
            self.assertIn(
                run.ENV_AND_ACCT_ERROR,
                str(exc.exception)
            )

    def test_no_account_or_environment(self):
        args = ['wat']

        with self.assertRaises(SystemExit) as exc:
            run.main(args)
            self.assertIn(
                run.NO_ACCT_OR_ENV_ERROR,
                str(exc.exception)
            )

    def test_environment_with_role(self):
        args = [
            '--environment',
            'foo',
            '--role',
            self.role,
            'wat'
        ]

        with self.assertRaises(SystemExit) as exc:
            run.main(args)
            self.assertIn(
                run.ENV_AND_ROLE_ERROR,
                str(exc.exception)
            )

    def test_no_username(self):
        args = [
            '--account',
            self.account,
            '--apikey',
            'foo',
            'wat'
        ]

        with self.assertRaises(SystemExit) as exc:
            run.main(args)
            self.assertIn(run.NO_USER_OR_APIKEY_ERROR, str(exc.exception))

    def test_no_apikey(self):
        args = [
            '--account',
            self.account,
            '--username',
            'foo',
            'wat'
        ]

        with self.assertRaises(SystemExit) as exc:
            run.main(args)
            self.assertIn(run.NO_USER_OR_APIKEY_ERROR, str(exc.exception))

    def test_good_rackspace_token(self):
        response_mock = mock.MagicMock()
        response_mock.ok = True
        response_mock.json = lambda: utils.USER_DATA

        with mock.patch('fleece.cli.run.run.requests.post',
                        return_value=response_mock) as requests_mock:
            token, tenant = run.get_rackspace_token('foo', 'bar')
            requests_mock.assert_called_with(
                'https://identity.api.rackspacecloud.com/v2.0/tokens',
                json={
                    'auth': {
                        'RAX-KSKEY:apiKeyCredentials': {
                            'username': 'foo',
                            'apiKey': 'bar'
                        }
                    }
                },
            )
        self.assertEqual(utils.TEST_TOKEN, token)
        self.assertEqual(utils.USER_DATA['access']['token']['tenant']['id'],
                         tenant)

    def test_bad_rackspace_token(self):
        response_mock = mock.MagicMock()
        response_mock.ok = False
        response_mock.status_code = 401
        response_mock.text = 'Narp'
        with mock.patch('fleece.cli.run.run.requests.post',
                        return_value=response_mock):
            with self.assertRaises(SystemExit) as exc:
                run.get_rackspace_token('foo', 'bar')
                self.assertIn(
                    run.RS_AUTH_ERROR.format(response_mock.status_code,
                                             response_mock.text),
                    str(exc.exception),
                )

    def test_get_aws_creds(self):
        response_mock = mock.MagicMock()
        response_mock.ok = True
        response_mock.json = mock.MagicMock(return_value=self.aws_credentials)
        with mock.patch('fleece.cli.run.run.requests.post',
                        return_value=response_mock) as requests_mock:
            creds = run.get_aws_creds(self.account, '123456', 'foo')
            requests_mock.assert_called_with(
                run.FAWS_API_URL.format(self.account),
                headers={
                    'X-Auth-Token': 'foo',
                    'X-Tenant-Id': '123456',
                },
                json={
                    'credential': {
                        'duration': '3600'
                    }
                },
            )

        self.assertDictEqual(self.aws_credentials['credential'], creds)

    def test_get_aws_creds_fail(self):
        response_mock = mock.MagicMock()
        response_mock.ok = False
        response_mock.status_code = 404
        response_mock.test = 'Narp'
        with mock.patch('fleece.cli.run.run.requests.post',
                        return_value=response_mock):
            with self.assertRaises(SystemExit) as exc:
                run.get_aws_creds(self.account, '123456', 'foo')
                self.assertIn(
                    run.FAWS_API_ERROR.format(response_mock.status_code,
                                              response_mock.text),
                    str(exc.exception),
                )

    def test_assume_role(self):
        with mock_sts():
            creds = run.assume_role(self.aws_credentials['credential'],
                                    self.account, self.role)

            # There is currently a bug in moto that causes it to simply
            # return the passed-in RoleArn instead of an actual assumed-role
            # ARN. Disabling these until fixed in moto.
            #
            # expected_arn = 'arn:aws:sts::{}:assumed-role/{}/{}'.format(
            #     self.account,
            #     self.role,
            #     'fleece_assumed_role',
            # )
            # self.assertEqual(
            #     creds['AssumedRoleUser']['Arn'],
            #     expected_arn,
            # )

            expected_keys = ['secretAccessKey', 'sessionToken', 'accessKeyId']
            [self.assertIn(key, creds) for key in expected_keys]

    def test_get_config(self):
        mock_open = mock.mock_open(read_data=self.config)
        with mock.patch('fleece.cli.run.run.open', mock_open, create=True):
            config = run.get_config('./wat')

        self.assertDictEqual(yaml.load(self.config), config)

    def test_bad_config_file_path(self):
        with self.assertRaises(SystemExit) as exc:
            run.get_config('./nope')
        self.assertIn('No such file or directory', str(exc.exception))

    def test_get_account(self):
        config = yaml.load(self.config)
        account, role, username, apikey = run.get_account(config,
                                                          self.environment)
        self.assertEqual(account, self.account)
        self.assertIsNone(role)
        self.assertIsNone(username)
        self.assertIsNone(apikey)

    def test_get_account_with_creds(self):
        os.environ['MY_USERNAME'] = 'foo'
        os.environ['MY_APIKEY'] = 'bar'
        config = yaml.load(
            'environments:\n'
            '  - name: {}\n'
            '    account: "{}"\n'
            '    rs_username_var: MY_USERNAME\n'
            '    rs_api_key_var: MY_APIKEY'.format(
                self.environment, self.account))
        account, role, username, apikey = run.get_account(config,
                                                          self.environment)
        del os.environ['MY_USERNAME']
        del os.environ['MY_APIKEY']
        self.assertEqual(account, self.account)
        self.assertIsNone(role)
        self.assertEqual(username, 'foo')
        self.assertEqual(apikey, 'bar')

    def test_environment_not_found(self):
        with self.assertRaises(SystemExit) as exc:
            run.get_account({}, self.environment)
        self.assertIn(run.ACCT_NOT_FOUND_ERROR.format(self.environment),
                      str(exc.exception))
