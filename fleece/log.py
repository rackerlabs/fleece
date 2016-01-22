import logging

import structlog


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
            self.logger.log(self.level, "Entering %s" % func.__name__)
            response = func(*args, **kwargs)
            self.logger.log(self.level,
                            "Exiting %s" % func.__name__,
                            response=response)
            return response
        return wrapped


def get_logger(level=logging.DEBUG, name=None):
    WrappedDictClass = structlog.threadlocal.wrap_dict(dict)
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
        context_class=WrappedDictClass,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True)
    log = structlog.get_logger(name)
    log.setLevel(level)
    return log
