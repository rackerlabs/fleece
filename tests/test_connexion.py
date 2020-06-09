import os
import tempfile
import unittest

import flask
import six

import fleece.connexion

from unittest import mock

# NOTE(larsbutler): The one thing that is not shown here are the
# x-amazon-apigateway-integration response templates which API Gateway can use
# to raise the appropriate status code. You will notice in the tests below that
# even though the schema specifies return codes, that return code doesn't get
# propagated by `call_api`.
# For more information about the x-amazon-apigateway-integration response
# templates, see
# http://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-swagger-extensions-integration.html.
TEST_SWAGGER = """
swagger: '2.0'
info:
  version: 'v1'
  title: 'myapp'
  description: 'myapp: for testing connexion/fleece integration'
basePath: '/v1'
paths:
  /users/{user_id}:
    get:
      summary: Get a specific user profile
      description: |
        Retrieve the full details of a single user's profile.
      operationId: 'tests.test_connexion.myapp_get_user'
      parameters:
        - name: user_id
          type: integer
          in: path
          required: true
          description: ID of the user to fetch
      responses:
        200:
          description: 'A single user'
          schema:
            $ref: '#/definitions/User'
        404:
          description: 'Not Found'
          schema:
            $ref: '#/definitions/ErrorResponse'
        400:
          description: 'Bad Request'
          schema:
            $ref: '#/definitions/ErrorResponse'
        500:
          description: 'Internal Server Error'
          schema:
            $ref: '#/definitions/ErrorResponse'
  /users:
    post:
      summary: Create a new user
      description: |
        Create a brand new user profile.
        A user_id will be automatically generated for the new user.
      operationId: 'tests.test_connexion.myapp_create_user'
      parameters:
        - name: user
          in: body
          schema:
            $ref: '#/definitions/CreateUserPayload'
      responses:
        201:
          description: 'The newly-created user'
          schema:
            $ref: '#/definitions/User'
        400:
          description: 'Bad Request'
          schema:
            $ref: '#/definitions/ErrorResponse'
        500:
          description: 'Internal Server Error'
          schema:
            $ref: '#/definitions/ErrorResponse'

definitions:
  ErrorResponse:
    description: Error response
    type: object
    required: [error]
    properties:
      error:
        type: object
        required: [code, message]
        properties:
          code:
            type: integer
          message:
            type: string

  User:
    description: A single user
    type: object
    required: [full_name, email, active]
    properties:
      user_id:
        type: integer
        description: ID of the user's account
      full_name:
        type: string
        description: User's full name
      email:
        type: string
        description: User's email address
      active:
        type: boolean
        description: True if the user account is active

  CreateUserPayload:
    description: A single user to be created
    type: object
    required: [full_name, email]
    properties:
      full_name:
        type: string
        description: User's full name
      email:
        type: string
        description: User's email address
"""


def myapp_get_user(user_id):
    response = {}
    headers = {}
    status = 200
    if user_id == 123:
        response = {
            "full_name": "Bob User",
            "email": "bob@example.com",
            "active": False,
            "user_id": 123,
        }
    elif user_id == 456:
        response = {
            "full_name": "Alice User",
            "email": "alice@example.com",
            "active": True,
            "user_id": 456,
        }
    elif user_id == 789:
        response = {
            "full_name": "Carol User",
            "email": "carol@example.com",
            "active": False,
            # This should trigger a 500 error response, since the user_id must
            # be an integer.
            "user_id": "789",
        }
    elif user_id == 404:
        # user not found
        status = 404
        response = {"error": {"message": "user not found", "code": status}}
    elif user_id == 500:
        # A real "internal server error".
        raise TypeError("something unexpected happened")
    return response, status, headers


def myapp_create_user(**kwargs):
    headers = {}
    body = flask.request.get_json()
    body["user_id"] = 777
    body["active"] = True
    status = 201
    return body, status, headers


