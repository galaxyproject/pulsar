"""Utilities allowing for high-level testing throughout Pulsar."""

import os
import configparser
import sys
import threading
import traceback
from contextlib import contextmanager
from stat import S_IXGRP, S_IXOTH
from os import pardir, stat, chmod, access, X_OK, pathsep, environ
from os import makedirs, listdir, system
from os.path import join, dirname, isfile, split
from pathlib import Path
from tempfile import mkdtemp
from shutil import rmtree
from typing import (
    Any,
    Dict,
    Optional,
)

import time

import pytest
from webtest import TestApp
from webtest.http import StopableWSGIServer

from galaxy.job_metrics import NULL_JOB_INSTRUMENTER
from galaxy.util.bunch import Bunch
from simplejobfiles.app import JobFilesApp

from pulsar.managers.util import drmaa
from pulsar.tools import ToolBox
from pulsar.managers.base import JobDirectory
from pulsar.user_auth.manager import UserAuthManager

from unittest import TestCase, skip

import stopit
from functools import wraps


class MarkGenerator:
    def __getattr__(self, name):
        return getattr(pytest.mark, name)


mark = MarkGenerator()


def timed(timeout):
    def outer_wrapper(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            with stopit.ThreadingTimeout(timeout) as to_ctx_mgr:
                f(*args, **kwargs)
            if to_ctx_mgr.state != to_ctx_mgr.EXECUTED:
                raise Exception("Test function timed out.")

        return wrapper

    return outer_wrapper


INTEGRATION_MAXIMUM_TEST_TIME = 120
integration_test = timed(INTEGRATION_MAXIMUM_TEST_TIME)

TEST_DIR = dirname(__file__)
ROOT_DIR = join(TEST_DIR, pardir)
TEST_TEMPDIR_PREFIX = 'tmp_pulsar_'


class TempDirectoryTestCase(TestCase):

    def setUp(self):
        self.temp_directory = temp_directory_persist(prefix=TEST_TEMPDIR_PREFIX)

    def tearDown(self):
        rmtree(self.temp_directory)


def get_test_toolbox():
    toolbox_path = join(dirname(__file__), pardir, "test_data", "test_shed_toolbox.xml")
    toolbox = ToolBox(toolbox_path)
    return toolbox


def get_test_tool():
    return get_test_toolbox().get_tool("tool1")


class TestManager:

    def setup_temp_directory(self):
        self.temp_directory = temp_directory_persist(prefix='test_manager_')
        self.__job_directory = JobDirectory(self.temp_directory, '1')

    def cleanup_temp_directory(self):
        rmtree(self.temp_directory)

    def job_directory(self, job_id):
        return self.__job_directory


@contextmanager
def temp_job_directory():
    with temp_directory(prefix='job_') as directory:
        yield JobDirectory(directory, '1')


@contextmanager
def temp_directory(prefix=''):
    directory = temp_directory_persist(prefix=prefix)
    try:
        yield directory
    finally:
        rmtree(directory)


def temp_directory_persist(prefix=''):
    return mkdtemp(prefix=TEST_TEMPDIR_PREFIX + prefix)


@contextmanager
def get_test_manager():
    manager = TestManager()
    manager.setup_temp_directory()
    yield manager
    manager.cleanup_temp_directory()


class TestAuthorization:

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


class TestDependencyManager:

    def dependency_shell_commands(self, requirements, **kwds):
        return []


class BaseManagerTestCase(TestCase):

    def setUp(self):
        self.app = minimal_app_for_managers()
        self.staging_directory = self.app.staging_directory
        self.authorizer = self.app.authorizer
        self.user_auth_manager = self.app.user_auth_manager

    def tearDown(self):
        rmtree(self.staging_directory)

    def _test_simple_execution(self, manager, timeout=None):
        command = """
python -c "import sys; sys.stdout.write(\'Hello World!\'); sys.stdout.flush(); sys.stderr.write(\'moo\'); sys.stderr.flush()" \
2> ../metadata/tool_stderr > ../metadata/tool_stdout"""
        job_id = manager.setup_job("123", "tool1", "1.0.0")
        manager.launch(job_id, command)

        time_end = None if timeout is None else time.time() + timeout
        while manager.get_status(job_id) not in ['complete', 'cancelled']:
            if time_end and time.time() > time_end:
                raise Exception("Timeout.")
        self.assertEqual(manager.job_stderr_contents(job_id), b"")
        self.assertEqual(manager.job_stdout_contents(job_id), b"")
        self.assertEqual(manager.stderr_contents(job_id), b"moo")
        self.assertEqual(manager.stdout_contents(job_id), b"Hello World!")
        self.assertEqual(manager.return_code(job_id), 0)
        manager.clean(job_id)
        self.assertEqual(len(listdir(self.staging_directory)), 0)

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
    staging_directory = temp_directory_persist(prefix='minimal_app_')
    rmtree(staging_directory)
    authorizer = TestAuthorizer()
    user_auth_manager = get_test_user_auth_manager()
    return Bunch(staging_directory=staging_directory,
                 authorizer=authorizer,
                 job_metrics=NullJobMetrics(),
                 dependency_manager=TestDependencyManager(),
                 user_auth_manager=user_auth_manager,
                 object_store=object())


def get_test_user_auth_manager():
    config = {"user_auth": {"authentication": [{"type": "allow_all"}], "authorization": [{"type": "allow_all"}]}}
    return UserAuthManager(config)


def get_failing_user_auth_manager():
    config = {"user_auth": {"authentication": [{"type": "allow_all"}],
                            "authorization": [{"type": "userlist", "userlist_allowed_users": []}]}}
    return UserAuthManager(config)


class NullJobMetrics:

    def __init__(self):
        self.default_job_instrumenter = NULL_JOB_INSTRUMENTER


@contextmanager
def server_for_test_app(test_app):
    app = test_app.app
    create_kwds = {
    }
    if os.environ.get("PULSAR_TEST_FILE_SERVER_HOST"):
        create_kwds["host"] = os.environ.get("PULSAR_TEST_FILE_SERVER_HOST")
    server = StopableWSGIServer.create(app, **create_kwds)
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


@contextmanager
def test_pulsar_server(global_conf={}, app_conf={}, test_conf={}):
    with test_pulsar_app(global_conf, app_conf, test_conf) as app:
        with server_for_test_app(app) as test_pulsar_server:
            yield test_pulsar_server


test_pulsar_server.__test__ = False  # type:ignore[attr-defined]


class RestartablePulsarAppProvider:

    def __init__(self, global_conf={}, app_conf={}, test_conf={}, web=True):
        self.staging_directory = temp_directory_persist(prefix='staging_')
        self.global_conf = global_conf
        self.app_conf = app_conf
        self.test_conf = test_conf
        self.web = web

    @contextmanager
    def new_app(self):
        with test_pulsar_app(
                self.global_conf,
                self.app_conf,
                self.test_conf,
                staging_directory=self.staging_directory,
                web=self.web,
        ) as app:
            yield app

    def cleanup(self):
        try:
            rmtree(self.staging_directory)
        except Exception:
            pass


@contextmanager
def restartable_pulsar_app_provider(**kwds):
    try:
        has_app = RestartablePulsarAppProvider(**kwds)
        yield has_app
    finally:
        has_app.cleanup()


@contextmanager
def test_pulsar_app(
        global_conf={},
        app_conf={},
        test_conf={},
        staging_directory=None,
        web=True,
):
    clean_staging_directory = False
    if staging_directory is None:
        staging_directory = temp_directory_persist(prefix='staging_')
        clean_staging_directory = True
    # Make staging directory world executable for run as user tests.
    mode = stat(staging_directory).st_mode
    chmod(staging_directory, mode | S_IXGRP | S_IXOTH)
    cache_directory = temp_directory_persist(prefix='cache_')
    app_conf["staging_directory"] = staging_directory
    app_conf["file_cache_dir"] = cache_directory
    app_conf["ensure_cleanup"] = True
    app_conf["conda_auto_init"] = app_conf.get("conda_auto_init", False)
    app_conf["conda_auto_install"] = app_conf.get("conda_auto_install", False)
    try:
        with _yield_app(global_conf, app_conf, test_conf, web) as app:
            yield app
    finally:
        to_clean = [cache_directory]
        if clean_staging_directory:
            to_clean.append(staging_directory)

        for directory in to_clean:
            try:
                rmtree(directory)
                pass
            except Exception:
                pass


test_pulsar_app.__test__ = False  # type:ignore[attr-defined]


@contextmanager
def _yield_app(global_conf, app_conf, test_conf, web):
    # Yield either wsgi webapp of the underlying pulsar
    # app object if the web layer is not needed.
    try:
        if web:
            from pulsar.web.wsgi import app_factory
            app = app_factory(global_conf, **app_conf)
            yield TestApp(app, **test_conf)
        else:
            from pulsar.main import load_app_configuration
            from pulsar.core import PulsarApp
            app_conf = load_app_configuration(local_conf=app_conf)
            app = PulsarApp(**app_conf)
            yield app
    finally:
        try:
            shutdown_args = []
            if not web:
                shutdown_args.append(2)
            app.shutdown(*shutdown_args)
        except Exception:
            pass


def skip_unless_environ(var):
    if var in environ:
        return lambda func: func
    return skip("Environment variable %s not found, dependent test skipped." % var)


def skip_unless_executable(executable):
    if _which(executable):
        return lambda func: func
    return skip("PATH doesn't contain executable %s" % executable)


def skip_unless_module(module):
    available = True
    try:
        __import__(module)
    except (ImportError, RuntimeError):
        # drmaa raises RuntimeError if DRMAA_LIBRARY_PATH is unset
        available = False
    if available:
        return lambda func: func
    return skip("Module %s could not be loaded, dependent test skipped." % module)


def skip_unless_any_module(modules):
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


def skip_if_none(value):
    if value is not None:
        return lambda func: func
    return skip


def skip_without_drmaa(f):
    return skip_if_none(drmaa.Session)(f)


def _which(program):
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


class TestAuthorizer:

    def __init__(self):
        self.authorization = TestAuthorization()

    def get_authorization(self, tool_id):
        return self.authorization


@contextmanager
def files_server(directory=None):
    external_url = os.environ.get("PULSAR_TEST_EXTERNAL_JOB_FILES_URL")
    if external_url:
        if directory is None:
            directory = os.environ.get("PULSAR_TEST_EXTERNAL_JOB_FILES_DIRECTORY")
            if directory:
                yield Bunch(application_url=external_url), directory
            else:
                with temp_directory() as directory:
                    yield Bunch(application_url=external_url), directory
        else:
            yield Bunch(application_url=external_url)
    else:
        if not directory:
            with temp_directory() as directory:
                app = TestApp(JobFilesApp(directory))
                with server_for_test_app(app) as server:
                    yield server, directory
        else:
            app = TestApp(JobFilesApp(directory))
            with server_for_test_app(app) as server:
                yield server


def dump_other_threads():
    # Utility for debugging threads that aren't dying during
    # tests.
    main_thread = threading.current_thread()
    for t in threading.enumerate():
        if t is main_thread:
            continue

        print(t.getName())
        traceback.print_stack(sys._current_frames()[t.ident])


# Extracted from: https://github.com/python/cpython/blob/
# 937ee9e745d7ff3c2010b927903c0e2a83623324/Lib/test/support/__init__.py
class EnvironmentVarGuard:
    """Class to help protect the environment variable properly.  Can be used as
    a context manager."""

    def __init__(self):
        self._environ = os.environ
        self._changed = {}

    def __getitem__(self, envvar):
        return self._environ[envvar]

    def __setitem__(self, envvar, value):
        # Remember the initial value on the first access
        if envvar not in self._changed:
            self._changed[envvar] = self._environ.get(envvar)
        self._environ[envvar] = value

    def __delitem__(self, envvar):
        # Remember the initial value on the first access
        if envvar not in self._changed:
            self._changed[envvar] = self._environ.get(envvar)
        if envvar in self._environ:
            del self._environ[envvar]

    def keys(self):
        return self._environ.keys()

    def __iter__(self):
        return iter(self._environ)

    def __len__(self):
        return len(self._environ)

    def set(self, envvar, value):
        self[envvar] = value

    def unset(self, envvar):
        del self[envvar]

    def __enter__(self):
        return self

    def __exit__(self, *ignore_exc):
        for (k, v) in self._changed.items():
            if v is None:
                if k in self._environ:
                    del self._environ[k]
            else:
                self._environ[k] = v
        os.environ = self._environ


class IntegrationTestConfiguration:
    _test_suffix: Optional[str]
    _app_conf_dict: Dict[str, Any]
    _test_conf_dict: Dict[str, Any]

    def __init__(self, tmp_path: Path, test_suffix: Optional[str] = None):
        self._app_conf_dict = {}
        self._test_conf_dict = {}
        self._tmp_path = tmp_path
        self.__setup_dependencies()
        self._test_suffix = test_suffix

    def __setup_dependencies(self):
        dependencies_dir = self._tmp_path / "dependencies"
        dep1_directory = dependencies_dir / "dep1" / "1.1"
        makedirs(dep1_directory)
        try:
            # Let external users read/execute this directory for run as user
            # test.
            system("chmod 755 %s" % self._tmp_path)
            system("chmod -R 755 %s" % dependencies_dir)
        except Exception as e:
            print(e)
        env_file = dep1_directory / "env.sh"
        env_file.write_text("MOO=moo_override; export MOO")
        self._app_conf_dict["tool_dependency_dir"] = str(dependencies_dir)

    def write_job_conf_props(self, job_conf_props: Optional[Dict[str, str]]):
        if job_conf_props:
            job_conf_props = job_conf_props.copy()
            job_conf = self._tmp_path / "job_managers.ini"
            config = configparser.ConfigParser()
            section_name = "manager:_default_"
            config.add_section(section_name)
            for key, value in job_conf_props.items():
                config.set(section_name, key, value)
            with open(job_conf, "w") as configf:
                config.write(configf)

            self._app_conf_dict["job_managers_config"] = job_conf

    def set_app_conf_props(self, **kwd):
        self._app_conf_dict.update(**kwd)

    def set_test_conf_props(self, **kwd):
        self._test_conf_dict.update(**kwd)

    @property
    def test_suffix(self) -> str:
        return self._test_suffix or ""
