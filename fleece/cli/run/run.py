#!/usr/bin/env python
from __future__ import print_function

import argparse
import code
import os
import subprocess
import sys

import boto3
import requests
import yaml

try:
    import bpython
    have_bpython = True
except ImportError:
    have_bpython = False
try:
    from IPython import start_ipython
    have_ipython = True
except ImportError:
    have_ipython = False


RS_AUTH_ERROR = 'Rackspace authentication failed:\nStatus: {}\nResponse: {}'
ACCT_NOT_FOUND_ERROR = 'No AWS account for `{}` found in config'
NO_USER_OR_APIKEY_ERROR = 'You must provide a Rackspace username and apikey'
ENV_AND_ACCT_ERROR = 'Use only ONE of `--environment` or `--account`'
NO_ACCT_OR_ENV_ERROR = 'You must provide either `--environment` or `--account`'
ENV_AND_ROLE_ERROR = ('`--role` cannot be used with `--environment` '
                      '- use `role: <rolename>` in the config file instead')
FAWS_API_URL = ('https://accounts.api.manage.rackspace.com/v0/awsAccounts/{0}'
                '/credentials')
RS_IDENTITY_URL = 'https://identity.api.rackspacecloud.com/v2.0/tokens'
FAWS_API_ERROR = ('Could not fetch AWS Account credentials.\nStatus: {}\n'
                  'Reason: {}')


def get_parser():
    parser = argparse.ArgumentParser(
        prog='fleece run',
        description=('Run command in environment with AWS credentials from '
                     'Rackspace FAWS API')
    )
    parser.add_argument('--username', '-u', type=str,
                        help=('Rackspace username. Can also be set via '
                              'RS_USERNAME environment variable'))
    parser.add_argument('--apikey', '-k', type=str,
                        help=('Rackspace API key. Can also be set via '
                              'RS_API_KEY environment variable'))
    parser.add_argument('--config', '-c', type=str,
                        default='./environments.yml',
                        help=('Path to YAML config file with defined accounts '
                              'and aliases. Default is ./environments.yml'))
    parser.add_argument('--account', '-a', type=str,
                        help=('AWS account number. Cannot be used with '
                              '`--environment`'))
    parser.add_argument('--environment', '-e', type=str,
                        help=('Environment alias to AWS account defined in '
                              'config file. Cannot be used with `--account`'))
    parser.add_argument('--role', '-r', type=str,
                        help=('Role name to assume after obtaining credentials'
                              ' from FAWS API'))
    parser.add_argument('--interactive', '-i',
                        action='store_true', default=False,
                        help=('Launch an interactive Python shell. Will use '
                              'the more advanced shells if they are available '
                              '(bpython or IPyhon).'))
    parser.add_argument('--region', type=str,
                        help='Set default AWS region for the environment.')
    parser.add_argument('command', type=str, nargs='?',
                        help=('Command to execute. Required in '
                              'non-interactive mode.'))
    return parser


def parse_args(args):
    return get_parser().parse_args(args)


def assume_role(credentials, account, role):
    """Use FAWS provided credentials to assume defined role."""
    sts = boto3.client(
        'sts',
        aws_access_key_id=credentials['accessKeyId'],
        aws_secret_access_key=credentials['secretAccessKey'],
        aws_session_token=credentials['sessionToken'],
    )
    resp = sts.assume_role(
        RoleArn='arn:aws:sts::{}:role/{}'.format(account, role),
        RoleSessionName='fleece_assumed_role'
    )
    return {
        'accessKeyId': resp['Credentials']['AccessKeyId'],
        'secretAccessKey': resp['Credentials']['SecretAccessKey'],
        'sessionToken': resp['Credentials']['SessionToken'],
    }


def get_account(config, environment):
    """Find environment name in config object and return AWS account."""
    account = None
    for env in config.get('environments', []):
        if env.get('name') == environment:
            account = env.get('account')
            role = env.get('role')
            username = os.environ.get(env.get('rs_username_var')) \
                if env.get('rs_username_var') else None
            apikey = os.environ.get(env.get('rs_apikey_var')) \
                if env.get('rs_apikey_var') else None
    if not account:
        sys.exit(ACCT_NOT_FOUND_ERROR.format(environment))
    return account, role, username, apikey


