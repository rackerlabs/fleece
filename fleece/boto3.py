from __future__ import absolute_import

import boto3 as real_boto3
from boto3 import docs  # noqa: F401
from boto3 import exceptions  # noqa: F401
from boto3 import logging  # noqa: F401
from boto3 import resources  # noqa: F401
from boto3 import session  # noqa: F401
from boto3 import set_stream_logger  # noqa: F401
from boto3 import setup_default_session  # noqa: F401
from botocore.client import Config

DEFAULT_TIMEOUT = None
DEFAULT_CONNECT_TIMEOUT = None
DEFAULT_READ_TIMEOUT = None


def set_default_timeout(timeout=None, connect_timeout=None, read_timeout=None):
    """
    The purpose of this function is to install default socket timeouts that
    different than those used by boto3 and botocore. Clients obtained from the
    `fleece.boto3.client()` function will have these timeouts set, unless
    explicitly overriden.

    The default timeouts set through this option apply to the entire process.
    For that reason, it is recommended that this function is only called once
    during startup, and from the main thread, before any other threads are
    spawned.

    Socket timeouts are automatically retried by boto, according to its own
    retry policies.

    :param timeout timeout for socket connections and reads in seconds. This is
                   a convenience argument that applies the same default to both
                   connection and read timeouts.
    :param connect_timeout timeout for socket connections in seconds.
    :param read_timeout timeout for socket reads in seconds.
    """
    global DEFAULT_TIMEOUT
    global DEFAULT_CONNECT_TIMEOUT
    global DEFAULT_READ_TIMEOUT
    DEFAULT_TIMEOUT = timeout
    DEFAULT_CONNECT_TIMEOUT = connect_timeout
    DEFAULT_READ_TIMEOUT = read_timeout


def client(*args, **kwargs):
    """
    Create a low-level service client by name using the default session.
    Socket level timeouts are preconfigured according to the defaults set via
    the `fleece.boto3.set_default_timeout()` function, or they can also be set
    explicitly for a client by passing the `timeout`, `connect_timeout` or
    `read_timeout` arguments.
    """
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    connect_timeout = kwargs.pop("connect_timeout", DEFAULT_CONNECT_TIMEOUT or timeout)
    read_timeout = kwargs.pop("read_timeout", DEFAULT_READ_TIMEOUT or timeout)

    config = Config(connect_timeout=connect_timeout, read_timeout=read_timeout)
    return real_boto3.client(*args, config=config, **kwargs)


def resource(*args, **kwargs):
    """
    Create a resource service client by name using the default session.
    Socket level timeouts are preconfigured according to the defaults set via
    the `fleece.boto3.set_default_timeout()` function, or they can also be set
    explicitly for a client by passing the `timeout`, `connect_timeout` or
    `read_timeout` arguments.
    """
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    connect_timeout = kwargs.pop("connect_timeout", DEFAULT_CONNECT_TIMEOUT or timeout)
    read_timeout = kwargs.pop("read_timeout", DEFAULT_READ_TIMEOUT or timeout)

    config = Config(connect_timeout=connect_timeout, read_timeout=read_timeout)
    return real_boto3.resource(*args, config=config, **kwargs)
