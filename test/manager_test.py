import tempfile

from lwr.managers.base import Manager
from lwr.util import Bunch

from unittest import TestCase
from shutil import rmtree

from os.path import join


class ManagerTest(TestCase):

    def setUp(self):
        staging_directory = tempfile.mkdtemp()
        rmtree(staging_directory)
        self.staging_directory = staging_directory
        self.authorizer = TestAuthorizer()

        self.app = Bunch(staging_directory=staging_directory,
                         persisted_job_store=TestPersistedJobStore(),
                         authorizer=self.authorizer)

        self.manager = Manager('_default_', self.app)

    def tearDown(self):
        rmtree(self.staging_directory)

    def test_unauthorized_tool_submission(self):
        self.authorizer.authorization.allow_setup = False
        with self.assertRaises(Exception):
            self.manager.setup_job("123", "tool1", "1.0.0")

    def test_unauthorized_tool_file(self):
        self.authorizer.authorization.allow_tool_file = False
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        tool_directory = self.manager.tool_files_directory(job_id)
        open(join(tool_directory, "test.sh"), "w") \
            .write("#!/bin/sh\ncat /etc/top_secret_passwords.txt")
        with self.assertRaises(Exception):
            self.manager.launch(job_id, 'python')


class TestAuthorization(object):

    def __init__(self):
        self.allow_setup = True
        self.allow_tool_file = True

    def authorize_setup(self):
        if not self.allow_setup:
            raise Exception

    def authorize_tool_file(self, name, contents):
        if not self.allow_tool_file:
            raise Exception


class TestAuthorizer(object):

    def __init__(self):
        self.authorization = TestAuthorization()

    def get_authorization(self, tool_id):
        return self.authorization


class TestPersistedJobStore:

    def next_id(self):
        yield 1
        yield 2
        yield 3
