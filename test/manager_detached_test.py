"""Real native staging/command execution and crash recovery for detached_local."""

import json
import os
import shlex
import signal
import sys
from pathlib import Path

import pytest

from pulsar.manager_factory import _get_managers_dict
from pulsar.managers import status
from pulsar.managers.detached import (
    ACK_FILE,
    CLEAN_FILE,
    concurrent_jobs,
    DetachedLocalManager,
)
from pulsar.managers.util import detached_worker as worker
from .test_utils import (
    minimal_app_for_managers,
    wait_for,
)


@pytest.fixture
def managers():
    app = minimal_app_for_managers()
    created = []

    def make(**kwds):
        kwds.setdefault("poll_interval", 0.03)
        kwds.setdefault("cancel_grace_seconds", 0.1)
        kwds.setdefault("supervisor_respawn_interval", 0.1)
        manager = DetachedLocalManager("test", app, **kwds)
        created.append(manager)
        return manager

    yield make
    # Never remove a staging directory underneath detached children.
    for manager in created:
        manager.shutdown(2)
    if created:
        manager = created[-1]
        for path in Path(manager.staging_directory).glob(f"*/{worker.MANIFEST_FILE}"):
            job_id = path.parent.name
            manifest = worker.read_json(path)
            # Tests that intentionally corrupt saved identity restore it first.
            manifest["host_identity"] = worker.host_identity()
            worker.atomic_json(path, manifest)
            manager.kill(job_id)
            wait_for(
                lambda job_id=job_id: manager.get_status(job_id),
                "detached test teardown",
                until=lambda value: value
                in (status.CANCELLED, status.COMPLETE, status.FAILED),
                timeout=10,
            )
            manager.acknowledge_collection(job_id)
            manager.clean(job_id)
    import shutil

    shutil.rmtree(app.staging_directory, ignore_errors=True)


def launch(manager, code, job_id="galaxy-job", policy=None):
    remote_id = manager.setup_job(job_id, "ordinary_tool", "1.0")
    root = Path(manager.job_directory(remote_id).job_directory)
    if policy is not None:
        (root / "configs" / "detached_execution.json").write_text(json.dumps(policy))
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"
    manager.launch(remote_id, command)
    return remote_id, root


def completed(manager, job_id, expected=status.COMPLETE):
    value = wait_for(
        lambda: manager.get_status(job_id),
        "detached execution to finish",
        until=lambda value: value in (status.COMPLETE, status.CANCELLED, status.FAILED),
        timeout=12,
    )
    assert value == expected


def started(root):
    return wait_for(
        lambda: worker.read_json(root / worker.COMMAND_FILE),
        "detached command identity",
        timeout=10,
    )


@pytest.mark.parametrize(
    "raw,expected", [(None, 0), (0, 0), ("0", 0), (1, 1), (4, 4), ("2", 2)]
)
def test_capacity_values(raw, expected):
    assert concurrent_jobs(raw) == expected


def test_cpu_capacity(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 7)
    assert concurrent_jobs("*") == 7


@pytest.mark.parametrize(
    "raw", [-1, "-2", True, False, 1.1, "1.1", "", [], {}, float("nan")]
)
def test_invalid_capacity_before_side_effects(raw, tmp_path):
    class App:
        staging_directory = str(tmp_path / "must-not-be-created")

    with pytest.raises(ValueError, match="num_concurrent_jobs"):
        DetachedLocalManager("invalid", App(), num_concurrent_jobs=raw)
    assert not Path(App.staging_directory).exists()


@pytest.mark.parametrize(
    "setting,value",
    [
        ("poll_interval", 0),
        ("poll_interval", True),
        ("cancel_grace_seconds", -1),
        ("cancel_grace_seconds", float("nan")),
        ("supervisor_respawn_interval", float("inf")),
    ],
)
def test_invalid_timing_before_side_effects(setting, value, tmp_path):
    class App:
        staging_directory = str(tmp_path / "must-not-be-created")

    with pytest.raises(ValueError):
        DetachedLocalManager("invalid", App(), **{setting: value})
    assert not Path(App.staging_directory).exists()


def test_native_factory_and_capability(managers):
    assert _get_managers_dict()["detached_local"] is DetachedLocalManager
    manager = managers()
    assert manager.system_properties()["detached_local"] == {
        "schema": 1,
        "asynchronous_cancel": True,
        "collection_ack": True,
        "execution_policy": True,
    }


