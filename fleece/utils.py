import re
import sys


def _fullmatch(pattern, text, *args, **kwargs):
    """re.fullmatch is not available on Python<3.4."""
    match = re.match(pattern, text, *args, **kwargs)
    return match if match.group(0) == text else None


if sys.version_info >= (3, 4):
    # just use the built-in re.fullmatch
    fullmatch = re.fullmatch
else:
    fullmatch = _fullmatch
