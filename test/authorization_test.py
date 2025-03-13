from pulsar.tools.authorization import get_authorizer
from .test_utils import get_test_toolbox, TestCase


def test_allow_any_authorization():
    authorizer = get_authorizer(None)
    authorization = authorizer.get_authorization('tool1')
    authorization.authorize_setup()
    authorization.authorize_tool_file('cow', '#!/bin/bash\necho "Hello World!"')


class ToolBasedAuthorizationTestCase(TestCase):

    def setUp(self):
        self.toolbox = get_test_toolbox()
        self.authorizer = get_authorizer(self.toolbox)

    def test_valid_setup_passes(self):
        self.authorizer.get_authorization('tool1').authorize_setup()

    def test_invalid_setup_fails(self):
        with self.unauthorized_expectation():
            self.authorizer.get_authorization('tool2').authorize_setup()

    def test_valid_tool_file_passes(self):
        authorization = self.authorizer.get_authorization('tool1')
        authorization.authorize_tool_file('tool1_wrapper.py', b'print \'Hello World!\'\n')

    def test_invalid_tool_file_fails(self):
        authorization = self.authorizer.get_authorization('tool1')
        with self.unauthorized_expectation():
            authorization.authorize_tool_file('tool1_wrapper.py', '#!/bin/sh\nrm -rf /valuable/data')

    def unauthorized_expectation(self):
        return self.assertRaises(Exception)