def test_native_staging_streams_environment_and_exit_code(managers):
    manager = managers()
    job_id = manager.setup_job("123", "ordinary_tool", "1")
    root = Path(manager.job_directory(job_id).job_directory)
    (root / "inputs" / "in.txt").write_text("real staged input\n")
    manager.launch(
        job_id,
        "cat ../inputs/in.txt > ../outputs/out.txt; printf '%s' \"$MY_VALUE\" > ../metadata/tool_stdout; "
        "printf diagnostic > ../metadata/tool_stderr",
        env=[{"name": "MY_VALUE", "value": "native environment", "raw": False}],
    )
    completed(manager, job_id)
    assert (root / "outputs" / "out.txt").read_text() == "real staged input\n"
    assert manager.stdout_contents(job_id) == b"native environment"
    assert manager.stderr_contents(job_id) == b"diagnostic"
    assert manager.return_code(job_id) == 0
    assert (root / worker.MANIFEST_FILE).stat().st_mode & 0o777 == 0o600
    assert worker.read_json(root / worker.RESULT_FILE)["command_exit_confirmed"] is True


def test_nonzero_tool_exit_is_complete_for_native_client(managers):
    manager = managers()
    job_id, _ = launch(manager, "raise SystemExit(17)")
    completed(manager, job_id)
    assert manager.return_code(job_id) == 17


def test_restart_adopts_same_command_without_reexecution(managers):
    manager = managers()
    job_id, root = launch(
        manager,
        "from pathlib import Path; import time; p=Path('count'); p.write_text(p.read_text()+'x' if p.exists() else 'x'); time.sleep(.8)",
    )
    identity = started(root)["command_identity"]
    manager.shutdown(2)
    replacement = managers()
    replacement.launch(job_id, "false")
    completed(replacement, job_id)
    assert (root / "working" / "count").read_text() == "x"
    assert worker.read_json(root / worker.RESULT_FILE)["command_identity"] == identity


def test_capacity_shared_fifo_across_managers(managers):
    first = managers(num_concurrent_jobs=2)
    second = managers(num_concurrent_jobs=2)
    waiting = (
        "from pathlib import Path; import time; "
        "exec('while not Path(\"release\").exists(): time.sleep(.03)')"
    )
    one, root_one = launch(first, waiting)
    two, root_two = launch(second, waiting)
    three, root_three = launch(
        first, "from pathlib import Path; Path('started').touch()"
    )
    started(root_one)
    started(root_two)
    assert first.get_status(three) == status.QUEUED
    assert not (root_three / worker.COMMAND_FILE).exists()
    (root_one / "working" / "release").touch()
    (root_two / "working" / "release").touch()
    completed(first, one)
    completed(second, two)
    completed(first, three)
    commands = [
        worker.read_json(root / worker.COMMAND_FILE)
        for root in (root_one, root_two, root_three)
    ]
    exits = [worker.read_json(root / worker.EXIT_FILE) for root in (root_one, root_two)]
    assert commands[2]["started_at"] >= min(record["finished_at"] for record in exits)


@pytest.mark.parametrize("capacity", [None, 0])
def test_unbounded_does_not_queue_behind_running_commands(managers, capacity):
    manager = managers(num_concurrent_jobs=capacity)
    waiting = (
        "from pathlib import Path; import time; "
        "exec('while not Path(\"release\").exists(): time.sleep(.03)')"
    )
    executions = [launch(manager, waiting) for _ in range(3)]
    for job_id, root in executions:
        started(root)
        assert manager.get_status(job_id) == status.RUNNING
    for _, root in executions:
        (root / "working" / "release").touch()
    for job_id, _ in executions:
        completed(manager, job_id)


def test_conflicting_pool_capacity_rejected(managers):
    managers(num_concurrent_jobs=2)
    with pytest.raises(ValueError, match="Conflicting"):
        managers(num_concurrent_jobs=1)


def test_queued_stop_never_executes(managers):
    manager = managers(num_concurrent_jobs=1)
    blocker, blocker_root = launch(manager, "import time; time.sleep(30)")
    queued, root = launch(
        manager, "from pathlib import Path; Path('must-not-exist').touch()"
    )
    assert manager.get_status(queued) == status.QUEUED
    manager.kill(queued)
    completed(manager, queued, status.CANCELLED)
    assert not (root / worker.COMMAND_FILE).exists()
    assert not (root / "working" / "must-not-exist").exists()
    manager.kill(blocker)
    completed(manager, blocker, status.CANCELLED)


