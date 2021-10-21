""" Test utilities in pulsar.main """
from os.path import join
from .test_utils import temp_directory
from pulsar import main


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


class MockArgs:

    def __init__(self, ini_path, app):
        self.ini_path = ini_path
        self.app_conf_path = None
        self.app_conf_base64 = None
        self.app = app


def __write_mock_ini(path, **kwds):
    contents = __mock_ini_contents(**kwds)
    open(path, "w").write(contents)


def __mock_ini_contents(app="main", extra=""):
    return """
[app:{}]
paste.app_factory = pulsar.web.wsgi:app_factory
foo=bar1
{}
""".format(app, extra)
