import collections
import os
import subprocess
import yaml

from six.moves import configparser

from pulsar.scripts.config import main

from test_utils import temp_directory


def test_default_web_config():
    with temp_directory() as project_dir:
        main(["--directory", project_dir])
        project = _check_project_directory(project_dir)
        assert project.ini_config is not None

        local_env = os.path.join(project_dir, "local_env.sh")
        assert os.path.exists(local_env)
        exit_code = subprocess.check_call(['/bin/bash', '-c', '. %s' % local_env])
        assert exit_code == 0


def test_mq_config():
    with temp_directory() as project_dir:
        main(["--directory", project_dir, "--mq"])
        project = _check_project_directory(project_dir)
        assert project.ini_config is None
        assert "message_queue_url" in project.app_config


def test_with_supervisor():
    with temp_directory() as project_dir:
        main(["--directory", project_dir, "--supervisor"])
        project = _check_project_directory(project_dir)
        assert project.ini_config is not None

        supervisor_conf = os.path.join(project_dir, "supervisor.conf")
        assert os.path.exists(supervisor_conf)


def test_libdrmaa_config():
    with temp_directory() as project_dir:
        main(["--directory", project_dir, "--libdrmaa_path", "/path/to/test/libdrmaa.so"])

        local_env = os.path.join(project_dir, "local_env.sh")
        assert os.path.exists(local_env)
        exit_code = subprocess.check_call(['/bin/bash', '-c', '. %s' % local_env])
        assert exit_code == 0


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
        app_config = yaml.load(open(app_config_path, "r"))
        assert isinstance(app_config, dict) or (app_config is None)

    ini_config = None
    ini_path = path_if_exists("server.ini")
    if ini_path:
        ini_config = configparser.ConfigParser()
        ini_config.read([ini_path])

    return Project(ini_config, app_config)

Project = collections.namedtuple('Project', ['ini_config', 'app_config'])
