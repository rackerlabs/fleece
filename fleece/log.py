import logging
import sys

import structlog

LOG_FORMAT = '%(message)s'
DEFAULT_STREAM = sys.stdout
WRAPPED_DICT_CLASS = structlog.threadlocal.wrap_dict(dict)


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
            self.logger.log(self.level, "Exiting %s", func.__name__,
                            response=response)
            return response

        return wrapped


def _has_streamhandler(logger, level=None, fmt=LOG_FORMAT,
                       stream=DEFAULT_STREAM):
    """Check the named logger for an appropriate existing StreamHandler.

    This only returns True if a StreamHandler that exaclty matches
    our specification is found. If other StreamHandlers are seen,
    we assume they were added for a different purpose.
    """
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


def _configure_logger():

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
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True)


def get_logger(level=logging.DEBUG, name=None, stream=DEFAULT_STREAM,
               clobber_root_handler=True):
    """Configure and return a logger with structlog and stdlib."""
    _configure_logger()
    log = structlog.get_logger(name)
    root_logger = logging.getLogger()
    if clobber_root_handler:
        for handler in root_logger.handlers:
            handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))

    if not _has_streamhandler(logging.getLogger(name),
                              level=level, stream=stream):
        streamhandler = logging.StreamHandler(stream)
        streamhandler.setLevel(level)
        streamhandler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
        log.addHandler(streamhandler)

    log.setLevel(level)
    return log


getLogger = get_logger
