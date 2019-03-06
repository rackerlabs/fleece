import six
import base64
import json
import os
import sys
import unittest

import yaml

from fleece.cli.config import config
from fleece import utils

if six.PY2:
    import mock
    from StringIO import StringIO
else:
    from unittest import mock
    from io import StringIO

TEST_CONFIG = '.config.tmp'

test_yaml_config = '''stages:
  /.*/:
    environment: dev
    key: dev-key
  prod:
    environment: prod
    key: prod-key
config:
  foo: bar
  password:
    +dev: :encrypt:dev-password
    +prod: :encrypt:prod-password
    +foo: :encrypt:foo-password
    +/ba.*/: :encrypt:bar-password
  nest:
    bird: pigeon
    tree: birch
'''

test_json_config = '''{
    "stages": {
        "/.*/": {
            "environment": "dev",
            "key": "dev-key"
        },
        "prod": {
            "environment": "prod",
            "key": "prod-key"
        }
    },
    "config": {
        "foo": "bar",
        "password": {
            "+dev": ":encrypt:dev-password",
            "+prod": ":encrypt:prod-password"
        },
        "nest": {
            "bird": "pigeon",
            "tree": "birch"
        }
    }
}
'''

test_config_file = '''stages:
  /.*/:
    environment: dev
    key: dev-key
  prod:
    environment: prod
    key: prod-key
config:
  foo: bar
  password:
    +dev: :decrypt:ZGV2OmRldi1wYXNzd29yZA==
    +prod: :decrypt:cHJvZDpwcm9kLXBhc3N3b3Jk
    +foo: :decrypt:Zm9vOmZvby1wYXNzd29yZA==
    +/ba.*/: :decrypt:L2JhLiovOmJhci1wYXNzd29yZA==
  nest:
    bird: pigeon
    tree: birch'''


test_environments = {
    'environments': [
        {'name': 'dev', 'account': '1234567890'},
        {'name': 'prod', 'account': '0987654321'}
    ]
}


def mock_encrypt(text, stage):
    return base64.b64encode('{}:{}'.format(stage, text).encode(
        'utf-8')).decode('utf-8')


def mock_decrypt(text, stage):
    s, d = base64.b64decode(text.encode('utf-8')).decode('utf-8').split(':', 1)
    stage = stage.split(':')[-1]
    if s != stage and not utils.fullmatch(s.split('/')[1], stage):
        raise RuntimeError('wrong stage:' + s + ':' + stage)
    return d