def test_stop_is_async_and_cleanup_requires_explicit_ack(managers):
    manager = managers()
    job_id, root = launch(manager, "import time; time.sleep(30)")
    started(root)
    manager.kill(job_id)
    manager.clean(job_id)
    manager.clean(job_id)
    assert (root / CLEAN_FILE).exists()
    assert not (root / ACK_FILE).exists()
    assert root.exists()
    completed(manager, job_id, status.CANCELLED)
    assert root.exists()
    assert manager.acknowledge_collection(job_id) is True
    assert not root.exists()
    assert manager.acknowledge_collection(job_id) is True
    manager.clean(job_id)


def test_collection_failure_retains_staging_until_acknowledged(managers):
    manager = managers()
    job_id, root = launch(
        manager,
        "from pathlib import Path; Path('../outputs/result').write_text('recover me')",
    )
    completed(manager, job_id)
    manager.clean(job_id)
    manager.shutdown(2)
    replacement = managers()
    assert root.exists()
    assert (root / "outputs" / "result").read_text() == "recover me"
    assert replacement.acknowledge_collection(job_id) is True
    assert not root.exists()


def test_supervisor_loss_uses_gate_exit_record(managers):
    manager = managers()
    job_id, root = launch(
        manager,
        "from pathlib import Path; import time; p=Path('count'); p.write_text(p.read_text()+'x' if p.exists() else 'x'); time.sleep(.5)",
    )
    command = started(root)["command_identity"]
    live = wait_for(
        lambda: worker.read_json(root / worker.LIVE_FILE), "live supervisor"
    )
    os.kill(live["worker_identity"]["pid"], signal.SIGKILL)
    completed(manager, job_id)
    assert (root / "working" / "count").read_text() == "x"
    assert worker.read_json(root / worker.RESULT_FILE)["command_identity"] == command


def test_manifests_reconciled_without_native_active_index(managers):
    manager = managers(num_concurrent_jobs=1)
    one, root_one = launch(manager, "import time; time.sleep(.3)")
    two, root_two = launch(
        manager, "from pathlib import Path; Path('recovered').touch()"
    )
    assert manager.get_status(two) == status.QUEUED
    manager.shutdown(2)
    replacement = managers(num_concurrent_jobs=1)
    completed(replacement, one)
    completed(replacement, two)
    assert (root_two / "working" / "recovered").exists()


def test_distinct_attempts_of_same_input_job_get_unique_roots(managers):
    manager = managers()
    one = manager.setup_job("same-galaxy-job", "tool", "1")
    two = manager.setup_job("same-galaxy-job", "tool", "1")
    assert one != two


def test_host_boot_mismatch_is_retained_and_holds_capacity(managers):
    manager = managers(num_concurrent_jobs=1)
    manager.shutdown(2)
    # Prevent initial worker launch so the test can set a foreign boot before
    # recovery. A durable reservation still consumes one slot.
    original_spawn = manager._spawn_worker
    manager._spawn_worker = lambda root, manifest: None
    job_id, root = launch(manager, "raise SystemExit('must never run')")
    manifest = worker.read_json(root / worker.MANIFEST_FILE)
    manifest["host_identity"] = {"hostname": "another-host", "boot_id": "another-boot"}
    worker.atomic_json(root / worker.MANIFEST_FILE, manifest)
    manager._spawn_worker = original_spawn
    replacement = managers(num_concurrent_jobs=1)
    queued, queued_root = launch(replacement, "print('must remain queued')")
    assert replacement.get_status(job_id) == status.RUNNING
    assert replacement.get_status(queued) == status.QUEUED
    assert not (root / worker.COMMAND_FILE).exists()
    replacement.clean(job_id)
    assert replacement.acknowledge_collection(job_id) is False
    assert root.exists()


def test_policy_is_snapshotted_and_enforced(managers):
    manager = managers()
    job_id, root = launch(
        manager,
        "import time; time.sleep(30)",
        policy={
            "schema": 1,
            "containers": [],
            "limits": {"walltime_seconds": 0.25},
        },
    )
    assert (
        worker.read_json(root / worker.MANIFEST_FILE)["limits"]["walltime_seconds"]
        == 0.25
    )
    manager.shutdown(2)
    # Enforcement is in the detached worker, not the manager polling thread.
    completed(manager, job_id, status.FAILED)
    assert "walltime" in worker.read_json(root / worker.RESULT_FILE)["failure"].lower()


