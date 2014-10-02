from contextlib import contextmanager
import os.path

from pulsar import manager_factory

from .test_utils import temp_directory
from .test_utils import minimal_app_for_managers


def test_default():
    # By defualt create single queue python manager with name _default_
    with __test_managers({}) as managers:
        assert len(managers) == 1
        assert "_default_" in managers
        __assert_manager_of_type(managers["_default_"], "queued_python")


def test_ini_populate():
    with temp_directory() as dir:
        config = os.path.join(dir, "job_managers.ini")
        open(config, "w").write("[manager:cool1]\ntype=queued_cli")
        with __test_managers({"job_managers_config": config}) as managers:
            assert len(managers) == 1
            assert "cool1" in managers
            __assert_manager_of_type(managers["cool1"], "queued_cli")


def test_yaml_populate_manager():
    conf = {
        'manager': {'type': 'queued_cli'}
    }
    with __test_managers(conf) as managers:
        assert len(managers) == 1
        assert "_default_" in managers
        __assert_manager_of_type(managers["_default_"], "queued_cli")


def test_yaml_populate_managers():
    conf = {
        'managers': {
            'man1': {'type': 'queued_cli'},
            'man2': {'type': 'queued_python'}
        },
    }

    with __test_managers(conf) as managers:
        assert len(managers) == 2
        assert "man1" in managers
        __assert_manager_of_type(managers["man1"], "queued_cli")
        __assert_manager_of_type(managers["man2"], "queued_python")


def __assert_manager_of_type(manager, expected_type):
    # Not a great test - break stateful abstraction and is testing
    # implementation details instead of behavior.
    actual = manager._proxied_manager.manager_type
    assert actual == expected_type


@contextmanager
def __test_managers(conf):
    app = minimal_app_for_managers()
    managers = manager_factory.build_managers(app, conf)
    try:
        yield managers
    finally:
        for manager in managers.values():
            manager.shutdown()
