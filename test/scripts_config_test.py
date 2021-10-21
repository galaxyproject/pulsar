import collections
import configparser
import os
import subprocess
import sys
from io import StringIO

import yaml


from pulsar.scripts import config
from pulsar.scripts.config import main
from .test_utils import (
    skip_unless_environ,
    temp_directory,
)


def test_default_web_config():
    with temp_directory() as project_dir:
        main(["--directory", project_dir])
        project = _check_project_directory(project_dir)
        assert project.ini_config is not None

        local_env = os.path.join(project_dir, "local_env.sh")
        assert os.path.exists(local_env)
        exit_code = subprocess.check_call(['/bin/bash', '-c', '. %s' % local_env])
        assert exit_code == 0


def test_private_token():
    with temp_directory() as project_dir:
        main(["--directory", project_dir, "--private_token", "moo"])
        project = _check_project_directory(project_dir)
        assert project.ini_config is not None
        assert "private_token" in project.app_config
        assert project.app_config["private_token"] == "moo"


def test_windows_options_limited():
    help = _get_help(mock_windows=True)
    assert "--libdrmaa_path" not in help


def test_linux_options_full():
    help = _get_help(mock_windows=False)
    assert "--libdrmaa_path" in help


def test_mq_config():
    with temp_directory() as project_dir:
        main(["--directory", project_dir, "--mq"])
        project = _check_project_directory(project_dir)
        assert project.ini_config is None
        assert "message_queue_url" in project.app_config


@skip_unless_environ('USER')
def test_with_supervisor():
    with temp_directory() as project_dir:
        main(["--directory", project_dir, "--supervisor"])
        project = _check_project_directory(project_dir)
        assert project.ini_config is not None

        supervisor_conf = os.path.join(project_dir, "supervisor.conf")
        assert os.path.exists(supervisor_conf)


def test_libdrmaa_config():
    with temp_directory() as project_dir:
        real_pip = config.pip
        config.pip = MockPip()
        try:
            main(["--directory", project_dir, "--libdrmaa_path", "/path/to/test/libdrmaa.so", "--install"])

            local_env = os.path.join(project_dir, "local_env.sh")
            assert os.path.exists(local_env)
            exit_code = subprocess.check_call(['/bin/bash', '-c', '. %s' % local_env])
            assert exit_code == 0

            pip_calls = config.pip.main_calls
            assert len(pip_calls) == 1
            assert pip_calls[0] == (["install", "drmaa"],), pip_calls
        finally:
            config.pip = real_pip


def test_force():
    with temp_directory() as project_dir:
        # Write a default configuration and make sure mq is configured.
        main(["--directory", project_dir])
        project = _check_project_directory(project_dir)
        assert "message_queue_url" not in (project.app_config or {})

        # Try to re-config with message queue, expect error because files
        # already exist.
        exit_code = None
        try:
            main(["--directory", project_dir, "--mq"])
        except SystemExit as e:
            exit_code = e.code
        assert exit_code == 1

        # Try re-config again with --force, expect it to work and for MQ to be
        # configured.
        main(["--directory", project_dir, "--mq", "--force"])
        project = _check_project_directory(project_dir)
        assert "message_queue_url" in project.app_config


def _check_project_directory(project_dir):
    def path_if_exists(name):
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            return path
        else:
            return None

    app_config = None
    app_config_path = path_if_exists("app.yml")
    if app_config_path:
        app_config = yaml.safe_load(open(app_config_path))
        assert isinstance(app_config, dict) or (app_config is None)

    ini_config = None
    ini_path = path_if_exists("server.ini")
    if ini_path:
        ini_config = configparser.ConfigParser()
        ini_config.read([ini_path])

    return Project(ini_config, app_config)


Project = collections.namedtuple('Project', ['ini_config', 'app_config'])


class MockPip:

    def __init__(self):
        self.main_calls = []

    def main(self, *args):
        self.main_calls.append(args)


def _get_help(mock_windows=False):
    is_windows = config.IS_WINDOWS
    backup = sys.stdout
    out = StringIO()
    sys.stdout = out
    try:
        config.IS_WINDOWS = mock_windows
        try:
            main(["--help"])
        except SystemExit:
            pass
    finally:
        config.IS_WINDOWS = is_windows
        sys.stdout = backup

    help = out.getvalue()
    return help
