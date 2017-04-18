from cProfile import Profile
try:
    from cStringIO import StringIO
except ImportError:
    # StringIO was moved in Python 3
    from io import StringIO
from functools import wraps
from pstats import Stats
import random
import re

from fleece import log

DEFAULT_LOGGER = log.getLogger('profiler')

RE_SUMMARY_LINE = re.compile(
    r'^\s+(?P<total_calls>\d+) function calls '
    r'\((?P<primitive_calls>\d+) primitive calls\) '
    r'in (?P<total_time>\d+\.\d+) seconds$'
)
RE_PROFILE_LINE = re.compile(
    r'^\s+(?P<ncalls>\d+)\s+'
    r'(?P<tottime>\d+\.\d+)\s+'
    r'(?P<tpercall>\d+\.\d+)\s+'
    r'(?P<cumtime>\d+\.\d+)\s+'
    r'(?P<cpercall>\d+\.\d+)\s+'
    r'(?P<filename>.*):(?P<lineno>\d+)\((?P<function>.*)\)$'
)
# Percentage of calls that should be profiled
PROFILE_SAMPLE = 0.5
# This means that only code that is part of the uploaded Lambda package will
# be present in the profiling report. This will include bundled dependencies,
# but not the standard library, or packages that are provided by Lambda
# (boto*).
DEFAULT_FILTER = ['/var/task/']
DEFAULT_LIMIT = 20


def process_profiling_data(stream, logger, event):
    profiling_data = []
    extra_dict = {}

    raw_string = stream.getvalue()
    lines = raw_string.split('\n')

    # First line contains a summary of the profiled data.
    match_summary = RE_SUMMARY_LINE.match(lines[0])
    if match_summary is not None:
        extra_dict = match_summary.groupdict()
    # In the rest of the data, there might be empty lines, so we have to handle
    # non-matching lines gracefully.
    for line in lines[1:]:
        match = RE_PROFILE_LINE.match(line)
        if match is not None:
            profiling_data.append(match.groupdict())

    logger.info(
        'Profiling completed',
        lambda_event=event,
        profiling_data=profiling_data,
        **extra_dict
    )


def profile_handler(sample=PROFILE_SAMPLE, stats_filter=None,
                    stats_limit=DEFAULT_LIMIT, logger=DEFAULT_LOGGER):

    def decorator(func):

        @wraps(func)
        def wrapper(event, context, *args, **kwargs):
            if random.random() <= PROFILE_SAMPLE:
                print_stats_filter = stats_filter or DEFAULT_FILTER
                print_stats_filter.append(stats_limit)

                profile = Profile()
                profile.enable()
                try:
                    return_value = func(event, context, *args, **kwargs)
                finally:
                    profile.disable()

                    stream = StringIO()
                    stats = Stats(profile, stream=stream)
                    stats.sort_stats('cumulative')
                    stats.print_stats(*print_stats_filter)
                    process_profiling_data(stream, logger, event)
            else:
                logger.info('Skipping profiling')
                return_value = func(event, context, *args, **kwargs)

            return return_value

        return wrapper

    return decorator
