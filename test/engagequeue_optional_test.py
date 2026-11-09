"""The optional CLI scheduler must load without the executor Python package."""

import subprocess
import sys

import pytest

from pulsar.managers import status
from pulsar.managers.queued_cli import CliQueueManager
from pulsar.managers.stateful import StatefulManagerProxy
from pulsar.managers.util.cli.job import job_states
from pulsar.managers.util.cli.job.engagequeue import EngageQueue
from .test_utils import minimal_app_for_managers


def test_plugin_discovery_does_not_import_optional_executor():
    script = """
import importlib.abc
import sys

class RejectExecutorImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'engagequeue' or fullname.startswith('engagequeue.'):
            raise AssertionError('Pulsar imported the optional executor library')
        return None

sys.meta_path.insert(0, RejectExecutorImport())
from pulsar.managers.util.cli import CliInterface
plugin = CliInterface().get_job_interface({'plugin': 'EngageQueue', 'state_dir': '/unused'})
assert plugin.__class__.__module__ == 'pulsar.managers.util.cli.job.engagequeue'
assert 'engagequeue' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_scheduler_cancel_status_does_not_redeliver(tmp_path, monkeypatch):
    app = minimal_app_for_managers()
    app.staging_directory = str(tmp_path / "staging")
    app.persistence_directory = str(tmp_path / "persistence")
    manager = CliQueueManager("legacy", app, job_plugin="Slurm")
    try:
        job_id = manager.setup_job("legacy", "tool", "1")
        manager._record_cancel(job_id)

        def unexpected_cancel(external_id):
            raise AssertionError("Legacy status polling must not redeliver cancellation")

        monkeypatch.setattr(manager, "_kill_external", unexpected_cancel)
        assert manager.get_status(job_id) == status.CANCELLED
    finally:
        manager.shutdown()


def test_custom_cli_subclass_without_job_plugin_preserves_launch_status_and_cancel(tmp_path):
    class CustomCliManager(CliQueueManager):
        def launch(self, job_id, command_line, *args, **kwargs):
            self.job_directory(job_id).write_file("outputs/invoked", command_line.encode())
            self._register_external_id(job_id, "custom-execution")

        def _get_status_external(self, external_id):
            assert external_id == "custom-execution"
            return status.RUNNING

    app = minimal_app_for_managers()
    app.staging_directory = str(tmp_path / "staging")
    app.persistence_directory = str(tmp_path / "persistence")
    manager = CustomCliManager("custom", app)
    proxy = StatefulManagerProxy(manager)
    try:
        assert not manager.recoverable_submission
        job_id = proxy.setup_job("custom", "tool", "1")
        proxy.preprocess_and_launch(job_id, {"command_line": "custom-command", "remote_staging": {}})
        assert manager.job_directory(job_id).read_file("outputs/invoked") == b"custom-command"
        assert proxy.get_status(job_id) == status.RUNNING
        manager._record_cancel(job_id)
        assert proxy.get_status(job_id) == status.CANCELLED
    finally:
        proxy.shutdown()


def test_invalid_cli_plugin_records_preprocessing_failure_without_escaping(tmp_path):
    app = minimal_app_for_managers()
    app.staging_directory = str(tmp_path / "staging")
    app.persistence_directory = str(tmp_path / "persistence")
    manager = CliQueueManager("invalid", app, job_plugin="MissingScheduler")
    proxy = StatefulManagerProxy(manager)
    try:
        job_id = proxy.setup_job("invalid", "tool", "1")
        proxy.preprocess_and_launch(job_id, {"command_line": "never-executed", "remote_staging": {}})
        assert proxy.get_status(job_id) == status.FAILED
        assert manager.job_directory(job_id).has_metadata("preprocessing_failed")
        assert "MissingScheduler" in manager.job_directory(job_id).read_file("stderr").decode()
    finally:
        proxy.shutdown()


@pytest.mark.parametrize("layout", ["marker", "dangling-marker", "root-alias"])
def test_managed_profile_is_rejected_before_new_dispatch(tmp_path, monkeypatch, layout):
    real_state = tmp_path / "real-state"
    real_state.mkdir()
    marker = real_state / "managed.json"
    state_dir = real_state
    if layout == "dangling-marker":
        try:
            marker.symlink_to(tmp_path / "missing-profile")
        except OSError:
            if sys.platform != "win32":
                raise
            pytest.skip("Windows symlink creation is unavailable")
    else:
        marker.write_text("{}")
    if layout == "root-alias":
        state_dir = tmp_path / "state-alias"
        try:
            state_dir.symlink_to(real_state, target_is_directory=True)
        except OSError:
            if sys.platform != "win32":
                raise
            pytest.skip("Windows symlink creation is unavailable")
    app = minimal_app_for_managers()
    app.staging_directory = str(tmp_path / "staging")
    app.persistence_directory = str(tmp_path / "persistence")
    manager = CliQueueManager("local", app, job_plugin="EngageQueue", job_state_dir=str(state_dir))
    proxy = StatefulManagerProxy(manager)
    shell, _ = manager.cli_interface.get_plugins(manager.shell_params, manager.job_params)

    def unexpected_dispatch(*args, **kwargs):
        raise AssertionError("Managed profile must fail before any CLI dispatch")

    monkeypatch.setattr(shell, "execute", unexpected_dispatch)
    try:
        job_id = proxy.setup_job("managed-profile", "tool", "1")
        proxy.preprocess_and_launch(job_id, {"command_line": "never-executed", "remote_staging": {}})
        assert proxy.get_status(job_id) == status.FAILED
        assert "managed Docker profile" in manager.job_directory(job_id).read_file("stderr").decode()
        assert {path.name for path in real_state.iterdir()} == {"managed.json"}
    finally:
        proxy.shutdown()


def test_status_parsers_preserve_parent_keyword_contract():
    plugin = EngageQueue(state_dir="/unused")
    assert plugin.parse_single_status(status='{"id":"job","state":"RUNNING"}', job_id="job") == job_states.RUNNING
    assert plugin.parse_status(status='[{"id":"job","state":"RUNNING"}]', job_ids=["job"]) == {"job": job_states.RUNNING}
