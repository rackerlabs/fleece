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

As an exmaple, the following code written against the original boto3 package
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
