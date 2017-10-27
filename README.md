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

You can also setup an environments file to reduce command-line flags:

```
# cat environments.yml
environments:
  - name: development
    account: '123456789012'
  - name: staging
    account: '123456789012'
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
