# Fleece

## Logging

To start using fleece with a lambda project you will need to make 2 small updates to your project.

* Where you would normally import `logging.get_logger` or `logging.getLogger` use`fleece.log.get_logger` or `fleece.log.getLogger`

* In the file with your primary lambda handler include `fleece.log.setup_root_logger()`prior to setting up any additional logging.

This should ensure that all handlers on the root logger are cleaned up and one with appropriate stream handlers is in place.

### Retry logging calls

A retry wrapper for logging handlers that occasionally fail is also provided. This wrapper can be useful in preventing crashes when logging calls to external services such as CloudWatch fail.

For example, consider the following handler for CloudWatch using watchtower:

```python
logger.addHandler(
    watchtower.CloudWatchLogHandler(log_group='WORKER-POLL',
                                    stream_name=str(uuid.uuid4()),
                                    use_queues=False))
```

If the CloudWatch service is down, or rate limits the client, that will cause logging calls to raise an exception, which may interrupt the script. To avoid that, the watchtower handler can be wrapped in a `RetryHandler` as follows:

```python
logger.addHandler(
    fleece.log.RetryHandler(
        watchtower.CloudWatchLogHandler(log_group='WORKER-POLL',
                                        stream_name=str(uuid.uuid4()),
                                        use_queues=False)))
```

In the above example, logging calls that fail will be retried up to 5 times, using an exponential backoff algorithm to increasingly space out retries. If all retries fail, then the logging call will, by default, give up silently and return, allowing the program to continue. See the documentation for the `RetryHandler` class for information on how to customize the retry strategy.

### Logging request IDs for each log event

It might be very helpful to have the API Gateway and/or Lambda request IDs present in each log event, so that troubleshooting problematic requests becomes easy. If you apply the `fleece.log.inject_request_ids_into_environment` decorator to the Lambda handler function, an `api_request_id` (only if the event source is API Gateway) and a `lambda_request_id` attribute will be added to the log event dictionary.

## boto3 wrappers

This project includes `fleece.boto3.client()` and `fleece.boto3.resource()` wrappers that support a friendly format for setting less conservative timeouts than the default 60 seconds used by boto. The following additional arguments are accepted to set these timeouts:

- `connect_timeout`: timeout for socket connections in seconds.
- `read_timeout`: timeout for socket read operations in seconds.
- `timeout`: convenience timeout that sets both of the above to the same value.

Also for convenience, timeouts can be set globally by calling `fleece.boto3.set_default_timeout()` at startup. Globally set timeouts are then applied to all clients, unless explicitly overriden. Default timeouts set via the `set_default_timeout()` function apply to all threads, and for that reason it is a good idea to only call this function during start up, before any additional threads are spawn.

As an example, the following code written against the original boto3 package uses the default 60 second socket timeouts:

```python
import boto3
# ...
lambda = boto3.client('lambda')
```

If you wanted to use 15 second timeouts instead, you can simply switch to the fleece wrappers as follows:

```python
from fleece import boto3
boto3.set_default_timeout(15)
# ...
lambda = boto3.client('lambda')
```

You can import other boto3 attributes, but only `client()` and `resource()` accept the additional arguments documented in this section.

## requests wrappers

This project also includes a wrapper for the requests package. When using `fleece.requests`, convenient access to set timeouts and retries is provided.

The high-level request functions such as `requests.get()` and `requests.post()` accept the following arguments:

- `timeout`: a network timeout, or a tuple containing the connection and
             read timeouts, in seconds. Note that this is functionality that
             exists in the requests package.
- `retries`: a retry mechanism to use with this request. This argument can be
             of several types: if it is `None`, then the default retry
             mechanism installed by the `set_default_retries` function is used;
             if it is an integer, it is the number of retries to use; if it is
             a dictionary, it must have the arguments to a urllib3 `Retry`
             instance. Alternatively, this argument can be a Retry instance as
             well.

