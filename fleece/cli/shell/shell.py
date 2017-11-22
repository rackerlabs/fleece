#!/usr/bin/env python
import argparse
import code
import os

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

from fleece.cli.run import run


def parse_args(args):
    parser = argparse.ArgumentParser(
        prog='fleece shell',
        description=('Start interactive shell in environment with AWS '
                     'credentials from Rackspace FAWS API. Preferential order '
                     'of shells: bpython, IPython, default.')
    )
    parser.add_argument('--username', '-u', type=str,
                        default=os.environ.get('RS_USERNAME'),
                        help=('Rackspace username. Can also be set via '
                              'RS_USERNAME environment variable'))
    parser.add_argument('--apikey', '-k', type=str,
                        default=os.environ.get('RS_API_KEY'),
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
    parser.add_argument('--region', type=str,
                        help='Set default AWS region for the shell.')
    return parser.parse_args(args)


def start_shell(args):
    role = args.role

    if args.environment:
        config = run.get_config(args.config)
        account, role = run.get_account(config, args.environment)
    else:
        account = args.account

    token, tenant = run.get_rackspace_token(args.username, args.apikey)
    faws_credentials = run.get_aws_creds(account, tenant, token)

    if role:
        aws_credentials = run.assume_role(faws_credentials, account, role)
    else:
        aws_credentials = faws_credentials

    os.environ['AWS_ACCESS_KEY_ID'] = aws_credentials['accessKeyId']
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_credentials['secretAccessKey']
    os.environ['AWS_SESSION_TOKEN'] = aws_credentials['sessionToken']
    if args.region:
        os.environ['AWS_DEFAULT_REGION'] = args.region

    # Select Python shell
    if have_bpython:
        bpython.embed()
    elif have_ipython:
        start_ipython(argv=[])
    else:
        code.interact()


def main(args):
    parsed_args = parse_args(args)
    run.validate_args(parsed_args)
    start_shell(parsed_args)