def test_reservation_recovers_when_manager_dies_before_worker_fork(
    managers, monkeypatch
):
    manager = managers()
    manager.shutdown(2)
    with monkeypatch.context() as context:

        def crash_before_fork(root, manifest):
            raise OSError("simulated interruption before Popen")

        context.setattr(manager, "_spawn_worker", crash_before_fork)
        job_id, root = launch(
            manager,
            "from pathlib import Path; Path('once').write_text('one execution')",
        )
    assert worker.read_json(root / worker.MANIFEST_FILE)["phase"] == "launching"
    assert not (root / worker.LIVE_FILE).exists()
    replacement = managers()
    completed(replacement, job_id)
    assert (root / "working" / "once").read_text() == "one execution"


def test_unconfirmed_terminal_record_cannot_release_capacity_or_delete(managers):
    manager = managers(num_concurrent_jobs=1)
    job_id, root = launch(manager, "pass")
    completed(manager, job_id)
    manager.shutdown(2)
    result_path = root / worker.RESULT_FILE
    original = worker.read_json(result_path)
    invalid = dict(original, container_exit_confirmed=False)
    worker.atomic_json(result_path, invalid)
    try:
        replacement = managers(num_concurrent_jobs=1)
        queued, queued_root = launch(replacement, "print('next command')")
        replacement.clean(job_id)
        assert replacement.get_status(job_id) == status.RUNNING
        assert replacement.acknowledge_collection(job_id) is False
        assert root.exists()
        assert replacement.get_status(queued) == status.QUEUED
        assert not (queued_root / worker.COMMAND_FILE).exists()
    finally:
        worker.atomic_json(result_path, original)


def test_pool_capacity_coordinates_independent_server_processes(managers):
    import subprocess

    manager = managers(num_concurrent_jobs=1)
    blocker, blocker_root = launch(
        manager,
        "from pathlib import Path; import time; "
        "exec('while not Path(\"release\").exists(): time.sleep(.03)')",
    )
    started(blocker_root)
    program = """
import sys
from test.test_utils import minimal_app_for_managers
from pulsar.managers.detached import DetachedLocalManager
app = minimal_app_for_managers()
manager = DetachedLocalManager('other-process', app, staging_directory=sys.argv[1], num_concurrent_jobs=1, poll_interval=.03)
job_id = manager.setup_job('second-process-job', 'ordinary_tool', '1')
manager.launch(job_id, 'printf second-process > ../outputs/result')
manager.shutdown(2)
print(job_id)
"""
    environment = os.environ.copy()
    source = str(Path(__file__).resolve().parent.parent)
    environment["PYTHONPATH"] = source + os.pathsep + environment.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", program, manager.staging_directory],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
    )
    job_id = result.stdout.strip().splitlines()[-1]
    root = Path(manager.job_directory(job_id).job_directory)
    assert manager.get_status(job_id) == status.QUEUED
    assert not (root / worker.COMMAND_FILE).exists()
    (blocker_root / "working" / "release").touch()
    completed(manager, blocker)
    completed(manager, job_id)
    assert (root / "outputs" / "result").read_text() == "second-process"


def test_unknown_admission_state_cannot_authorize_launch_or_cleanup(
    managers, monkeypatch
):
    manager = managers(num_concurrent_jobs=1)
    manager.shutdown(2)
    with monkeypatch.context() as context:
        context.setattr(manager, "_spawn_worker", lambda root, manifest: None)
        job_id, root = launch(manager, "raise SystemExit('must not execute')")
    path = root / worker.MANIFEST_FILE
    manifest = worker.read_json(path)
    worker.atomic_json(path, dict(manifest, phase="unrecognized-state"))
    try:
        replacement = managers(num_concurrent_jobs=1)
        assert replacement.get_status(job_id) == status.RUNNING
        assert not (root / worker.COMMAND_FILE).exists()
        with pytest.raises(ValueError, match="Unknown detached admission"):
            replacement.clean(job_id)
        assert root.exists()
    finally:
        worker.atomic_json(path, manifest)


def test_unknown_supervisor_state_cannot_authorize_launch(managers, monkeypatch):
    manager = managers()
    manager.shutdown(2)
    with monkeypatch.context() as context:
        context.setattr(manager, "_spawn_worker", lambda root, manifest: None)
        job_id, root = launch(manager, "raise SystemExit('must not execute')")
    manifest = worker.read_json(root / worker.MANIFEST_FILE)
    live_path = root / worker.LIVE_FILE
    worker.atomic_json(
        live_path,
        {
            "schema": 1,
            "job_id": job_id,
            "token": manifest["token"],
            "phase": "future-unknown-state",
            "launch_intent": True,
        },
    )
    try:
        replacement = managers()
        assert replacement.get_status(job_id) == status.RUNNING
        assert not (root / worker.COMMAND_FILE).exists()
    finally:
        live_path.unlink()


