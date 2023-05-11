from unittest import TestCase

from test.test_utils import get_test_user_auth_manager, get_failing_user_auth_manager


class UserAuthorizationTestCase(TestCase):

    def setUp(self):
        self.authorizer = get_test_user_auth_manager()
        self.failing_authorizer = get_failing_user_auth_manager()

    def test_passes(self):
        self.authorizer.authorize("123", None)

    def test_fails(self):
        with self.unauthorized_expectation():
            self.failing_authorizer.authorize("123", None)

    def unauthorized_expectation(self):
        return self.assertRaises(Exception)