@mock.patch('fleece.cli.config.config._encrypt_text', new=mock_encrypt)
@mock.patch('fleece.cli.config.config._decrypt_text', new=mock_decrypt)
@mock.patch('fleece.cli.run.run.get_config', return_value=test_environments)
class TestCLIConfig(unittest.TestCase):
    def tearDown(self):
        if os.path.exists(TEST_CONFIG):
            os.unlink(TEST_CONFIG)

    def test_import_yaml_config(self, *args):
        stdin = sys.stdin
        sys.stdin = StringIO(test_yaml_config)
        config.main(['-c', TEST_CONFIG, 'import'])
        sys.stdin = stdin

        with open(TEST_CONFIG, 'rt') as f:
            data = yaml.load(f.read())
        self.assertEqual(data, {
            'stages': {
                '/.*/': {'environment': 'dev', 'key': 'dev-key'},
                'prod': {'environment': 'prod', 'key': 'prod-key'}
            },
            'config': {
                'foo': 'bar',
                'password': {
                    '+dev': ':decrypt:ZGV2OmRldi1wYXNzd29yZA==',
                    '+prod': ':decrypt:cHJvZDpwcm9kLXBhc3N3b3Jk',
                    '+foo': ':decrypt:Zm9vOmZvby1wYXNzd29yZA==',
                    '+/ba.*/': ':decrypt:L2JhLiovOmJhci1wYXNzd29yZA=='
                },
                'nest': {
                    'bird': 'pigeon',
                    'tree': 'birch',
                }
            }
        })

    def test_import_json_config(self, *args):
        stdin = sys.stdin
        sys.stdin = StringIO(test_json_config)
        config.main(['-c', TEST_CONFIG, 'import'])
        sys.stdin = stdin

        with open(TEST_CONFIG, 'rt') as f:
            data = yaml.load(f.read())
        self.assertEqual(data, {
            'stages': {
                '/.*/': {'environment': 'dev', 'key': 'dev-key'},
                'prod': {'environment': 'prod', 'key': 'prod-key'}
            },
            'config': {
                'foo': 'bar',
                'password': {
                    '+dev': ':decrypt:ZGV2OmRldi1wYXNzd29yZA==',
                    '+prod': ':decrypt:cHJvZDpwcm9kLXBhc3N3b3Jk'
                },
                'nest': {
                    'bird': 'pigeon',
                    'tree': 'birch',
                }
            }
        })

    def test_export_yaml_config(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'export'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        self.assertEqual(yaml.load(data), {
            'stages': {
                '/.*/': {'environment': 'dev', 'key': 'dev-key'},
                'prod': {'environment': 'prod', 'key': 'prod-key'}
            },
            'config': {
                'foo': 'bar',
                'password': {
                    '+dev': ':encrypt:dev-password',
                    '+prod': ':encrypt:prod-password',
                    '+foo': ':encrypt:foo-password',
                    '+/ba.*/': ':encrypt:bar-password'
                },
                'nest': {
                    'bird': 'pigeon',
                    'tree': 'birch',
                }
            }
        })

    def test_export_json_config(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'export', '--json'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        self.assertEqual(json.loads(data), {
            'stages': {
                '/.*/': {'environment': 'dev', 'key': 'dev-key'},
                'prod': {'environment': 'prod', 'key': 'prod-key'}
            },
            'config': {
                'foo': 'bar',
                'password': {
                    '+dev': ':encrypt:dev-password',
                    '+prod': ':encrypt:prod-password',
                    '+foo': ':encrypt:foo-password',
                    '+/ba.*/': ':encrypt:bar-password'
                },
                'nest': {
                    'bird': 'pigeon',
                    'tree': 'birch',
                }
            }
        })

    def test_render_yaml_config(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'render', 'dev'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        self.assertEqual(yaml.load(data), {
            'foo': 'bar',
            'password': 'dev-password',
            'nest': {
                'bird': 'pigeon',
                'tree': 'birch',
            }
        })

    def test_render_yaml_config_custom(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'render', 'foo'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        self.assertEqual(yaml.load(data), {
            'foo': 'bar',
            'password': 'foo-password',
            'nest': {
                'bird': 'pigeon',
                'tree': 'birch',
            }
        })

    def test_render_yaml_config_custom_regex(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'render', 'baz'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        self.assertEqual(yaml.load(data), {
            'foo': 'bar',
            'password': 'bar-password',
            'nest': {
                'bird': 'pigeon',
                'tree': 'birch',
            },
        })

    def test_render_json_config(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'render', 'prod', '--json'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        self.assertEqual(json.loads(data), {
            'foo': 'bar',
            'password': 'prod-password',
            'nest': {
                'bird': 'pigeon',
                'tree': 'birch',
            }
        })

    def test_render_encrypted_config(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'render', 'prod', '--encrypt'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        self.assertEqual(
            json.loads(mock_decrypt(json.loads(data)[0], 'prod')), {
                'foo': 'bar',
                'password': 'prod-password',
                'nest': {
                    'bird': 'pigeon',
                    'tree': 'birch',
                }
            })

    def test_render_python_config(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'render', 'prod', '--python'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        g = {'ENCRYPTED_CONFIG': None}
        exec(data.split('\n')[0], g)
        data = mock_decrypt(g['ENCRYPTED_CONFIG'][0], 'prod')
        self.assertEqual(json.loads(data), {
            'foo': 'bar',
            'password': 'prod-password',
            'nest': {
                'bird': 'pigeon',
                'tree': 'birch',
            }
        })

    class FakeAws:
        def __init__(self):
            self.fake_parameter_store = {}

            class StsClient:
                def get_caller_identity(self):
                    return {'Account': '12345'}

            class SsmClient:
                def put_parameter(self_2, Name, Value, Type, Overwrite,
                                  **kwargs):
                    self.fake_parameter_store[Name] = Value
                    if 'KeyId' in kwargs:
                        assert isinstance(kwargs["KeyId"], str)
                        del kwargs['KeyId']
                    assert len(kwargs) == 0

                    assert Type == 'SecureString'
                    assert Overwrite

            class KmsClient:
                def describe_key(self, KeyId):
                    key_arn = (
                        'arn:aws:kms:us-east-1:123456789012:key/'
                        '11111111-2222-3333-4444-555555555555'
                    )
                    return {
                        'KeyMetadata': {
                            'KeyId': key_arn
                        }
                    }

            def fake_boto3_client(name, *args, **kwargs):
                if name == 'sts':
                    return StsClient()
                elif name == 'ssm':
                    return SsmClient()
                elif name == 'kms':
                    return KmsClient()
                raise AssertionError("non-mocked boto3 call")

            self._fake_boto3_client = fake_boto3_client

        def patch(self):
            return mock.patch('boto3.client', self._fake_boto3_client)

    def fake_awscreds(self, environment):
        assert environment == 'prod'
        return {
            'accessKeyId': ':)',
            'secretAccessKey': '0-..',
            'sessionToken': '$',
        }

    def test_render_parameter_store(self, *args):
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)

        fake_aws = self.FakeAws()

        with fake_aws.patch():
            with mock.patch.object(config.AWSCredentialCache,
                                   'get_awscreds', self.fake_awscreds):
                config.main(['-c', TEST_CONFIG, 'render', 'prod',
                             '--parameter-store', '/super-service/blah'])

        sys.stdout.seek(0)
        data = sys.stdout.read()

        actual_lines = [line for line in data.split('\n') if line]

        self.assertEqual(
            'Writing config with parameter store prefix '
            '/super-service/blah to AWS account 12345',
            actual_lines[0]
        )
        for index, actual_line in enumerate(actual_lines[1:]):
            self.assertTrue(
                actual_line.startswith('Writing /super-service/blah/'),
                msg='Line {} was {}'.format(index + 1, actual_line))

        self.assertEqual(
            {
                '/super-service/blah/foo': 'bar',
                '/super-service/blah/password': 'prod-password',
                '/super-service/blah/nest/bird': 'pigeon',
                '/super-service/blah/nest/tree': 'birch',
            },
            fake_aws.fake_parameter_store
        )

    def _test_bad_config(self, config_arg, error_msg,
                         prefix='/super-service/blah'):
        with mock.patch.object(config.AWSCredentialCache,
                               'get_awscreds', self.fake_awscreds):
            try:
                config.write_to_parameter_store(
                    'prod', prefix, config_arg)
                self.fail('Expected ValueError')
            except ValueError as ve:
                self.assertTrue(error_msg in str(ve),
                                msg='Error msg "{}"" not found n exception '
                                    'string "{}".'.format(error_msg, str(ve)))

    def test_render_parameter_store_bad_prefix(self, *args):
        self._test_bad_config(
            {
                'a': 'a',
            },
            'Parameter store names must be fully qualified',
            prefix='no-slash',
        )

    def test_render_parameter_store_validate_bad_text(self, *args):
        self._test_bad_config(
            {
                'hello how are you': ':)'
            },
            'invalid parameter name'
        )

    def test_render_parameter_store_validate_str_or_dict(self, *args):
        self._test_bad_config(
            {
                'bool': True
            },
            'all config values must be strings or dictionaries'
        )

    def test_render_parameter_store_validate_str_or_dict_2(self, *args):
        self._test_bad_config(
            {
                'list': ['1', '2', '3'],
            },
            'all config values must be strings or dictionaries'
        )

    def test_render_parameter_store_validate_hierarchy(self, *args):
        root_bad_config = {}
        bad_config = root_bad_config
        for i in range(15):
            bad_config['n'] = {}
            bad_config = bad_config['n']

        self._test_bad_config(
            root_bad_config,
            'Error writing name '
            '"/super-service/blah/n/n/n/n/n/n/n/n/n/n/n/n/n/n": '
            'parameter store names allow for no more than 15 levels '
            'of hierarchy.'
        )
