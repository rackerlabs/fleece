import six
import base64
import json
import os
import sys
import unittest

import yaml

from fleece.cli.config import config

if six.PY2:
    import mock
    from StringIO import StringIO
else:
    from unittest import mock
    from io import StringIO

TEST_CONFIG = '.config.tmp'

test_yaml_config = '''foo: bar
password:
  -dev: :encrypt:dev-password
  -prod: :encrypt:prod-password
'''

test_json_config = '''{
    "foo": "bar",
    "password": {
        "-dev": ":encrypt:dev-password",
        "-prod": ":encrypt:prod-password"
    }
}
'''

test_config_file = '''foo: bar
password:
  -dev: :decrypt:ZGV2OmRldi1wYXNzd29yZA==
  -prod: :decrypt:cHJvZDpwcm9kLXBhc3N3b3Jk'''


def mock_encrypt(text, stage):
    return base64.b64encode('{}:{}'.format(stage, text).encode(
        'utf-8')).decode('utf-8')


def mock_decrypt(text, stage):
    s, d = base64.b64decode(text.encode('utf-8')).decode('utf-8').split(':')
    stage = stage.split(':')[-1]
    if s != stage:
        raise RuntimeError('wrong stage:' + s + ':' + stage)
    return d


@mock.patch('fleece.cli.config.config._encrypt_text', new=mock_encrypt)
@mock.patch('fleece.cli.config.config._decrypt_text', new=mock_decrypt)
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
            'foo': 'bar',
            'password': {
                '-dev': ':decrypt:ZGV2OmRldi1wYXNzd29yZA==',
                '-prod': ':decrypt:cHJvZDpwcm9kLXBhc3N3b3Jk'
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
            'foo': 'bar',
            'password': {
                '-dev': ':decrypt:ZGV2OmRldi1wYXNzd29yZA==',
                '-prod': ':decrypt:cHJvZDpwcm9kLXBhc3N3b3Jk'
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
            'foo': 'bar',
            'password': {
                '-dev': ':encrypt:dev-password',
                '-prod': ':encrypt:prod-password'
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
            'foo': 'bar',
            'password': {
                '-dev': ':encrypt:dev-password',
                '-prod': ':encrypt:prod-password'
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

    def test_render_default_stage_yaml_config(self, *args):
        stdout = sys.stdout
        sys.stdout = StringIO()
        with open(TEST_CONFIG, 'wt') as f:
            f.write(test_config_file)
        config.main(['-c', TEST_CONFIG, 'render', 'john:dev'])
        sys.stdout.seek(0)
        data = sys.stdout.read()
        sys.stdout = stdout
        self.assertEqual(yaml.load(data), {
            'foo': 'bar',
            'password': 'dev-password'
        })
