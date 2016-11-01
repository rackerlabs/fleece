# Fleece

## Logging

To start using fleece with a lambda project you will need to make 2 small
updates to your project.

* Where you would normally import `logging.get_logger` or `logging.getLogger`
use`fleece.log.get_logger` or `fleece.log.getLogger`


* In the file with your primary lambda handler include
`fleece.log.setup_root_logger()`prior to setting up any additional logging.

This should ensure that all handlers on the root logger are cleaned up and one
with appropriate stream handlers is in place.

### Retry logging calls

A retry wrapper for logging handlers that occasionally fail is also provided.
This wrapper can be useful in preventing crashes when logging calls to external
services such as CloudWatch fail.

For example, consider the following handler for CloudWatch using watchtower:

```python
logger.addHandler(
    watchtower.CloudWatchLogHandler(log_group='WORKER-POLL',
                                    stream_name=str(uuid.uuid4()),
                                    use_queues=False))
```

If the CloudWatch service is down, or rate limits the client, that will cause
logging calls to raise an exception, which may interrupt the script. To avoid
that, the watchtower handler can be wrapped in a `RetryHandler` as follows:

```python
logger.addHandler(
    fleece.log.RetryHandler(
        watchtower.CloudWatchLogHandler(log_group='WORKER-POLL',
                                        stream_name=str(uuid.uuid4()),
                                        use_queues=False)))
```

In the above example, logging calls that fail will be retried up to 5 times,
using an exponential backoff algorithm to increasingly space out retries. If
all retries fail, then the logging call will, by default, give up silently and
return, allowing the program to continue. See the documentation for the
`RetryHandler` class for information on how to customize the retry strategy.

## boto3 wrappers

This project includes `fleece.boto3.client()` and `fleece.boto3.resource()`
wrappers that support a friendly format for setting less conservative timeouts
than the default 60 seconds used by boto. The following additional arguments
are accepted to set these timeouts:

- `connect_timeout`: timeout for socket connections in seconds.
- `read_timeout`: timeout for socket read operations in seconds.
- `timeout`: convenience timeout that sets both of the above to the same value.

Also for convenience, timeouts can be set globally by calling
`fleece.boto3.set_default_timeout()` at startup. Globally set timeouts are
then applied to all clients, unless explicitly overriden. Default timeouts set
via the `set_default_timeout()` function apply to all threads, and for that
reason it is a good idea to only call this function during start up, before
any additional threads are spawn.

As an example, the following code written against the original boto3 package
uses the default 60 second socket timeouts:

    import boto3
    # ...
    lambda = boto3.client('lambda')

If you wanted to use 15 second timeouts instead, you can simply switch to the
fleece wrappers as follows:

    from fleece import boto3
    boto3.set_default_timeout(15)
    # ...
    lambda = boto3.client('lambda')

## requests wrappers

This project also includes a wrapper for the requests package. When using
`fleece.requests`, convenient access to set timeouts and retries is provided.

The high-level request functions such as `requests.get()` and
`requests.post()` accept the following arguments:

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

The `Session` class is also wrapped. A session instance from this module also
accepts the two arguments above, and passes them on to any requests it issues.

Finally, it is also possible to install global timeout and retry defaults that
are used for any requests that don't specify them explicitly. This enables
existing code to take advantage of retries and timeouts after changing the
imports to point to this wrapped version of requests. Below is an example that
sets global timeouts and retries:

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
