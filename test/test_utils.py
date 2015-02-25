from contextlib import contextmanager
from stat import S_IXOTH
from os import pardir, stat, chmod, access, X_OK, pathsep, environ
from os import makedirs, listdir
from os.path import join, dirname, isfile, split
from os.path import exists
from tempfile import mkdtemp
from shutil import rmtree
import time

from sys import version_info
import webob
from webtest import TestApp
from webtest.http import StopableWSGIServer

import galaxy.util
from galaxy.util.bunch import Bunch
from galaxy.jobs.metrics import NULL_JOB_INSTRUMENTER

from pulsar.tools import ToolBox
from pulsar.managers.base import JobDirectory
from pulsar.web.framework import file_response

if version_info < (2, 7):
    from unittest2 import TestCase, skip
else:
    from unittest import TestCase, skip

try:
    from nose.tools import nottest
except ImportError:
    def nottest(x):
        return x


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


def get_test_tool():
    return get_test_toolbox().get_tool("tool1")


class TestManager(object):

    def setup_temp_directory(self):
        self.temp_directory = mkdtemp()
        self.__job_directory = JobDirectory(self.temp_directory, '1')

    def cleanup_temp_directory(self):
        rmtree(self.temp_directory)

    def job_directory(self, job_id):
        return self.__job_directory


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


class TestDependencyManager(object):

    def dependency_shell_commands(self, requirements, **kwds):
        return []


class BaseManagerTestCase(TestCase):

    def setUp(self):
        self.app = minimal_app_for_managers()
        self.staging_directory = self.app.staging_directory
        self.authorizer = self.app.authorizer

    def tearDown(self):
        rmtree(self.staging_directory)

    @nottest
    def _test_simple_execution(self, manager):
        command = """python -c "import sys; sys.stdout.write(\'Hello World!\'); sys.stderr.write(\'moo\')" """
        job_id = manager.setup_job("123", "tool1", "1.0.0")
        manager.launch(job_id, command)
        while manager.get_status(job_id) not in ['complete', 'cancelled']:
            pass
        self.assertEquals(manager.stderr_contents(job_id), 'moo')
        self.assertEquals(manager.stdout_contents(job_id), 'Hello World!')
        self.assertEquals(manager.return_code(job_id), 0)
        manager.clean(job_id)
        self.assertEquals(len(listdir(self.staging_directory)), 0)

    def _test_cancelling(self, manager):
        job_id = manager.setup_job("124", "tool1", "1.0.0")
        command = self._python_to_command("import time; time.sleep(1000)")
        manager.launch(job_id, command)
        time.sleep(0.05)
        manager.kill(job_id)
        manager.kill(job_id)  # Make sure kill doesn't choke if pid doesn't exist
        self._assert_status_becomes_cancelled(job_id, manager)
        manager.clean(job_id)

    def _python_to_command(self, code, quote='"'):
        assert '"' not in code
        return 'python -c "%s"' % "; ".join(code.split("\n"))

    def _assert_status_becomes_cancelled(self, job_id, manager):
        i = 0
        while True:
            i += 1
            status = manager.get_status(job_id)
            if status in ["complete", "failed"]:
                raise AssertionError("Expected cancelled status but got %s." % status)
            elif status == "cancelled":
                break
            time.sleep(0.01)
            if i > 100:  # Wait one second
                raise AssertionError("Job failed to cancel quickly.")


def minimal_app_for_managers():
    """ Minimimal app description for consumption by managers.
    """
    staging_directory = mkdtemp()
    rmtree(staging_directory)
    authorizer = TestAuthorizer()
    return Bunch(staging_directory=staging_directory,
                 authorizer=authorizer,
                 job_metrics=NullJobMetrics(),
                 dependency_manager=TestDependencyManager())


class NullJobMetrics(object):

    def __init__(self):
        self.default_job_instrumenter = NULL_JOB_INSTRUMENTER


@nottest
@contextmanager
def server_for_test_app(app):
    try:
        from paste.exceptions.errormiddleware import ErrorMiddleware
        error_app = ErrorMiddleware(app.app, debug=True, error_log="errors.log")
    except ImportError:
        # paste.exceptions not available for Python 3.
        error_app = app
    server = StopableWSGIServer.create(error_app)
    try:
        server.wait()
        yield server
    finally:
        server.shutdown()
    # There seem to be persistent transient problems with the testing, sleeping
    # between creation of test app instances for greater than .5 seconds seems
    # to help (async loop length in code is .5 so this maybe makes some sense?)
    if "TEST_WEBAPP_POST_SHUTDOWN_SLEEP" in environ:
        time.sleep(int(environ.get("TEST_WEBAPP_POST_SHUTDOWN_SLEEP")))


@nottest
@contextmanager
def test_pulsar_server(global_conf={}, app_conf={}, test_conf={}):
    with test_pulsar_app(global_conf, app_conf, test_conf) as app:
        with server_for_test_app(app) as test_pulsar_server:
            yield test_pulsar_server


@nottest
@contextmanager
def test_pulsar_app(global_conf={}, app_conf={}, test_conf={}):
    staging_directory = mkdtemp()
    # Make staging directory world executable for run as user tests.
    mode = stat(staging_directory).st_mode
    chmod(staging_directory, mode | S_IXOTH)
    cache_directory = mkdtemp()
    try:
        app_conf["staging_directory"] = staging_directory
        app_conf["file_cache_dir"] = cache_directory
        from pulsar.web.wsgi import app_factory

        app = app_factory(global_conf, **app_conf)
        yield TestApp(app, **test_conf)
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


def skipUnlessAnyModule(modules):
    available = False
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            continue
        available = True
    if available:
        return lambda func: func
    return skip("None of the modules %s could be loaded, dependent test skipped." % modules)


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


class JobFilesApp(object):

    def __init__(self, root_directory=None):
        self.root_directory = root_directory

    def __call__(self, environ, start_response):
        req = webob.Request(environ)
        params = req.params.mixed()
        method = req.method
        if method == "POST":
            resp = self._post(req, params)
        elif method == "GET":
            resp = self._get(req, params)
        else:
            raise Exception("Unhandled request method %s" % method)
        return resp(environ, start_response)

    def _post(self, request, params):
        path = params['path']
        if not galaxy.util.in_directory(path, self.root_directory):
            assert False, "%s not in %s" % (path, self.root_directory)
        parent_directory = dirname(path)
        if not exists(parent_directory):
            makedirs(parent_directory)
        galaxy.util.copy_to_path(params["file"].file, path)
        return webob.Response(body='')

    def _get(self, request, params):
        path = params['path']
        if not galaxy.util.in_directory(path, self.root_directory):
            assert False, "%s not in %s" % (path, self.root_directory)
        return file_response(path)


@contextmanager
def files_server(directory=None):
    if not directory:
        with temp_directory() as directory:
            app = TestApp(JobFilesApp(directory))
            with server_for_test_app(app) as server:
                yield server, directory
    else:
        app = TestApp(JobFilesApp(directory))
        with server_for_test_app(app) as server:
            yield server
