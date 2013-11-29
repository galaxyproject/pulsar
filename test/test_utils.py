from contextlib import contextmanager
from stat import S_IXOTH
from os import pardir, stat, chmod, access, X_OK, pathsep, environ
from os.path import join, dirname, isfile, split
from tempfile import mkdtemp
from shutil import rmtree

from sys import version_info
if version_info < (2, 7):
    from unittest2 import TestCase, skip
else:
    from unittest import TestCase, skip

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
    with temp_directory() as directory:
        yield JobDirectory(directory, '1')


@contextmanager
def temp_directory():
    directory = mkdtemp()
    try:
        yield directory
    finally:
        rmtree(directory)


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
        try:
            from paste.exceptions.errormiddleware import ErrorMiddleware
            error_app = ErrorMiddleware(app.app, debug=True, error_log="errors")
        except ImportError:
            # paste.exceptions not available for Python 3.
            error_app = app
        server = StopableWSGIServer.create(error_app)
        try:
            server.wait()
            yield server
        finally:
            server.shutdown()


@contextmanager
def test_app(global_conf={}, app_conf={}, test_conf={}):
    staging_directory = mkdtemp()
    # Make staging directory world executable for run as user tests.
    mode = stat(staging_directory).st_mode
    chmod(staging_directory, mode | S_IXOTH)
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
                pass
            except:
                pass


def skipUnlessExecutable(executable):
    if __which(executable):
        return lambda func: func
    return skip("PATH doesn't contain executable %s" % executable)


def skipUnlessModule(module):
    available = True
    try:
        __import__(module)
    except ImportError:
        available = False
    if available:
        return lambda func: func
    return skip("Module %s could not be loaded, dependent test skipped." % module)


def __which(program):

    def is_exe(fpath):
        return isfile(fpath) and access(fpath, X_OK)

    fpath, fname = split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in environ["PATH"].split(pathsep):
            path = path.strip('"')
            exe_file = join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


class TestAuthorizer(object):

    def __init__(self):
        self.authorization = TestAuthorization()

    def get_authorization(self, tool_id):
        return self.authorization
