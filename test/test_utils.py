from os import pardir
from os.path import join, dirname

from unittest import TestCase
from tempfile import mkdtemp
from shutil import rmtree

from contextlib import contextmanager

from lwr.tools import ToolBox
from lwr.util import JobDirectory


class TempDirectoryTestCase(TestCase):

    def setUp(self):
        self.temp_directory = mkdtemp()

    def tearDown(self):
        rmtree(self.temp_directory)


def get_test_toolbox():
    toolbox_path = join(dirname(__file__), pardir, "test_data", "test_shed_toolbox.xml")
    toolbox = ToolBox(toolbox_path)
    return toolbox


class TestManager(object):

    def setup_temp_directory(self):
        self.temp_directory = mkdtemp()
        self.job_directory = JobDirectory(self.temp_directory, '1')

    def cleanup_temp_directory(self):
        rmtree(self.temp_directory)

    def outputs_directory(self, job_id):
        return self.job_directory.outputs_directory()


@contextmanager
def test_job_directory():
    temp_directory = mkdtemp()
    job_directory = JobDirectory(temp_directory, '1')
    yield job_directory
    rmtree(temp_directory)


@contextmanager
def test_manager():
    manager = TestManager()
    manager.setup_temp_directory()
    yield manager
    manager.cleanup_temp_directory()


class TestAuthorization(object):

    def __init__(self):
        self.allow_setup = True
        self.allow_tool_file = True
        self.allow_execution = True
        self.allow_config = True

    def authorize_setup(self):
        if not self.allow_setup:
            raise Exception

    def authorize_tool_file(self, name, contents):
        if not self.allow_tool_file:
            raise Exception

    def authorize_execution(self, job_directory, command_line):
        if not self.allow_execution:
            raise Exception

    def authorize_config_file(self, job_directory, name, path):
        if not self.allow_config:
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
