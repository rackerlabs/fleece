#!/usr/bin/env python
import argparse
import json
import os
import subprocess
import sys
import tempfile

import ruamel.yaml as yaml
import six

import base64


def _encrypt_text(text, stage):
    # TODO: use kms here
    return base64.b64encode(text.encode('utf-8')).decode('utf-8')


def _decrypt_text(text, stage):
    # TODO: use kms here
    return base64.b64decode(text.encode('utf-8')).decode('utf-8')


def _encrypt_item(data, stage, key):
    if (isinstance(data, six.text_type) or isinstance(data, six.binary_type)) \
            and data.startswith(':encrypt:'):
        if not stage:
            sys.stderr.write('Warning: Key "{}" cannot be encrypted because '
                             'it does not belong to a stage\n'.format(key))
        else:
            data = ':decrypt:' + _encrypt_text(data[9:], stage)
    elif isinstance(data, dict):
        per_stage = [k.startswith('-') for k in data]
        if any(per_stage):
            if not all(per_stage):
                raise ValueError('Keys "{}" have a mix of stage and non-stage '
                                 'variables'.format(', '.join(data.keys)))
            key_prefix = key + '.' if key else ''
            for k, v in data.items():
                data[k] = _encrypt_item(v, stage=k[1:], key=key_prefix + k)
        else:
            data = _encrypt_dict(data, stage=stage, key=key)
    elif isinstance(data, list):
        data = _encrypt_list(data, stage=stage, key=key)
    return data


def _encrypt_list(data, stage, key):
    return [_encrypt_item(v, stage=stage, key=key + '[]') for v in data]


def _encrypt_dict(data, stage=None, key=''):
    key_prefix = key + '.' if key else ''
    for k, v in data.items():
        data[k] = _encrypt_item(v, stage=stage, key=key_prefix + k)
    return data


def import_config(args):
    source = sys.stdin.read().strip()
    if source[0] == '{':
        # JSON input
        config = json.loads(source)
    else:
        # YAML input
        config = yaml.round_trip_load(source)

    config = _encrypt_dict(config)
    with open(args.config, 'wt') as f:
        if config:
            yaml.round_trip_dump(config, f)


def _decrypt_item(data, stage, key, render):
    if (isinstance(data, six.text_type) or isinstance(data, six.binary_type)) \
            and data.startswith(':decrypt:'):
        data = _decrypt_text(data[9:], stage)
        if not render:
            data = ':encrypt:' + data
    elif isinstance(data, dict):
        per_stage = [k.startswith('-') for k in data]
        if any(per_stage):
            if not all(per_stage):
                raise ValueError('Keys "{}" have a mix of stage and non-stage '
                                 'variables'.format(', '.join(data.keys)))
        if render:
            main_stage, default_stage = (stage + ':').split(':')[:2]
            if per_stage[0]:
                if '-' + main_stage in data:
                    data = _decrypt_item(
                        data.get(stage, data['-' + main_stage]),
                        stage=stage, key=key, render=render)
                elif '-' + default_stage in data:
                    data = _decrypt_item(
                        data.get(stage, data['-' + default_stage]),
                        stage=stage, key=key, render=render)
                else:
                    raise ValueError('Key "{}" has no value for stage '
                                     '"{}"'.format(key, stage))
            else:
                data = _decrypt_dict(data, stage=stage, key=key, render=render)
        else:
            key_prefix = key + '.' if key else ''
            for k, v in data.items():
                data[k] = _decrypt_item(v, stage=k[1:], key=key_prefix + k,
                                        render=render)
            data = _decrypt_dict(data, stage=stage, key=key, render=render)
    elif isinstance(data, list):
        data = _decrypt_list(data, stage=stage, key=key, render=render)
    return data


def _decrypt_list(data, stage, key, render):
    return [_decrypt_item(v, stage=stage, key=key + '[]', render=render)
            for v in data]


def _decrypt_dict(data, stage=None, key='', render=False):
    key_prefix = key + '.' if key else ''
    for k, v in data.items():
        data[k] = _decrypt_item(v, stage=stage, key=key_prefix + k,
                                render=render)
    return data


def export_config(args):
    if os.path.exists(args.config):
        with open(args.config, 'rt') as f:
            config = yaml.round_trip_load(f.read())
        config = _decrypt_dict(config)
    else:
        config = {}
    if args.json:
        print(json.dumps(config, indent=4))
    elif config:
        yaml.round_trip_dump(config, sys.stdout)


def edit_config(args):
    ftemp, filename = tempfile.mkstemp()
    os.close(ftemp)

    with open(filename, 'wt') as fd:
        stdout = sys.stdout
        sys.stdout = fd
        export_config(args)
        sys.stdout = stdout

    subprocess.call(args.editor + ' ' + filename, shell=True)

    with open(filename, 'rt') as fd:
        stdin = sys.stdin
        sys.stdin = fd
        import_config(args)
        sys.stdin = stdin

    os.unlink(filename)


def render_config(args):
    with open(args.config, 'rt') as f:
        config = yaml.safe_load(f.read())
    config = _decrypt_item(config, stage=args.stage, key='', render=True)
    if args.json:
        print(json.dumps(config, indent=4))
    elif config:
        yaml.round_trip_dump(config, sys.stdout)


def upload_config(args):
    print('not implemented yet')


def parse_args(args):
    parser = argparse.ArgumentParser(
        prog='fleece config',
        description=('Configuration management')
    )
    parser.add_argument(
        '--config', '-c', default='config.yml',
        help='Config file (default is config.yml)')
    subparsers = parser.add_subparsers(help='Sub-command help')

    import_parser = subparsers.add_parser(
        'import', help='Import configuration from stdin')
    import_parser.set_defaults(func=import_config)

    export_parser = subparsers.add_parser(
        'export', help='Export configuration to stdout')
    export_parser.add_argument(
        '--json', action='store_true',
        help='Use JSON format (default is YAML)')
    export_parser.set_defaults(func=export_config)

    edit_parser = subparsers.add_parser(
        'edit', help='Edit configuration')
    edit_parser.add_argument(
        '--json', action='store_true',
        help='Use JSON format (default is YAML)')
    edit_parser.add_argument(
        '--editor', '-e', default=os.environ.get('FLEECE_EDITOR', 'vi'),
        help='Text editor (defaults to $FLEECE_EDITOR, or else "vi")')
    edit_parser.set_defaults(func=edit_config)

    render_parser = subparsers.add_parser(
        'render', help='Render configuration for a stage')
    render_parser.add_argument(
        '--json', action='store_true',
        help='Use JSON format (default is YAML)')
    render_parser.add_argument(
        'stage', help='Target stage name')
    render_parser.set_defaults(func=render_config)

    upload_parser = subparsers.add_parser(
        'upload', help='Upload configuration to SSM')
    upload_parser.set_defaults(func=upload_config)
    return parser.parse_args(args)


def main(args):
    parsed_args = parse_args(args)
    parsed_args.func(parsed_args)
