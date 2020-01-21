import json
import unittest

from fleece import authpolicy


class AuthpolicyTests(unittest.TestCase):
    """Tests for :class: `fleece.authpolicy.AuthPolicy`."""

    def setUp(self):
        self.aws_account_id = "000000000000"
        self.resource_base_path = ("arn:aws:execute-api:*:{}:myapi/"
                                   "mystage").format(self.aws_account_id)

    @staticmethod
    def generate_policy(effect, resources, condition=None):
        policy_template = {
            "principalId": "foo",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": effect,
                        "Resource": resources,
                    }
                ],
            },
            "context": {},
        }

        if condition:
            policy_template["policyDocument"]["Statement"][0][
                "Condition"] = condition

        return policy_template

    @staticmethod
    def validate_policies(policy1, policy2):
        assert json.dumps(policy1, sort_keys=True) == json.dumps(
            policy2, sort_keys=True)

    def test_allow_all(self):
        expected_policy = self.generate_policy(
            "Allow",
            [self.resource_base_path + "/*/*"]
        )
        policy = authpolicy.AuthPolicy(self.aws_account_id, principal="foo",
                                       rest_api_id="myapi", stage="mystage")
        policy.allow_all_methods()
        self.validate_policies(expected_policy, policy.build())

    def test_deny_all(self):
        expected_policy = self.generate_policy(
            "Deny",
            [self.resource_base_path + "/*/*"]
        )
        policy = authpolicy.AuthPolicy(self.aws_account_id, principal="foo",
                                       rest_api_id="myapi", stage="mystage")
        policy.deny_all_methods()
        self.validate_policies(expected_policy, policy.build())

    def test_allow_method(self):
        expected_policy = self.generate_policy(
            "Allow",
            [self.resource_base_path + "/GET/test/path"],
        )
        policy = authpolicy.AuthPolicy(self.aws_account_id, principal="foo",
                                       rest_api_id="myapi", stage="mystage")
        policy.allow_method("GET", "/test/path")
        self.validate_policies(expected_policy, policy.build())

    def test_allow_method_with_conditions(self):
        condition = {"DateLessThan": {"aws:CurrentTime": "foo"}}
        expected_policy = self.generate_policy(
            "Allow",
            [self.resource_base_path + "/GET/test/path"],
            condition=condition,
        )
        # NOTE(ryandub): I think there is a bug with conditions in the
        # upstream source this is based on that appends an extra statement.
        # Need to investigate this more and fix if necessary.
        expected_policy["policyDocument"]["Statement"].append({
            "Action": "execute-api:Invoke",
            "Effect": "Allow",
            "Resource": [],
        })

        policy = authpolicy.AuthPolicy(self.aws_account_id, principal="foo",
                                       rest_api_id="myapi", stage="mystage")
        policy.allow_method_with_conditions("GET", "/test/path", condition)
        self.validate_policies(expected_policy, policy.build())

    def test_deny_method(self):
        expected_policy = self.generate_policy(
            "Deny",
            [self.resource_base_path + "/GET/test/path"]
        )
        policy = authpolicy.AuthPolicy(self.aws_account_id, principal="foo",
                                       rest_api_id="myapi", stage="mystage")
        policy.deny_method("GET", "/test/path")
        self.validate_policies(expected_policy, policy.build())

    def test_deny_method_with_conditions(self):
        condition = {"DateLessThan": {"aws:CurrentTime": "foo"}}
        expected_policy = self.generate_policy(
            "Deny",
            [self.resource_base_path + "/GET/test/path"],
            condition=condition,
        )
        # NOTE(ryandub): I think there is a bug with conditions in the
        # upstream source this is based on that appends an extra statement.
        # Need to investigate this more and fix if necessary.
        expected_policy["policyDocument"]["Statement"].append({
            "Action": "execute-api:Invoke",
            "Effect": "Deny",
            "Resource": [],
        })

        policy = authpolicy.AuthPolicy(self.aws_account_id, principal="foo",
                                       rest_api_id="myapi", stage="mystage")
        policy.deny_method_with_conditions("GET", "/test/path", condition)
        self.validate_policies(expected_policy, policy.build())
