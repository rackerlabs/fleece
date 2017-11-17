import six
import base64
import json
import os
import re
import sys
import unittest

import yaml

from fleece.cli.config import config

if six.PY2:
    import mock
    from StringIO import StringIO

    # fullmatch is not available on PY2
    def fullmatch(pattern, text, *args, **kwargs):
        match = re.match(pattern, text, *args, **kwargs)
        return match if match.group(0) == text else None

    re.fullmatch = fullmatch
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
    +/ba.*/: :decrypt:L2JhLiovOmJhci1wYXNzd29yZA=='''


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
    if s != stage and not re.fullmatch(s.split('/')[1], stage):
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
            'password': 'dev-password'
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
            'password': 'foo-password'
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
            'password': 'bar-password'
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
            'password': 'prod-password'
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
                'password': 'prod-password'
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
            'password': 'prod-password'
        })