class TestFleeceApp(unittest.TestCase):
    """Test full execution paths of FleeceApp."""

    def setUp(self):
        self.swagger_path = tempfile.mktemp()
        with open(self.swagger_path, "w") as fp:
            fp.write(TEST_SWAGGER)

        self.logger = mock.Mock()

        self.app = fleece.connexion.get_connexion_app(
            "myapp", self.swagger_path, cache_app=False, logger=self.logger,
        )

    def tearDown(self):
        if os.path.exists(self.swagger_path):
            os.unlink(self.swagger_path)

    def test_get_user_200_response(self):
        event = {
            "parameters": {
                "gateway": {"resource-path": "/v1/users/{user_id}"},
                "request": {
                    "header": {
                        "X-Forwarded-Port": "443",
                        "X-Forwarded-Proto": "https",
                        "Host": "myapp.com",
                    },
                    "body": {},
                    # Variables, as key/value pairs to render into the
                    # resource-path.
                    "path": {"user_id": "123"},
                    "querystring": "",
                },
            },
            "rawContext": {"identity": {"sourceIp": "1.2.3.4"}, "httpMethod": "GET"},
        }
        expected_response = {
            "active": False,
            "email": "bob@example.com",
            "full_name": "Bob User",
            "user_id": 123,
        }
        response = self.app.call_api(event)
        self.assertEqual(expected_response, response)

    def test_get_user_400_response(self):
        event = {
            "parameters": {
                "gateway": {"resource-path": "/v1/users/{user_id}"},
                "request": {
                    "header": {
                        "X-Forwarded-Port": "443",
                        "X-Forwarded-Proto": "https",
                        "Host": "myapp.com",
                    },
                    "body": {},
                    "path": {"user_id": "123"},
                    # Query string variables, as a list of name/value pairs
                    # In this case, the presence of the query string should
                    # trigger a 400 Bad Request.
                    "querystring": [("invalid", "value")],
                },
            },
            "rawContext": {"identity": {"sourceIp": "1.2.3.4"}, "httpMethod": "GET"},
        }
        with self.assertRaises(fleece.httperror.HTTPError) as ar:
            self.app.call_api(event)
        self.assertEqual(400, ar.exception.status_code)
        self.assertEqual(
            "400: Bad Request - Extra query parameter(s) invalid not in spec",
            str(ar.exception),
        )

    def test_get_user_404_response(self):
        event = {
            "parameters": {
                "gateway": {"resource-path": "/v1/users/{user_id}"},
                "request": {
                    "header": {
                        "X-Forwarded-Port": "443",
                        "X-Forwarded-Proto": "https",
                        "Host": "myapp.com",
                    },
                    "body": {},
                    # This will trigger a 404.
                    "path": {"user_id": "404"},
                    "querystring": [],
                },
            },
            "rawContext": {"identity": {"sourceIp": "1.2.3.4"}, "httpMethod": "GET"},
        }
        with self.assertRaises(fleece.httperror.HTTPError) as ar:
            self.app.call_api(event)
        self.assertEqual(404, ar.exception.status_code)
        self.assertEqual("404: Not Found - user not found", str(ar.exception))

    def test_get_user_500_response(self):
        event = {
            "parameters": {
                "gateway": {"resource-path": "/v1/users/{user_id}"},
                "request": {
                    "header": {
                        "X-Forwarded-Port": "443",
                        "X-Forwarded-Proto": "https",
                        "Host": "myapp.com",
                    },
                    "body": {},
                    "path": {"user_id": "500"},
                    "querystring": [],
                },
            },
            "rawContext": {"identity": {"sourceIp": "1.2.3.4"}, "httpMethod": "GET"},
        }
        with self.assertRaises(fleece.httperror.HTTPError) as ar:
            self.app.call_api(event)
        self.assertEqual(500, ar.exception.status_code)
        self.assertEqual("500: Internal Server Error", str(ar.exception))

    def test_get_user_500_response_contract_violation(self):
        event = {
            "parameters": {
                "gateway": {"resource-path": "/v1/users/{user_id}"},
                "request": {
                    "header": {
                        "X-Forwarded-Port": "443",
                        "X-Forwarded-Proto": "https",
                        "Host": "myapp.com",
                    },
                    "body": {},
                    "path": {"user_id": "789"},
                    "querystring": [],
                },
            },
            "rawContext": {"identity": {"sourceIp": "1.2.3.4"}, "httpMethod": "GET"},
        }
        with self.assertRaises(fleece.httperror.HTTPError) as ar:
            self.app.call_api(event)
        self.assertEqual(500, ar.exception.status_code)
        self.assertEqual("500: Internal Server Error", str(ar.exception))

        # Since this error was triggered because of an API contract voilation,
        # check that it is explicitly logged:
        expected_log_error_detail = """\
u'789' is not of type 'integer'

Failed validating 'type' in schema['properties']['user_id']:
    {'description': "ID of the user's account", 'type': 'integer'}

On instance['user_id']:
    u'789'"""
        if six.PY3:
            expected_log_error_detail = expected_log_error_detail.replace("u'", "'")
        self.assertEqual(1, self.logger.error.call_count)
        self.logger.error.assert_called_with(
            fleece.connexion.RESPONSE_CONTRACT_VIOLATION,
            detail=expected_log_error_detail,
        )

    def test_create_user_201_response(self):
        # This test shows how to create an event for a POST.
        event = {
            "parameters": {
                "gateway": {"resource-path": "/v1/users"},
                "request": {
                    "header": {
                        "X-Forwarded-Port": "443",
                        "X-Forwarded-Proto": "https",
                        "Host": "myapp.com",
                    },
                    "body": {"full_name": "Erin User", "email": "erin@example.com"},
                    "path": {},
                    "querystring": [],
                },
            },
            "rawContext": {"identity": {"sourceIp": "1.2.3.4"}, "httpMethod": "POST"},
        }
        response = self.app.call_api(event)
        expected_response = {
            "active": True,
            "user_id": 777,
            "email": "erin@example.com",
            "full_name": "Erin User",
        }
        self.assertEqual(expected_response, response)
