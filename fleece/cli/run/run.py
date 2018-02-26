#!/usr/bin/env python
import argparse
import os
import subprocess
import sys

import boto3
import requests
import yaml


RS_AUTH_ERROR = 'Rackspace authentication failed:\nStatus: {}\nResponse: {}'
ACCT_NOT_FOUND_ERROR = 'No AWS account for `{}` found in config'
NO_USER_OR_APIKEY_ERROR = 'You must provide a Rackspace username and apikey'
NO_USER_ENV_VAR_ERROR = 'Username environment variable `{}`, not found.'
NO_APIKEY_ENV_VAR_ERROR = 'Api key environment variable `{}` not found.'
ENV_AND_ACCT_ERROR = 'Use only ONE of `--environment` or `--account`'
NO_ACCT_OR_ENV_ERROR = 'You must provide either `--environment` or `--account`'
ENV_AND_ROLE_ERROR = ('`--role` cannot be used with `--environment` '
                      '- use `role: <rolename>` in the config file instead')
FAWS_API_URL = ('https://accounts.api.manage.rackspace.com/v0/awsAccounts/{0}'
                '/credentials')
RS_IDENTITY_URL = 'https://identity.api.rackspacecloud.com/v2.0/tokens'
FAWS_API_ERROR = ('Could not fetch AWS Account credentials.\nStatus: {}\n'
                  'Reason: {}')


def parse_args(args):

    for arg in args:
        try:
            cutoff = args.index('--')
            ap_args = args[:cutoff]
            run_args = args[cutoff + 1:]
        except ValueError:
            ap_args = args
            run_args = None

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
    if run_args is None:
        parser.add_argument('command', type=str, help=('Command to execute'))

    args_namespace = parser.parse_args(ap_args)

    if run_args is not None:
        args_namespace.command = run_args

    return args_namespace


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


def get_account(config, environment, require_username, require_apikey):
    """Find environment name in config object and return AWS account.

    If `require_username` or `require_apikey` are set, the process will exit
    if either environment variable can't be found.
    """
    account = None
    for env in config.get('environments', []):
        if env.get('name') == environment:
            account = env.get('account')
            role = env.get('role')
            if 'rs_username_var' in env:
                username = os.environ.get(env['rs_username_var'])
                if require_username and not username:
                    sys.exit(NO_USER_ENV_VAR_ERROR.format(
                             env['rs_username_var']))
            else:
                username = None
            if 'rs_apikey_var' in env:
                apikey = os.environ.get(env['rs_apikey_var'])
                if require_apikey and not apikey:
                    sys.exit(NO_APIKEY_ENV_VAR_ERROR.format(
                             env['rs_apikey_var']))
            else:
                apikey = None
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
            config,
            args.environment,
            require_username=args.username is None,
            require_apikey=args.apikey is None
        )
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

    env = os.environ.copy()
    env['AWS_ACCESS_KEY_ID'] = aws_credentials['accessKeyId']
    env['AWS_SECRET_ACCESS_KEY'] = aws_credentials['secretAccessKey']
    env['AWS_SESSION_TOKEN'] = aws_credentials['sessionToken']

    if isinstance(args.command, list):
        command = ' '.join("'{}'".format(c.replace("'", "\\'"))
                           for c in args.command)
    else:
        command = args.command

    sys.exit(subprocess.call(command, shell=True, env=env))


def main(args):
    parsed_args = parse_args(args)
    validate_args(parsed_args)
    run(parsed_args)
