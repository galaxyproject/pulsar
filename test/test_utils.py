from contextlib import contextmanager
from os import pardir
from os.path import join, dirname
from tempfile import mkdtemp
from shutil import rmtree

from sys import version_info
if version_info < (2, 7):
    from unittest2 import TestCase
else:
    from unittest import TestCase

from webtest import TestApp
from webtest.http import StopableWSGIServer

from lwr.tools import ToolBox
from lwr.util import JobDirectory

TEST_DIR = dirname(__file__)
ROOT_DIR = join(TEST_DIR, pardir)


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


@contextmanager
def test_server(global_conf={}, app_conf={}, test_conf={}):
    with test_app(global_conf, app_conf, test_conf) as app:
        from paste.exceptions.errormiddleware import ErrorMiddleware
        error_app = ErrorMiddleware(app.app, debug=True, error_log="errors")
        server = StopableWSGIServer.create(error_app)
        try:
            server.wait()
            yield server
        finally:
            server.shutdown()


@contextmanager
def test_app(global_conf={}, app_conf={}, test_conf={}):
    staging_directory = mkdtemp()
    cache_directory = mkdtemp()
    try:
        app_conf["staging_directory"] = staging_directory
        app_conf["file_cache_dir"] = cache_directory
        from lwr.app import app_factory

        app = app_factory(global_conf, **app_conf)
        test_app = TestApp(app, **test_conf)
        yield test_app
    finally:
        try:
            app.shutdown()
        except:
            pass
        for directory in [staging_directory, cache_directory]:
            try:
                rmtree(directory)
            except:
                pass


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
