import logging
import sys

import structlog

LOG_FORMAT = '%(message)s'
DEFAULT_STREAM = sys.stdout
WRAPPED_DICT_CLASS = structlog.threadlocal.wrap_dict(dict)


def clobber_root_handlers():
    [logging.root.removeHandler(handler) for handler in
     logging.root.handlers[:]]


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
            func_response_name = "{0}_response".format(func.__name__)
            kwarg = {func_response_name: response}
            self.logger.log(self.level, "Exiting %s", func.__name__, **kwarg)
            return response

        return wrapped


def _has_streamhandler(logger, level=None, fmt=LOG_FORMAT,
                       stream=DEFAULT_STREAM):
    """Check the named logger for an appropriate existing StreamHandler.

    This only returns True if a StreamHandler that exaclty matches
    our specification is found. If other StreamHandlers are seen,
    we assume they were added for a different purpose.
    """
    # Ensure we are talking the same type of logging levels
    # if they passed in a string we need to convert it to a number
    if isinstance(level, basestring):
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


def _configure_logger(logger_factory=None):

    if not logger_factory:
        logger_factory = structlog.stdlib.LoggerFactory()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt='iso'),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(sort_keys=True)
        ],
        context_class=WRAPPED_DICT_CLASS,
        logger_factory=logger_factory,
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True)


def setup_root_logger(level=logging.DEBUG, stream=DEFAULT_STREAM,
                      logger_factory=None):
    _configure_logger(logger_factory=logger_factory)
    clobber_root_handlers()
    root_logger = logging.root
    stream_handler = logging.StreamHandler(stream)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    root_logger.addHandler(stream_handler)


def get_logger(name=None, level=None, stream=DEFAULT_STREAM,
               clobber_root_handler=True, logger_factory=None):
    """Configure and return a logger with structlog and stdlib."""
    _configure_logger(logger_factory=logger_factory)
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


getLogger = get_logger
