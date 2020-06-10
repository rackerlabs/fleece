import copy
import datetime
import random
import uuid

from fleece.events import format_event


class LambdaContext(object):
    """
    A python class to simulate the context class passed in when a lambda is
    invoked.

    Most functionality can be overridden with a simple sublass.
    Ex:  get_remaining_time_in_millis() simply returns a static value.
     This could be overridden to help test time boxed functions.
    """

    def __init__(
        self,
        function_name="test_function",
        function_version=1,
        remaining_time_in_milli=9999,
        memory_limit_in_mb=256,
        region="us-east-1",
        account_id="999999999999",
        stage="test_stage",
        aws_request_id=None,
        client_context=None,
    ):
        """

        :param function_name: Name of the given function
        :param function_version: version of the function
        :param remaining_time_in_milli: default value tp return for
        get_remaining_time_in_millis
        :param memory_limit_in_mb: Amount of ram the lambda has access to
        :param region: Which region the lambda is executing in
        :param account_id: The account id the lambda is running in
        :param stage: Which "stage" the lambda is running in
        :param aws_request_id: Defaults to a random UUID
        :param client_context: Defaults to None
        """

        # Setup Default values not exposed directly
        self._region = region
        self._account_id = account_id
        self._stage = stage
        self._remaining_time_in_milli = remaining_time_in_milli

        # Set Basic fields
        self.memory_limit_in_mb = memory_limit_in_mb
        self.function_name = function_name
        self.function_version = function_version

        # Use formatters to create appropriate values
        if aws_request_id is None:
            self.aws_request_id = self._generate_aws_request_id()
        else:
            self.aws_request_id = aws_request_id

        if client_context is None:
            self.client_context = self._generate_client_context()

        self.invoked_function_arn = self._generate_function_arn()
        self.log_group_name = self._generate_log_group_name()
        self.log_stream_name = self._generate_log_stream_name()

    def get_remaining_time_in_millis(self):
        return self._remaining_time_in_milli

    def _generate_log_group_name(self):
        return f"/aws/lambda/{self.function_name}"

    def _generate_log_stream_name(self):
        year = datetime.datetime.year
        month = datetime.datetime.month
        day = datetime.datetime.day
        iterator = str(random.randint(1, 999))  # nosec
        random_id = str(uuid.uuid4()).replace("-", "")
        return f"{year}/{month}/{day}/[{iterator}]/{random_id}"

    def _generate_aws_request_id(self):
        return str(uuid.uuid4())

    def _generate_client_context(self):
        return {}

    def _generate_function_arn(self):
        region = self._region
        account_id = self._account_id
        function_name = self.function_name
        stage = self._stage
        return f"arn:aws:lambda:{region}:{account_id}:function:{function_name}:{stage}"  # noqa


class LambdaEvent(object):
    """
    A class the help generating events passed to lambda functions

    After an object has been created use generate() to create events

    To override and of the default values simply pass in a dictionary for the
    appropriate keyword and it will be merged.

    EX:
    event.generate(gateway={"http-method": "post"},
                   header={"x-auth-token": "SOME VALUE"})

    """

    body = {}
    gateway = {
        "http-method": "GET",
        "request-id": str(uuid.uuid4()),
        "resource-path": "/bogus/path/",
        "stage": "test_stage",
        "stage-data": {},
    }
    header = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "CloudFront-Forwarded-Proto": "https",
        "CloudFront-Is-Desktop-Viewer": "true",
        "CloudFront-Is-Mobile-Viewer": "false",
        "CloudFront-Is-SmartTV-Viewer": "false",
        "CloudFront-Is-Tablet-Viewer": "false",
        "CloudFront-Viewer-Country": "US",
        "Host": "BOGUS.execute-api.us-east-1.amazonaws.com",
        "User-Agent": "python-requests/2.9.1",
        "Via": "1.1 BOGUS.cloudfront.net (CloudFront)",
        "X-Amz-Cf-Id": "FAKE_TID",
        "X-Forwarded-For": "127.0.0.1",
        "X-Forwarded-Port": "443",
        "X-Forwarded-Proto": "https",
        "x-auth-token": "FAKE_TOKEN",
    }
    operation = "test:operation"
    path = {}
    querystring = {}
    requestor = {
        "account-id": "",
        "api-key": "",
        "caller": "",
        "source-ip": "127.0.0.1",
        "user": "",
        "user-agent": "python-requests/2.9.1",
        "user-arn": "",
    }
    merge_dicts = True

    def __init__(
        self,
        body=None,
        gateway=None,
        header=None,
        operation=None,
        path=None,
        querystring=None,
        requestor=None,
    ):

        self.body = body or LambdaEvent.body
        self.gateway = gateway or LambdaEvent.gateway
        self.header = header or LambdaEvent.header
        self.operation = operation or LambdaEvent.operation
        self.path = path or LambdaEvent.path
        self.querystring = querystring or LambdaEvent.querystring
        self.requestor = requestor or LambdaEvent.requestor

    def _generate_body(self, merge, kwargs):
        return dict_update(self.body or LambdaEvent.body, merge, kwargs)

    def _generate_gateway(self, merge, kwargs):
        return dict_update(self.gateway or LambdaEvent.gateway, merge, kwargs)

    def _generate_header(self, merge, kwargs):
        return dict_update(self.header or LambdaEvent.header, merge, kwargs)

    def _generate_operation(self, operation=None):
        if operation is not None:
            return operation
        if self.operation is not None:
            return self.operation
        return LambdaEvent.operation

    def _generate_path(self, merge, kwargs):
        return dict_update(self.path or LambdaEvent.path, merge, kwargs)

    def _generate_querystring(self, merge, kwargs):
        return dict_update(self.querystring or LambdaEvent.querystring, merge, kwargs)

    def _generate_requestor(self, merge, kwargs):
        return dict_update(self.querystring or LambdaEvent.requestor, merge, kwargs)

    def generate(self, merge_with_default=True, **kwargs):

        body = self._generate_body(merge_with_default, kwargs.get("body", {}))
        gateway = self._generate_gateway(merge_with_default, kwargs.get("gateway", {}))
        header = self._generate_header(merge_with_default, kwargs.get("header", {}))
        operation = self._generate_operation(kwargs.get("operation", None))
        path = self._generate_path(merge_with_default, kwargs.get("path", {}))
        querystring = self._generate_querystring(
            merge_with_default, kwargs.get("querystring", {})
        )
        requestor = self._generate_requestor(
            merge_with_default, kwargs.get("requestor", {})
        )

        event = {
            "operation": operation,
            "parameters": {
                "requestor": requestor,
                "request": {
                    "body": body,
                    "path": path,
                    "querystring": querystring,
                    "header": header,
                },
                "gateway": gateway,
            },
        }

        return copy.deepcopy(event)


class LambdaRequestGenerator(object):
    """
    This class takes a given context and event and simplifies a generating a
    request. This allows for deeper more targeted testing of code without
    having to jump through the full set of routers. Most higher level functions
    should be able to take a request and proceed as expected.

    And kwargs pass to generate_request will be handed off to the event
    generator.

    This allows you to set up sane defaults for your app and replace only the
    bits you want to test on the fly.
    """

    def __init__(self, event=None, context=None):
        self.event = event or LambdaEvent()
        self.context = context or LambdaContext()

    def generate_request(self, **kwargs):
        request = format_event(
            event=self.event.generate(**kwargs), context=self.context
        )
        return request


def dict_update(base, merge, kwargs):
    if not merge:
        return kwargs

    response = base.copy()
    response.update(kwargs)
    return response
