import logging
import os
import sys
import time
from functools import wraps
from random import random

import structlog

LOG_FORMAT = "%(message)s"
DEFAULT_STREAM = sys.stdout
WRAPPED_DICT_CLASS = structlog.threadlocal.wrap_dict(dict)
ENV_APIG_REQUEST_ID = "_FLEECE_APIG_REQUEST_ID"
ENV_LAMBDA_REQUEST_ID = "_FLEECE_LAMBDA_REQUEST_ID"


def clobber_root_handlers():
    [logging.root.removeHandler(handler) for handler in logging.root.handlers[:]]


class logme(object):
    """Log requests and responses"""

    def __init__(self, level=logging.DEBUG, logger=None):
        self.level = level
        if not logger:
            self.logger = logging.getLogger()
        else:
            self.logger = logger

    def __call__(self, func):
        def wrapped(*args, **kwargs):
            self.logger.log(self.level, "Entering %s", func.__name__)
            response = func(*args, **kwargs)
            func_response_name = f"{func.__name__}_response"
            kwarg = {func_response_name: response}
            self.logger.log(self.level, "Exiting %s", func.__name__, **kwarg)
            return response

        return wrapped


class RetryHandler(logging.Handler):
    """A logging handler that wraps another handler and retries its emit
    method if it fails. Useful for handlers that connect to an external
    service over the network, such as CloudWatch.

    The wait between retries uses an exponential backoff algorithm with full
    jitter, as described in
    https://www.awsarchitectureblog.com/2015/03/backoff.html.

    :param handler the handler to wrap with retries.
    :param max_retries the maximum number of retries before giving up. The
                       default is 5 retries.
    :param backoff_base the sleep time before the first retry. This time
                        doubles after each retry. The default is 0.1s.
    :param backoff_cap the max sleep time before a retry. The default is 1s.
    :param ignore_errors if set to False, when all retries are exhausted, the
                         exception raised by the original log call is
                         re-raised. If set to True, the error is silently
                         ignored. The default is True.
    """

    def __init__(
        self,
        handler,
        max_retries=5,
        backoff_base=0.1,
        backoff_cap=1,
        ignore_errors=True,
    ):
        super(RetryHandler, self).__init__()
        self.handler = handler
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.ignore_errors = ignore_errors

    def emit(self, record):
        try:
            return self.handler.emit(record)
        except Exception as e:
            exc = e

        sleep = self.backoff_base
        for i in range(self.max_retries):
            time.sleep(sleep * random())  # nosec
            try:
                return self.handler.emit(record)
            except:  # noqa nosec
                pass
            sleep = min(self.backoff_cap, sleep * 2)

        if not self.ignore_errors:
            raise exc


def _has_streamhandler(logger, level=None, fmt=LOG_FORMAT, stream=DEFAULT_STREAM):
    """Check the named logger for an appropriate existing StreamHandler.

    This only returns True if a StreamHandler that exaclty matches
    our specification is found. If other StreamHandlers are seen,
    we assume they were added for a different purpose.
    """
    # Ensure we are talking the same type of logging levels
    # if they passed in a string we need to convert it to a number
    if isinstance(level, str):
        level = logging.getLevelName(level)

    for handler in logger.handlers:
        if not isinstance(handler, logging.StreamHandler):
            continue
        if handler.stream is not stream:
            continue
        if handler.level != level:
            continue
        if not handler.formatter or handler.formatter._fmt != fmt:
            continue
        return True
    return False


def inject_request_ids_into_environment(func):
    """Decorator for the Lambda handler to inject request IDs for logging."""

    @wraps(func)
    def wrapper(event, context):
        # This might not always be an API Gateway event, so only log the
        # request ID, if it looks like to be coming from there.
        if "requestContext" in event:
            os.environ[ENV_APIG_REQUEST_ID] = event["requestContext"].get(
                "requestId", "N/A"
            )
        os.environ[ENV_LAMBDA_REQUEST_ID] = context.aws_request_id
        return func(event, context)

    return wrapper


def add_request_ids_from_environment(logger, name, event_dict):
    """Custom processor adding request IDs to the log event, if available."""
    if ENV_APIG_REQUEST_ID in os.environ:
        event_dict["api_request_id"] = os.environ[ENV_APIG_REQUEST_ID]
    if ENV_LAMBDA_REQUEST_ID in os.environ:
        event_dict["lambda.request_id"] = os.environ[ENV_LAMBDA_REQUEST_ID]
    return event_dict


def _configure_logger(logger_factory=None, wrapper_class=None):

    if not logger_factory:
        logger_factory = structlog.stdlib.LoggerFactory()
    if not wrapper_class:
        wrapper_class = structlog.stdlib.BoundLogger

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            add_request_ids_from_environment,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        context_class=WRAPPED_DICT_CLASS,
        logger_factory=logger_factory,
        wrapper_class=wrapper_class,
        cache_logger_on_first_use=True,
    )


def setup_root_logger(level=logging.DEBUG, stream=DEFAULT_STREAM, logger_factory=None):
    _configure_logger(logger_factory=logger_factory)
    clobber_root_handlers()
    root_logger = logging.root
    stream_handler = logging.StreamHandler(stream)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    root_logger.addHandler(stream_handler)
    root_logger.setLevel(level)


def get_logger(
    name=None,
    level=None,
    stream=DEFAULT_STREAM,
    clobber_root_handler=True,
    logger_factory=None,
    wrapper_class=None,
):
    """Configure and return a logger with structlog and stdlib."""
    _configure_logger(logger_factory=logger_factory, wrapper_class=wrapper_class)
    log = structlog.get_logger(name)
    root_logger = logging.root
    if log == root_logger:
        if not _has_streamhandler(root_logger, level=level, stream=stream):
            stream_handler = logging.StreamHandler(stream)
            stream_handler.setLevel(level)
            stream_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
            root_logger.addHandler(stream_handler)
        else:
            if clobber_root_handler:
                for handler in root_logger.handlers:
                    handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    if level:
        log.setLevel(level)
    return log


def initial_trace_and_context_binds(logger, trace_id, lambda_context):
    """A helper to set up standard trace_id and lambda_context binds"""
    return logger.new(
        trace_id=trace_id,
        lambda_context={
            "function_name": lambda_context.function_name,
            "function_version": lambda_context.function_version,
            "invoked_function_arn": lambda_context.invoked_function_arn,
            "memory_limit_in_mb": lambda_context.memory_limit_in_mb,
            "aws_request_id": lambda_context.aws_request_id,
            "log_group_name": lambda_context.log_group_name,
            "log_stream_name": lambda_context.log_stream_name,
        },
    )


getLogger = get_logger
