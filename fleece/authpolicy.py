# Based on https://github.com/awslabs/aws-apigateway-lambda-authorizer-blueprints/blob/master/blueprints/python/api-gateway-authorizer-python.py  # noqa
import re


class HttpVerb:
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    HEAD = "HEAD"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    ALL = "*"


class AuthPolicy(object):
    def __init__(
        self,
        aws_account_id,
        principal=None,
        context=None,
        rest_api_id=None,
        region=None,
        stage=None,
    ):
        # AWS account ID policy will be generated for
        self.aws_account_id = aws_account_id
        # Principal used for policy, unique ID for end user
        self.principal_id = principal or ""
        # Policy version should always be '2012-10-17'
        self.version = "2012-10-17"
        # Used to validate resource paths for policy
        self.path_regex = r'^[/.a-zA-Z0-9-_\*\:]+$'
        # Lists of allowed/denied methods, objects with resource ARN and
        # nullable conditions statement
        self.allowMethods = []
        self.denyMethods = []
        # The API Gateway API id. By default this is set to '*'
        self.rest_api_id = rest_api_id or "*"
        # The region where the API is deployed. Default is '*'
        self.region = region or "*"
        # The name of the stage used in the policy. Default is '*'
        self.stage = stage or "*"
        # Optional context
        self.context = context or {}

    def _add_method(self, effect, verb, resource, conditions):
        """
        Adds a method to the internal lists of allowed or denied methods.
        Each object in the internal list contains a resource ARN and a
        condition statement. The condition statement can be null.
        """
        if verb != "*" and not hasattr(HttpVerb, verb):
            raise NameError(
                "Invalid HTTP verb " + verb + ". Allowed verbs in HttpVerb class"
            )
        resource_pattern = re.compile(self.path_regex)
        if not resource_pattern.match(resource):
            raise NameError(
                "Invalid resource path: "
                + resource
                + ". Path should match "
                + self.path_regex
            )

        if resource[:1] == "/":
            resource = resource[1:]

        resource_arn = (
            "arn:aws:execute-api:"
            + self.region
            + ":"
            + self.aws_account_id
            + ":"
            + self.rest_api_id
            + "/"
            + self.stage
            + "/"
            + verb
            + "/"
            + resource
        )

        if effect.lower() == "allow":
            self.allowMethods.append(
                {"resource_arn": resource_arn, "conditions": conditions}
            )
        elif effect.lower() == "deny":
            self.denyMethods.append(
                {"resource_arn": resource_arn, "conditions": conditions}
            )

    def _get_empty_statement(self, effect):
        """
        Returns an empty statement object prepopulated with the
        correct action and the desired effect.
        """
        statement = {
            "Action": "execute-api:Invoke",
            "Effect": effect[:1].upper() + effect[1:].lower(),
            "Resource": [],
        }

        return statement

    def _get_effect_statement(self, effect, methods):
        """
        This function loops over an array of objects containing
        a resourceArn and conditions statement and generates
        the array of statements for the policy.
        """
        statements = []

        if len(methods) > 0:
            statement = self._get_empty_statement(effect)

            for method in methods:
                if method["conditions"] is None or len(method["conditions"]) == 0:
                    statement["Resource"].append(method["resource_arn"])
                else:
                    cond_statement = self._get_empty_statement(effect)
                    cond_statement["Resource"].append(method["resource_arn"])
                    cond_statement["Condition"] = method["conditions"]
                    statements.append(cond_statement)
            statements.append(statement)

        return statements

    def allow_all_methods(self):
        """Adds a '*' allow to authorize access to all methods of an API"""
        self._add_method("Allow", HttpVerb.ALL, "*", [])

    def deny_all_methods(self):
        """Adds a '*' allow to deny access to all methods of an API"""
        self._add_method("Deny", HttpVerb.ALL, "*", [])

    def allow_method(self, verb, resource):
        """
        Adds an API Gateway method (Http verb + Resource path)
        to the list of allowed methods for the policy
        """
        self._add_method("Allow", verb, resource, [])

    def deny_method(self, verb, resource):
        """
        Adds an API Gateway method (Http verb + Resource path)
        to the list of denied methods for the policy
        """
        self._add_method("Deny", verb, resource, [])

    def allow_method_with_conditions(self, verb, resource, conditions):
        """
        Adds an API Gateway method (Http verb + Resource path) to the
        list of allowed methods and includes a condition for the policy
        statement. More on AWS policy conditions here:
        http://docs.aws.amazon.com/IAM/latest/UserGuide/
        reference_policies_elements.html#Condition
        """
        self._add_method("Allow", verb, resource, conditions)

    def deny_method_with_conditions(self, verb, resource, conditions):
        """
        Adds an API Gateway method (Http verb + Resource path) to the
        list of denied methods and includes a condition for the policy
        statement. More on AWS policy conditions here:
        http://docs.aws.amazon.com/IAM/latest/UserGuide/
        reference_policies_elements.html#Condition
        """
        self._add_method("Deny", verb, resource, conditions)

    def build(self):
        """
        Generates the policy document based on the internal lists of
        allowed and denied conditions. This will generate a policy with
        two main statements for the effect: one statement for Allow and
        one statement for Deny. Methods that includes conditions will
        have their own statement in the policy.
        """
        if (self.allowMethods is None or len(self.allowMethods) == 0) and (
            self.denyMethods is None or len(self.denyMethods) == 0
        ):
            raise NameError("No statements defined for the policy")

        policy = {
            "principalId": self.principal_id,
            "policyDocument": {"Version": self.version, "Statement": []},
            "context": self.context,
        }

        policy["policyDocument"]["Statement"].extend(
            self._get_effect_statement("Allow", self.allowMethods)
        )
        policy["policyDocument"]["Statement"].extend(
            self._get_effect_statement("Deny", self.denyMethods)
        )

        return policy