def test_slow_preparation_does_not_block_unrelated_pool_operations(
    managers, monkeypatch
):
    import threading

    manager = managers(num_concurrent_jobs=2)
    running, running_root = launch(manager, "import time; time.sleep(30)")
    started(running_root)
    slow = manager.setup_job("slow-preparation", "ordinary_tool", "1")
    prepare_entered = threading.Event()
    release_prepare = threading.Event()
    unrelated_done = threading.Event()
    errors = []
    original_prepare = manager._prepare_run

    def prepare(job_id, *args, **kwargs):
        if job_id == slow:
            prepare_entered.set()
            assert release_prepare.wait(10)
        return original_prepare(job_id, *args, **kwargs)

    monkeypatch.setattr(manager, "_prepare_run", prepare)

    def submit_slow():
        try:
            manager.launch(slow, "true")
        except BaseException as error:
            errors.append(error)

    def unrelated():
        try:
            assert manager.get_status(running) == status.RUNNING
            manager.kill(running)
            launch(manager, "print('independent preparation')")
            unrelated_done.set()
        except BaseException as error:
            errors.append(error)

    slow_thread = threading.Thread(target=submit_slow)
    other_thread = threading.Thread(target=unrelated)
    slow_thread.start()
    try:
        assert prepare_entered.wait(3)
        other_thread.start()
        assert unrelated_done.wait(
            3
        ), "Slow dependency preparation held the shared pool lock"
    finally:
        release_prepare.set()
        slow_thread.join(10)
        if other_thread.ident:
            other_thread.join(10)
    assert not slow_thread.is_alive() and not other_thread.is_alive()
    assert errors == []
    completed(manager, running, status.CANCELLED)
    completed(manager, slow)


def test_concurrent_duplicate_submissions_prepare_and_execute_once(
    managers, monkeypatch
):
    import threading

    manager = managers()
    job_id = manager.setup_job("same-attempt", "ordinary_tool", "1")
    root = Path(manager.job_directory(job_id).job_directory)
    entered = threading.Event()
    release = threading.Event()
    preparations = []
    errors = []
    original_prepare = manager._prepare_run

    def prepare(*args, **kwargs):
        preparations.append(args[0])
        entered.set()
        assert release.wait(10)
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(manager, "_prepare_run", prepare)

    def submit():
        try:
            manager.launch(job_id, "printf x >> count")
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=submit)
    second = threading.Thread(target=submit)
    first.start()
    try:
        assert entered.wait(3)
        second.start()
    finally:
        release.set()
        first.join(10)
        if second.ident:
            second.join(10)
    assert errors == []
    assert preparations == [job_id]
    completed(manager, job_id)
    assert (root / "working" / "count").read_text() == "x"


def test_stateful_proxy_stop_before_launch_has_terminal_no_command_proof(managers):
    from pulsar.managers import ManagerProxy
    from pulsar.managers.stateful import (
        JOB_FILE_PREPROCESSED,
        StatefulManagerProxy,
    )

    manager = managers()
    proxy = StatefulManagerProxy(manager)
    job_id = proxy.setup_job("stop-before-submit", "ordinary_tool", "1")
    root = Path(proxy.job_directory(job_id).job_directory)
    proxy.kill(job_id)
    # A stop request without a submit is not proof that staging has finished.
    assert proxy.get_status(job_id) == status.PREPROCESSING
    assert not (root / worker.RESULT_FILE).exists()
    proxy.preprocess_and_launch(job_id, {"command_line": "touch must-not-run"})
    assert proxy.get_status(job_id) == status.CANCELLED
    assert manager.job_directory(job_id).has_metadata(JOB_FILE_PREPROCESSED)
    assert (
        worker.read_json(root / worker.MANIFEST_FILE)["cancelled_before_launch"] is True
    )
    assert not (root / worker.COMMAND_FILE).exists()
    assert not (root / "working" / "must-not-run").exists()
    assert proxy.active_jobs.active_job_ids() == []
    # Optional confirmation is forwarded through other manager facades too.
    ManagerProxy(manager).confirm_cancelled_before_launch(job_id)
    proxy.clean(job_id)
    assert root.exists()
    assert proxy.acknowledge_collection(job_id) is True
    assert not root.exists()


