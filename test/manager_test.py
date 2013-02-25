import tempfile
from time import sleep

from lwr.managers.base import Manager
from lwr.util import Bunch

from unittest import TestCase
from shutil import rmtree

from os import listdir
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

    def test_unauthorized_command_line(self):
        self.authorizer.authorization.allow_execution = False
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        with self.assertRaises(Exception):
            self.manager.launch(job_id, 'python')

    def test_simple_execution(self):
        manager = self.manager
        command = """python -c "import sys; sys.stdout.write(\'Hello World!\'); sys.stderr.write(\'moo\')" """
        job_id = manager.setup_job("123", "tool1", "1.0.0")
        manager.launch(job_id, command)
        while not manager.check_complete(job_id):
            pass
        self.assertEquals(manager.stderr_contents(job_id), 'moo')
        self.assertEquals(manager.stdout_contents(job_id), 'Hello World!')
        self.assertEquals(manager.return_code(job_id), 0)
        manager.clean_job_directory(job_id)
        self.assertEquals(len(listdir(self.staging_directory)), 0)

    def test_kill(self):
        manager = self.manager
        job_id = manager.setup_job("124", "tool1", "1.0.0")
        command = """python -c "import time; time.sleep(10000)" """
        manager.launch(job_id, command)
        sleep(0.1)
        manager.kill(job_id)
        manager.kill(job_id)  # Make sure kill doesn't choke if pid doesn't exist
        while not manager.check_complete(job_id):
            pass
        manager.clean_job_directory(job_id)


class TestAuthorization(object):

    def __init__(self):
        self.allow_setup = True
        self.allow_tool_file = True
        self.allow_execution = True

    def authorize_setup(self):
        if not self.allow_setup:
            raise Exception

    def authorize_tool_file(self, name, contents):
        if not self.allow_tool_file:
            raise Exception

    def authorize_execution(self, command_line):
        if not self.allow_execution:
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
