from __future__ import absolute_import

import datetime

from requests.structures import CaseInsensitiveDict


class Hasher(dict):
    # http://stackoverflow.com/a/3405143/190597
    def __missing__(self, key):
        value = self[key] = type(self)()
        return value


def format_event(event, context):
    output_context = {
        'aws_request_id': context.aws_request_id,
        'client_context': context.client_context,
        'function_name': context.function_name,
        'function_version': context.function_version,
        'get_remaining_time_in_millis': context.get_remaining_time_in_millis(),
        'invoked_function_arn': context.invoked_function_arn,
        'log_group_name': context.log_group_name,
        'log_stream_name': context.log_stream_name,
        'memory_limit_in_mb': context.memory_limit_in_mb,
    }

    hashed_event = Hasher(event)

    request = {
        'requested-at': datetime.datetime.utcnow().isoformat(),
        'context': output_context,
        'operation': hashed_event['operation'],
        'requestor': hashed_event['parameters']['requestor'],
        'body': hashed_event['parameters']['request']['body'],
        'path': hashed_event['parameters']['request']['path'],
        'querystring': hashed_event['parameters']['request']['querystring'],
        'header': CaseInsensitiveDict(
            hashed_event['parameters']['request']['header']),
        'gateway': hashed_event['parameters']['gateway'],
    }

    return request