def test_stateful_proxy_stop_waits_for_preprocessing_writers(managers, monkeypatch):
    import threading

    from pulsar.managers import stateful
    from pulsar.managers.stateful import StatefulManagerProxy

    manager = managers()
    proxy = StatefulManagerProxy(manager)
    job_id = proxy.setup_job("stop-during-copy", "ordinary_tool", "1")
    root = Path(proxy.job_directory(job_id).job_directory)
    copying = threading.Event()
    release = threading.Event()

    def slow_preprocess(*args, **kwargs):
        copying.set()
        assert release.wait(10)
        (root / "inputs" / "copy-finished").touch()

    monkeypatch.setattr(stateful, "preprocess", slow_preprocess)
    proxy.preprocess_and_launch(
        job_id,
        {
            "command_line": "touch must-not-run",
            "remote_staging": {"setup": [{}]},
        },
    )
    try:
        assert copying.wait(3)
        proxy.kill(job_id)
        assert proxy.get_status(job_id) == status.PREPROCESSING
        assert not (root / worker.RESULT_FILE).exists()
    finally:
        release.set()
    wait_for(
        lambda: proxy.get_status(job_id) == status.CANCELLED,
        "copy cancellation proof",
        timeout=5,
    )
    assert (root / "inputs" / "copy-finished").exists()
    assert not (root / worker.COMMAND_FILE).exists()
    assert not (root / "working" / "must-not-run").exists()


def test_stateful_proxy_stop_during_command_preparation_never_launches(
    managers, monkeypatch
):
    import threading

    from pulsar.managers.stateful import StatefulManagerProxy

    manager = managers()
    proxy = StatefulManagerProxy(manager)
    job_id = proxy.setup_job("stop-during-prepare", "ordinary_tool", "1")
    root = Path(proxy.job_directory(job_id).job_directory)
    entered = threading.Event()
    release = threading.Event()
    original_prepare = manager._prepare_run

    def slow_prepare(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(manager, "_prepare_run", slow_prepare)
    thread = threading.Thread(
        target=proxy.preprocess_and_launch,
        args=(job_id, {"command_line": "touch must-not-run"}),
    )
    thread.start()
    try:
        assert entered.wait(3)
        proxy.kill(job_id)
        assert proxy.get_status(job_id) == status.PREPROCESSING
        assert not (root / worker.RESULT_FILE).exists()
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive()
    assert proxy.get_status(job_id) == status.CANCELLED
    assert not (root / worker.COMMAND_FILE).exists()
    assert not (root / "working" / "must-not-run").exists()


def test_stateful_proxy_recovers_durable_cancel_before_its_preprocessed_flag(managers):
    from pulsar.managers.stateful import StatefulManagerProxy

    manager = managers()
    proxy = StatefulManagerProxy(manager)
    job_id = proxy.setup_job("crash-after-cancel-proof", "ordinary_tool", "1")
    root = Path(proxy.job_directory(job_id).job_directory)
    proxy.kill(job_id)
    # Simulate the proxy exiting after manager confirmation but before its own
    # PREPROCESSED write. A replacement reads authoritative terminal proof.
    manager.confirm_cancelled_before_launch(job_id)
    replacement = StatefulManagerProxy(manager)
    assert replacement.get_status(job_id) == status.CANCELLED
    assert not (root / worker.COMMAND_FILE).exists()


@pytest.mark.parametrize("cancel_before_prepare", [False, True])
def test_proxy_terminal_cancel_poll_cannot_reactivate_active_index(
    managers, monkeypatch, cancel_before_prepare
):
    from pulsar.managers.stateful import StatefulManagerProxy

    manager = managers()
    proxy = StatefulManagerProxy(manager)
    job_id = proxy.setup_job("cancel-index-race", "ordinary_tool", "1")
    if cancel_before_prepare:
        proxy.kill(job_id)
        original = manager.confirm_cancelled_before_launch

        def confirm(*args, **kwargs):
            original(*args, **kwargs)
            assert proxy.get_status(job_id) == status.CANCELLED

        monkeypatch.setattr(manager, "confirm_cancelled_before_launch", confirm)
    else:
        original = manager.launch

        def launch_after_stop(*args, **kwargs):
            manager.kill(job_id)
            original(*args, **kwargs)
            assert proxy.get_status(job_id) == status.CANCELLED

        monkeypatch.setattr(manager, "launch", launch_after_stop)
    proxy.preprocess_and_launch(job_id, {"command_line": "touch must-not-run"})
    assert proxy.get_status(job_id) == status.CANCELLED
    assert proxy.active_jobs.active_job_ids() == []