def get_aws_creds(account, tenant, token):
    """Get AWS account credentials to enable access to AWS.

    Returns a time bound set of AWS credentials.
    """
    url = (FAWS_API_URL.format(account))
    headers = {
        'X-Auth-Token': token,
        'X-Tenant-Id': tenant,
    }
    response = requests.post(url, headers=headers,
                             json={'credential': {'duration': '3600'}})

    if not response.ok:
        sys.exit(FAWS_API_ERROR.format(response.status_code, response.text))
    return response.json()['credential']


def get_config(config_file):
    """Get config file and parse YAML into dict."""
    config_path = os.path.abspath(config_file)

    try:
        with open(config_path, 'r') as data:
            config = yaml.safe_load(data)
    except IOError as exc:
        sys.exit(str(exc))

    return config


def get_rackspace_token(username, apikey):
    """Get Rackspace Identity token.

    Login to Rackspace with cloud account and api key from environment vars.
    Returns dict of the token and tenant id.
    """
    auth_params = {
        "auth": {
            "RAX-KSKEY:apiKeyCredentials": {
                "username": username,
                "apiKey": apikey,
            }
        }
    }
    response = requests.post(RS_IDENTITY_URL, json=auth_params)
    if not response.ok:
        sys.exit(RS_AUTH_ERROR.format(response.status_code, response.text))

    identity = response.json()
    return (identity['access']['token']['id'],
            identity['access']['token']['tenant']['id'])


def validate_args(args):
    """Validate command-line arguments."""
    if not any([args.environment, args.account]):
        sys.exit(NO_ACCT_OR_ENV_ERROR)
    if args.environment and args.account:
        sys.exit(ENV_AND_ACCT_ERROR)
    if args.environment and args.role:
        sys.exit(ENV_AND_ROLE_ERROR)


def run(args):
    role = args.role

    if args.environment:
        config = get_config(args.config)
        account, role, cfg_username, cfg_apikey = get_account(
            config, args.environment)
    else:
        cfg_username, cfg_apikey = None, None
        account = args.account

    username = args.username or cfg_username or os.environ.get('RS_USERNAME')
    apikey = args.apikey or cfg_apikey or os.environ.get('RS_API_KEY')
    if not all([username, apikey]):
        sys.exit(NO_USER_OR_APIKEY_ERROR)
    token, tenant = get_rackspace_token(username, apikey)
    faws_credentials = get_aws_creds(account, tenant, token)

    if role:
        aws_credentials = assume_role(faws_credentials, account, role)
    else:
        aws_credentials = faws_credentials

    if args.interactive:
        run_interactive(aws_credentials, args.region)
    else:
        run_script(args.command, aws_credentials, args.region)


def run_script(command, aws_credentials, region=None):
    if command is None:
        get_parser().print_help()
        print('Command is a required argument in non-interactive mode.')
        sys.exit(1)

    env = os.environ.copy()
    env['AWS_ACCESS_KEY_ID'] = aws_credentials['accessKeyId']
    env['AWS_SECRET_ACCESS_KEY'] = aws_credentials['secretAccessKey']
    env['AWS_SESSION_TOKEN'] = aws_credentials['sessionToken']
    if region:
        env['AWS_DEFAULT_REGION'] = region

    process = subprocess.Popen(
        command,
        env=env,
        shell=True,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )
    for line in iter(process.stdout.readline, ''):
        sys.stdout.write(line)

    return_code = process.wait()
    sys.exit(return_code)


def run_interactive(aws_credentials, region=None):
    os.environ['AWS_ACCESS_KEY_ID'] = aws_credentials['accessKeyId']
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_credentials['secretAccessKey']
    os.environ['AWS_SESSION_TOKEN'] = aws_credentials['sessionToken']
    if region:
        os.environ['AWS_DEFAULT_REGION'] = region

    # Select Python shell
    if have_bpython:
        bpython.embed()
    elif have_ipython:
        start_ipython(argv=[])
    else:
        code.interact()


def main(args):
    parsed_args = parse_args(args)
    validate_args(parsed_args)
    run(parsed_args)
