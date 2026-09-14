import os
from os import environ

from pulsar.client.manager import (
    _per_handler_cursor_path,
    ClientManager,
)


def test_environment_variables_config():
    environ['PULSAR_CACHE_TRANSFERS'] = '1'
    client_manager = ClientManager()
    assert __produces_caching_client(client_manager)

    environ['PULSAR_CACHE_TRANSFERS'] = '0'
    client_manager = ClientManager()
    assert not __produces_caching_client(client_manager)

    environ['PULSAR_CACHE_TRANSFERS'] = '1'
    environ['PULSAR_CACHE_THREADS'] = '4'
    client_manager = ClientManager()
    client_manager.client_cacher.num_transfer_threads == 4


def test_kwds_config():
    client_manager = ClientManager(cache=True, transfer_threads=3)
    assert __produces_caching_client(client_manager)
    assert client_manager.client_cacher.num_transfer_threads == 3

    client_manager = ClientManager(cache=False)
    assert not __produces_caching_client(client_manager)


def __produces_caching_client(client_manager):
    return client_manager.client_class.__name__.find('Caching') > 0


def test_per_handler_cursor_path_passthrough_when_empty():
    assert _per_handler_cursor_path(None) is None
    assert _per_handler_cursor_path("") == ""


def test_per_handler_cursor_path_uses_explicit_handler_id():
    """The handler_id argument wins — it's the only thing the caller can
    guarantee is stable across restarts."""
    assert _per_handler_cursor_path(
        "/var/lib/galaxy/relay_cursor.json", "handler0",
    ) == "/var/lib/galaxy/relay_cursor-handler0.json"
    assert _per_handler_cursor_path("relay_cursor", "handler1") == "relay_cursor-handler1"


def test_per_handler_cursor_path_falls_back_to_galaxy_server_name(monkeypatch):
    monkeypatch.setenv("GALAXY_SERVER_NAME", "main.handler2")
    assert _per_handler_cursor_path("/tmp/relay_cursor.json") == \
        "/tmp/relay_cursor-main.handler2.json"


def test_per_handler_cursor_path_falls_back_to_pid_with_warning(monkeypatch, caplog):
    monkeypatch.delenv("GALAXY_SERVER_NAME", raising=False)
    with caplog.at_level("WARNING"):
        path = _per_handler_cursor_path("/tmp/relay_cursor.json")
    assert path == f"/tmp/relay_cursor-pid{os.getpid()}.json"
    assert any("will not be picked up after a process restart" in rec.message
               for rec in caplog.records)


def test_per_handler_cursor_path_includes_manager_name():
    """Multi-tenant runners drive many managers from one handler; each
    needs its own cursor file."""
    assert _per_handler_cursor_path(
        "/var/lib/galaxy/relay_cursor.json",
        "handler0",
        manager_name="byoc_7_lab",
    ) == "/var/lib/galaxy/relay_cursor-handler0-byoc_7_lab.json"


def test_per_handler_cursor_path_omits_default_manager_name():
    """``_default_`` is the historical single-manager sentinel — its cursor
    files must keep their existing path so single-Pulsar deployments
    upgrading to this version don't orphan their persisted progress."""
    assert _per_handler_cursor_path(
        "/var/lib/galaxy/relay_cursor.json",
        "handler0",
        manager_name="_default_",
    ) == "/var/lib/galaxy/relay_cursor-handler0.json"
    # Also true when no manager_name is supplied at all.
    assert _per_handler_cursor_path(
        "/var/lib/galaxy/relay_cursor.json", "handler0",
    ) == "/var/lib/galaxy/relay_cursor-handler0.json"
