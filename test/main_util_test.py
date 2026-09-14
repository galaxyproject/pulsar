""" Test utilities in pulsar.main """
from argparse import ArgumentParser
from os.path import join

import pytest

from pulsar import main
from .test_utils import temp_directory


def test_pulsar_config_builder_defaults():
    with temp_directory() as mock_root:
        __write_mock_ini(join(mock_root, "server.ini"))
        config = main.PulsarConfigBuilder(config_dir=mock_root)
        assert config.load()["foo"] == "bar1"


def test_pulsar_config_builder_defaults_sample():
    with temp_directory() as mock_root:
        __write_mock_ini(join(mock_root, "server.ini.sample"))
        config = main.PulsarConfigBuilder(config_dir=mock_root)
        assert config.load()["foo"] == "bar1"


def test_pulsar_config_builder_specified_ini():
    with temp_directory() as mock_root:
        __write_mock_ini(join(mock_root, "moo.ini"))
        config = main.PulsarConfigBuilder(config_dir=mock_root, ini_path="moo.ini")
        assert config.load()["foo"] == "bar1"


def test_pulsar_config_builder_specified_ini_args():
    with temp_directory() as mock_root:
        __write_mock_ini(join(mock_root, "moo.ini"), app="cool1")
        config = main.PulsarConfigBuilder(config_dir=mock_root, args=MockArgs("moo.ini", "cool1"))
        assert config.load()["foo"] == "bar1"


def test_pulsar_config_builder_specified_app():
    with temp_directory() as mock_root:
        __write_mock_ini(join(mock_root, "server.ini"), app="cool1")
        config = main.PulsarConfigBuilder(config_dir=mock_root, app="cool1")
        assert config.load()["foo"] == "bar1"


def test_pulsar_config_builder_app_yaml():
    with temp_directory() as mock_root:
        __write_mock_ini(join(mock_root, "server.ini"))
        open(join(mock_root, "app.yml"), "w").write("foo: bar2")
        config = main.PulsarConfigBuilder(config_dir=mock_root)
        assert config.load()["foo"] == "bar2"


def test_pulsar_config_builder_override_app_yaml():
    with temp_directory() as mock_root:
        app_yaml_path = join(mock_root, "new_app.yml")
        __write_mock_ini(join(mock_root, "server.ini"), extra="app_config=%s" % app_yaml_path)
        open(app_yaml_path, "w").write("foo: bar2")
        config = main.PulsarConfigBuilder(config_dir=mock_root)
        assert config.load()["foo"] == "bar2"


def test_pulsar_manager_config_builder_defaults():
    with temp_directory() as mock_root:
        __write_mock_ini(join(mock_root, "server.ini"))
        config = main.PulsarManagerConfigBuilder(config_dir=mock_root)
        config.load()["foo"] == "bar1"
        as_dict = config.to_dict()
        assert as_dict["manager"] == "_default_"
        assert as_dict["ini_path"] == join(mock_root, "server.ini")
        assert as_dict["app"] == "main"


def test_pulsar_manager_config_builder_overrides():
    with temp_directory() as mock_root:
        __write_mock_ini(join(mock_root, "pulsar5.ini"), app="cool1")
        config = main.PulsarManagerConfigBuilder(config_dir=mock_root, app="cool1", ini_path="pulsar5.ini", manager="manager3")
        config.load()["foo"] == "bar1"
        as_dict = config.to_dict()
        assert as_dict["manager"] == "manager3"
        assert as_dict["ini_path"] == join(mock_root, "pulsar5.ini")
        assert as_dict["app"] == "cool1"


def test_daemon_argument_aliases():
    for daemon_flag in ["-d", "--daemon", "--daemonize"]:
        args = _parse_main_args([daemon_flag])
        assert args.daemonize

    args = _parse_main_args([
        "--daemon",
        "--log-file", "custom.log",
        "--pid", "custom.pid",
    ])
    assert args.daemon_log_file == "custom.log"
    assert args.pid_file == "custom.pid"

    legacy_args = _parse_main_args([
        "--daemonize",
        "--daemon-log-file", "legacy.log",
        "--pid-file", "legacy.pid",
    ])
    assert legacy_args.daemon_log_file == "legacy.log"
    assert legacy_args.pid_file == "legacy.pid"


def test_stop_daemon_uses_shared_helper(monkeypatch):
    stopped = []
    monkeypatch.setattr(main, "stop_daemon", lambda pid_file: stopped.append(pid_file) or 0)
    monkeypatch.setattr(main, "app_loop", lambda *args: pytest.fail("app should not start"))

    assert main.main(["--stop-daemon", "--pid", "custom.pid"]) == 0
    assert stopped == ["custom.pid"]


def test_daemon_defaults_to_pulsar_log(monkeypatch, tmp_path):
    daemon_options = {}

    class MockDaemonize:

        def __init__(self, **kwds):
            daemon_options.update(kwds)

        def start(self):
            daemon_options["started"] = True

    original_handlers = list(main.log.handlers)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "Daemonize", MockDaemonize)
    try:
        main.main(["--daemon"])
    finally:
        for handler in set(main.log.handlers) - set(original_handlers):
            main.log.removeHandler(handler)
            handler.close()

    assert daemon_options["started"]
    assert len(daemon_options["keep_fds"]) == 1
    assert (tmp_path / "pulsar.log").exists()


def test_daemon_app_loop_redirects_output(monkeypatch):
    dup2_calls = []
    app_loop_calls = []
    monkeypatch.setattr(main.os, "dup2", lambda source, target: dup2_calls.append((source, target)))
    monkeypatch.setattr(main, "app_loop", lambda *args: app_loop_calls.append(args))

    main._daemon_app_loop("args", "log", True, 42)

    assert dup2_calls == [
        (42, main.sys.stdout.fileno()),
        (42, main.sys.stderr.fileno()),
    ]
    assert app_loop_calls == [("args", "log", True)]


def test_missing_daemon_dependency_has_install_hint(monkeypatch, capsys):
    monkeypatch.setattr(main, "Daemonize", None)

    with pytest.raises(SystemExit) as exc_info:
        main.main(["--daemon"])

    assert exc_info.value.code == 2
    assert "pip install 'pulsar-app[daemon]'" in capsys.readouterr().err


class MockArgs:

    def __init__(self, ini_path, app):
        self.ini_path = ini_path
        self.app_conf_path = None
        self.app_conf_base64 = None
        self.app = app


def _parse_main_args(argv):
    parser = ArgumentParser()
    main.PulsarConfigBuilder.populate_options(parser)
    return parser.parse_args(argv)


def __write_mock_ini(path, **kwds):
    contents = __mock_ini_contents(**kwds)
    open(path, "w").write(contents)


def __mock_ini_contents(app="main", extra=""):
    return """
[app:{}]
foo=bar1
{}
""".format(app, extra)
