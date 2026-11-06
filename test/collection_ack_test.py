"""Opt-in collection acknowledgment applies to ordinary managers and clients."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from shutil import rmtree

import pytest

from pulsar.client.client import (
    _setup_params_from_job_config,
    JobClient,
)
from pulsar.client.server_interface import LocalPulsarInterface
from pulsar.managers.queued import QueueManager
from pulsar.managers.stateful import StatefulManagerProxy
from .test_utils import (
    minimal_app_for_managers,
    test_pulsar_app as pulsar_app,
)


@pytest.fixture
def manager():
    app = minimal_app_for_managers()
    manager = QueueManager("_default_", app)
    try:
        yield manager
    finally:
        manager.shutdown()
        rmtree(app.staging_directory, ignore_errors=True)


def test_legacy_client_cleanup_has_no_new_ack_requirement(manager):
    job_id = manager.setup_job("legacy", "tool", "1")
    directory = manager.job_directory(job_id)
    assert not directory.has_metadata("collection_ack_required")
    manager.clean(job_id)
    assert not directory.exists()


def test_opted_in_cleanup_waits_for_ack_and_repeated_calls_are_safe(manager):
    job_id = manager.setup_job("retained", "tool", "1")
    directory = manager.job_directory(job_id)
    manager.require_collection_ack(job_id)
    directory.write_file("outputs/result", b"import me")
    manager.clean(job_id)
    assert directory.exists()
    assert directory.read_file("outputs/result") == b"import me"
    assert manager.acknowledge_collection(job_id)
    assert not directory.exists()
    assert manager.acknowledge_collection(job_id)
    manager.clean(job_id)


def test_ack_does_not_clean_until_client_requests_it(manager):
    job_id = manager.setup_job("retain", "tool", "1")
    manager.require_collection_ack(job_id)
    assert manager.acknowledge_collection(job_id)
    assert manager.job_directory(job_id).exists()
    manager.clean(job_id)
    assert not manager.job_directory(job_id).exists()


def test_failed_or_cancelled_before_launch_has_api_cleanup_path(manager):
    job_id = manager.setup_job("not-launched", "tool", "1")
    manager.require_collection_ack(job_id)
    manager.kill(job_id)
    manager.clean(job_id)
    assert manager.job_directory(job_id).exists()
    assert manager.acknowledge_collection(job_id)
    assert not manager.job_directory(job_id).exists()


def test_generic_guard_coordinates_independent_manager_instances(manager):
    job_id = manager.setup_job("racing", "tool", "1")
    manager.require_collection_ack(job_id)
    second = QueueManager("other", manager.app if hasattr(manager, "app") else _app_for(manager))
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for _ in range(15):
                futures.append(executor.submit(manager.clean, job_id))
                futures.append(executor.submit(second.acknowledge_collection, job_id))
            for future in futures:
                future.result(timeout=5)
        assert not manager.job_directory(job_id).exists()
    finally:
        second.shutdown()


def _app_for(manager):
    app = minimal_app_for_managers()
    app.staging_directory = manager.staging_directory
    app.persistence_directory = manager.staging_directory
    return app


def test_unknown_job_cannot_create_opt_in_ghost_directory(manager):
    with pytest.raises(KeyError):
        manager.require_collection_ack("unknown")
    assert not manager.job_directory("unknown").exists()


def test_debug_mode_preserves_data_even_after_ack(manager):
    manager.debug = True
    job_id = manager.setup_job("debug", "tool", "1")
    manager.require_collection_ack(job_id)
    manager.clean(job_id)
    manager.acknowledge_collection(job_id)
    assert manager.job_directory(job_id).exists()


def test_default_setup_wire_parameters_remain_unchanged():
    config = {"job_id": "1", "tool_id": "tool", "tool_version": "1"}
    assert "require_collection_ack" not in _setup_params_from_job_config(config)
    assert "require_collection_ack" not in _setup_params_from_job_config({**config, "require_collection_ack": False})
    assert _setup_params_from_job_config({**config, "require_collection_ack": True})["require_collection_ack"] is True


def test_local_client_setup_opt_in_and_ack_route(manager):
    proxy = StatefulManagerProxy(manager)
    interface = LocalPulsarInterface({}, job_manager=proxy)
    client = JobClient({}, "local", interface)
    config = client.setup(require_collection_ack=True)
    assert config["require_collection_ack"] is True
    assert config["system_properties"]["collection_ack"] == {"schema": 1}
    client.clean()
    assert manager.job_directory(client.job_id).exists()
    assert client.acknowledge_collection() == {"acknowledged": True}
    assert not manager.job_directory(client.job_id).exists()


@pytest.mark.parametrize("confirmation", [None, False, "false", "true", 1])
def test_client_requires_literal_setup_confirmation(manager, monkeypatch, confirmation):
    interface = LocalPulsarInterface({}, job_manager=StatefulManagerProxy(manager))
    client = JobClient({}, "local", interface)
    monkeypatch.setattr(client.setup_handler, "setup", lambda **kwargs: {"require_collection_ack": confirmation})
    with pytest.raises(RuntimeError, match="did not confirm"):
        client.setup(require_collection_ack=True)


def test_http_setup_and_ack_are_opt_in_and_idempotent(tmp_path):
    with pulsar_app() as app:
        legacy = json.loads(app.post("/jobs?job_id=legacy&tool_id=tool").text)
        app.delete("/jobs/" + legacy["job_id"])
        retained = json.loads(app.post("/jobs?job_id=ack&tool_id=tool&require_collection_ack=true").text)
        directory = Path(retained["job_directory"])
        assert directory.exists()
        app.delete("/jobs/" + retained["job_id"])
        assert directory.exists()
        response = json.loads(app.put("/jobs/" + retained["job_id"] + "/collection").text)
        assert response == {"acknowledged": True}
        assert not directory.exists()
        assert json.loads(app.put("/jobs/" + retained["job_id"] + "/collection").text) == {"acknowledged": True}