The `Session` class is also wrapped. A session instance from this module also accepts the two arguments above, and passes them on to any requests it issues.

Finally, it is also possible to install global timeout and retry defaults that are used for any requests that don't specify them explicitly. This enables existing code to take advantage of retries and timeouts after changing the imports to point to this wrapped version of requests. Below is an example that sets global timeouts and retries:

```python
from fleece import requests

# 15 second timeout
requests.set_default_timeout(15)

# 5 retries with exponential backoff, also retry 429 and 503 responses
requests.set_default_retries(total=5, backoff_factor=1,
                             status_forcelist=[429, 503])

# the defaults above apply to any regular requests, no need to make
# changes to existing code.
r = requests.get('https://...')

# a request can override the defaults if desired
r = requests.put('https://...', timeout=25, retries=2)

# sessions are also supported
with requests.Session() as session:
    session.get('https://...')
```

## X-Ray integration

This project also bridges the gap of missing Python support in the [AWS X-Ray](https://aws.amazon.com/xray/) [Lambda integration](http://docs.aws.amazon.com/xray/latest/devguide/xray-services-lambda.html).

### Prerequisites

 1. Make sure you add the following permissions to the Lambda execution role of your function: `xray:PutTraceSegments` and `xray:PutTelemetryRecords`.
 2. Enable active tracing under Advanced settings on the Configuration tab of your Lambda function in the AWS Console (or using the [`update_function_configuration` API call](http://boto3.readthedocs.io/en/latest/reference/services/lambda.html#Lambda.Client.update_function_configuration)).

### Features

You can mark any function or method for tracing by using the `@trace_xray_subsegment` decorator. You can apply the decorator to any number of functions and methods, the resulting trace will be properly nested. You have to decorate all the methods you want traced (e.g. if you decorate your handler function only, no other functions will be traced that it calls).

This module also provides wrappers for `boto` and `requests` so that any AWS API call, or HTTP request will be automatically traced by X-Ray, but you have to explicitly allow this behavior by calling `monkey_patch_botocore_for_xray` and/or `monkey_patch_requests_for_xray`. The best place to do this would be the main handler module where the Lambda entry point is defined.

### A quick example (`handler.py`)

```python
from fleece import boto3
from fleece.xray import (monkey_patch_botocore_for_xray,
                         trace_xray_subsegment)

monkey_patch_botocore_for_xray()


@trace_xray_subsegment()
def lambda_handler(event, context):
    return get_user()


def get_user():
    # This function doesn't have to be decorated, because the API call to IAM
    # will be traced thanks to the monkey-patching.
    iam = boto3.client('iam')
    return iam.get_user()
```

**Note:** the monkey-patched tracing will also work with the wrappers described above.

## Connexion integration

Summary about what [Connexion](https://github.com/zalando/connexion) exactly is (from their project page):

 > Connexion is a framework on top of [Flask](http://flask.pocoo.org/) that automagically handles HTTP requests based on [OpenAPI 2.0 Specification](https://github.com/OAI/OpenAPI-Specification/blob/master/versions/2.0.md) (formerly known as Swagger Spec) of your API described in [YAML format](https://github.com/OAI/OpenAPI-Specification/blob/master/versions/2.0.md#format). Connexion allows you to write a Swagger specification, then maps the endpoints to your Python functions; this makes it unique, as many tools generate the specification based on your Python code. You can describe your REST API in as much detail as you want; then Connexion guarantees that it will work as you specified.

It's the perfect glue between your API Gateway API specification and your Lambda function. Fleece makes it very easy to use Connexion:

```python
from fleece.connexion import call_api
from fleece.log import get_logger

logger = get_logger(__name__)


def lambda_handler(event, context):
    return call_api(event, 'myapi', 'swagger.yml', logger)
```

You just have to make sure that the `swagger.yml` file is included in the Lambda bundle. For the API Gateway integration, we assume the [request template defined by yoke](https://github.com/rackerlabs/yoke/blob/master/yoke/templates.py#L60-L132) for now.

Using this integration has the added benefit of being able to run your API locally, by adding something like this to your Lambda handler:

```python
from fleece.connexion import get_connexion_app

[...]

if __name__ == '__main__':
    app = get_connexion_app('myapi', 'swagger.yml')
    app.run(8080)
```

## Fleece CLI

Fleece offers a limited functionality CLI to help build Lambda packages and run commands in a shell environment with AWS credentials from a Rackspace Fanatical AWS Account. The CLI functionality is not installed by default but can be installed as an extras package. NOTE: Package building with Fleece requires Docker.

### Installation

```
pip install fleece[cli]
```

### `fleece build`

```
usage: fleece build [-h] [--python36] [--rebuild]
                    [--requirements REQUIREMENTS]
                    [--dependencies DEPENDENCIES] [--target TARGET]
                    [--source SOURCE]
                    [--exclude [EXCLUDE [EXCLUDE ...]]]
                    service_dir

Simple Lambda builder.

positional arguments:
  service_dir           directory where the service is located (default: $pwd)

optional arguments:
  -h, --help            show this help message and exit
  --python36, -3        use Python 3.6 (default: Python 2.7)
  --rebuild             rebuild Python dependencies
  --requirements REQUIREMENTS, -r REQUIREMENTS
                        requirements.txt file with dependencies (default:
                        $service_dir/src/requirements.txt)
  --dependencies DEPENDENCIES, -d DEPENDENCIES
                        comma separated list of system dependencies
  --target TARGET, -t TARGET
                        target directory for lambda_function.zip (default
                        $service_dir/dist)
  --source SOURCE, -s SOURCE
                        source directory to include in lambda_function.zip
                        (default: $service_dir/src)
  --exclude [EXCLUDE [EXCLUDE ...]], -e [EXCLUDE [EXCLUDE ...]]
                        glob pattern to exclude
```

To build a lambda package from the service's top-level directory:

```
$ fleece build .
```

The assumptions made with the above command are that the source code of the service is in `./src`, the requirements file is in `./src/requirements.txt` and the output zip file will be written to `./dist`. These defaults can be changed with the `--source`, `--requirements` and `--target` options respectively.

The build process will run in a Docker container based on the Amazon Linux image. If there are any additional dependencies that need to be installed on the container prior to installing the Python requirements, those can be given with the `--dependencies` option. Any environment variables recognized by `pip`, such as `PIP_INDEX_URL`, are passed on to the container.

### `fleece run`

```
usage: fleece run [-h] [--username USERNAME] [--apikey APIKEY]
                  [--config CONFIG] [--account ACCOUNT]
                  [--environment ENVIRONMENT] [--role ROLE]
                  command

Run command in environment with AWS credentials from Rackspace FAWS API

positional arguments:
  command               Command to execute

optional arguments:
  -h, --help            show this help message and exit
  --username USERNAME, -u USERNAME
                        Rackspace username. Can also be set via RS_USERNAME
                        environment variable
  --apikey APIKEY, -k APIKEY
                        Rackspace API key. Can also be set via RS_API_KEY
                        environment variable
  --config CONFIG, -c CONFIG
                        Path to YAML config file with defined accounts and
                        aliases. Default is ./environments.yml
  --account ACCOUNT, -a ACCOUNT
                        AWS account number. Cannot be used with
                        `--environment`
  --environment ENVIRONMENT, -e ENVIRONMENT
                        Environment alias to AWS account defined in config
                        file. Cannot be used with `--account`
  --role ROLE, -r ROLE  Role name to assume after obtaining credentials from
                        FAWS API
```

```
# fleece run --username $username --apikey $apikey --account $account 'aws s3 ls'
2017-10-02 12:03:18 bucket1
2017-06-08 14:31:07 bucket2
2017-08-10 17:28:47 bucket3
2017-08-10 17:21:58 bucket4
2017-08-15 20:33:02 bucket5
```

You can also setup an environments file to reduce command-line flags. Ensure accounts are quoted to ensure they are not interperted incorrectly as ints or octals:

```
# cat environments.yml
environments:
  - name: development
    account: '123456789012'
  - name: staging
    account: '123456789012'
    rs_username_var: MY_RS_USERNAME
    rs_apikey_var: MY_RS_APIKEY
  - name: testing
    account: '123456789012'
  - name: production
    account: '123456789012'
    role: LambdaDeployRole

# fleece run --username $username --apikey $apikey --environment testing 'aws s3 ls'
2017-10-02 12:03:18 bucket1
2017-06-08 14:31:07 bucket2
2017-08-10 17:28:47 bucket3
2017-08-10 17:21:58 bucket4
2017-08-15 20:33:02 bucket5
```

Note the `staging` environment example above, which provides a custom pair of
environment variables from where the Rackspace username and API key are sourced.
These would be used only if credentials are not explicitly given as part of
the command.

### `fleece config`

```
usage: fleece config [-h] [--config CONFIG] [--username USERNAME]
                     [--apikey APIKEY] [--environments ENVIRONMENTS]
                     {import,export,edit,render} ...

Configuration management

positional arguments:
  {import,export,edit,render}
                        Sub-command help
    import              Import configuration from stdin
    export              Export configuration to stdout
    edit                Edit configuration
    render              Render configuration for an environment

optional arguments:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
                        Config file (default is config.yml)
  --username USERNAME, -u USERNAME
                        Rackspace username. Can also be set via RS_USERNAME
                        environment variable
  --apikey APIKEY, -k APIKEY
                        Rackspace API key. Can also be set via RS_API_KEY
                        environment variable
  --environments ENVIRONMENTS, -e ENVIRONMENTS
                        Path to YAML config file with defined accounts and
                        environment names. Defaults to ./environments.yml
```

The `fleece config` command has a few sub-commands that work with configuration files. There are a number of arguments that apply to all commands:

- `--config` sets the configuration file. This is the file that holds the configuration, in a format that is appropriate to commit to source control (i.e. sensitive variables are encrypted).
- `--username` and `--apikey` are the Rackspace credentials, used to obtain temporary AWS access credentials from FAWS. For convenience, these can be set in environment variables.
- `--environments` is an environments.yml file that defines the different environments and the associated AWS accounts for each. The format is as described in the `fleece run` command.

The config commands work with two types of config files. The `config.yml` file is a "closed" config file, where all sensitive values are encrypted. Developers typically do not edit this file but instead export it to a temporary "open" configuration file where sensitive variables appear in plain text for editing. As soon as changes are made, the open config file is imported back into the closed `config.yml`.

The open configuration format is as follows:

```
stages:                                 # stage definitions
  prod:                                 # stage name
    environment: prod                   # environment associated with this stage
    key: prod-key-here                  # KMS key, ARN or name with or without the "alias/" prefix are all valid
  /.*/:                                 # regular expressions for custom stage names
    environment: dev
    key: dev-key-here
config:
  foo: bar                              # plain text variable
  password:                             # per-stage values, encrypted
    +dev: :encrypt:my-dev-password      # per-stage keys must have a "+" prefix so they are
    +prod: :encrypt:my-prod-password    # not taken as a nested dict
    +/.*/: :encrypt:my-custom-password
  nested:                               # nested dictionaries
    inner_var: value
    a_list:                             # list of dictionaries
      - username1:                      # per-stage values, without encryption
          +prod: bob-prod
          +/.*/: bob-dev
        password1:                      # per-stage values, encrypted
          +prod: :encrypt:bob-prod-pw
          +/.*/: :encrypt:bob-dev-pw
      - username2: user2
        password2:
          +prod: :encrypt:prod-pw2
          +/.*/: :encrypt:dev-pw2
```

The `stages` section defines the available stages, along with their association to an environment and a KMS key. The environment, which must be defined in the `environments.yml`, links the stage to a AWS account. The KMS key can be given as an ARN or as an alias. The alias can be given with or without the `alias/` prefix. Stage names can be given explicitly or as a regular expression (surrounded by `/`s). When fleece needs to match a stage name given in one of its commands, it will first attempt to do an equality match, and only when that fails it will try the regular expression based stage names. The regular expression stage names are evaluated in random order until one succeeds, so it is important to avoid ambiguities in the regex patterns.

The `config` section is where configuration variables are defined. A standard key/value pair in this section represents a plaintext variable that will be made available for all stages. A variable can be given per-stage values by making its value a sub-dictionary where the keys are the stage names prefixed by `+`. Regex patterns for stage names are supported here as well.

Any variables that are sensitive and need to be encrypted must have per-stage values, and these values must have the `:encrypt:` prefix so that fleece knows to encrypt them when the configuration is imported and stored in `config.yml`.

The available sub-commands are:

#### `fleece config import`

Reads a source configuration file from `stdin` and writes a `config.yml` file. The input data can be in YAML or JSON format.

#### `fleece config export [--json]`

Writes the contents of `config.yml` to `stdout` in the open format for editing. By default this command outputs a YAML file. Use `--json` to output in JSON format.

#### `fleece config edit [--json] [--editor EDITOR]`

This command exports the configuration to a temp file, then starts a text editor (`vi` by default) on this file. After the editor is closed, the modified file is re-imported. This is the most convenient workflow to edit the configuration.

#### `fleece config render [--environment] [--json] [--encrypt] [--python] [--parameter-store PARAMETER_STORE_PREFIX] [--ssm-kms-key SSM_KMS_KEY] <stage>`

Writes the configuration variables for the given environment to stdout or uploads them to parameter store. There are four output options: YAML plaintext (the default), JSON plaintext (with `--json`), JSON encrypted (with `--encrypt`) and an encrypted Python module (with `--python`).

Parameters uploaded into SSM are encrypted by default, using the default SSM encryption key. If you want to use a custom KMS key to encrypt parameters, use the `--ssm-kms-key` option.
For this value, you can pass in a KMS key ID, ARN, alias name, or alias ARN. This feature enables a use case where parameters are copied from SSM into a Lambda Function environment configuration at deploy time, and a custom KMS key is configured for that function to decrypt config at runtime.

The encrypted configuration consists on a list of encrypted buffers that need to be decrypted and appended. The result of this operation is the JSON plaintext configuration. The following output is the output of `--python`, which includes the decrypt and decode logic:

```python
ENCRYPTED_CONFIG = ['... encrypted blob here ...']
import base64
import boto3
import json

def load_config():
    config_json = ''
    kms = boto3.client('kms')
    for buffer in ENCRYPTED_CONFIG:
        r = kms.decrypt(CiphertextBlob=base64.b64decode(buffer.encode(
            'utf-8')))
        config_json += r['Plaintext'].decode('utf-8')
    return json.loads(config_json)

CONFIG = load_config()
```

If this is saved as `fleece_config.py` in the source directory, the configuration can be imported with:

```python
from fleece_config import CONFIG
```

If `--parameter-store` is specified, the next argument needs to be a prefix used for all variables that will be uploaded to parameter store. This should start with a slash.

For example, if the arguments are `--parameter-store /super-service/some-id` and the config has a value called `foo`, then fleece will create or overwrite a secure string parameter store value named `/super-service/some-id/foo` with the value being the decrypted config value of `foo`.

All values are converted to strings before being saved to parameter store. If the config has a nested dictionary, then multiple parameter store values will be saved (so inthe example above, the field `nested` with a value of `inner` would be saved as `/super-service/some-id/nested/inner`).
