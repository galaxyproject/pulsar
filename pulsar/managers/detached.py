"""Durable, optionally bounded local execution through native Pulsar staging.

Every accepted command has a private manifest before it is eligible to run.
The staging directory is the pool boundary: independent handlers coordinate
admission with a file lock, while copied workers own execution independently
of a Pulsar/Galaxy process.  An ambiguous execution is retained, never replayed.
"""

import fcntl
import logging
import math
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from pulsar.managers import status
from pulsar.managers.unqueued import (
    Manager,
    new_clean_env,
)
from pulsar.managers.util import detached_worker as worker

log = logging.getLogger(__name__)
POOL_DIRECTORY = ".pulsar-detached-pool"
CLEAN_FILE = ".pulsar-detached-clean.json"
ACK_FILE = ".pulsar-detached-collected.json"


def concurrent_jobs(value):
    """Normalize native queue capacity: null/zero unlimited, '*' host CPUs."""
    if value is None:
        return 0
    if value == "*":
        return os.cpu_count() or 1
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(
            "num_concurrent_jobs must be a nonnegative integer, null, or '*'"
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "num_concurrent_jobs must be a nonnegative integer, null, or '*'"
        ) from error
    if parsed < 0:
        raise ValueError("num_concurrent_jobs cannot be negative")
    return parsed


def _seconds(value, name, allow_zero=False):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(result) or result < 0 or (result == 0 and not allow_zero):
        raise ValueError(
            f"{name} must be {'nonnegative' if allow_zero else 'positive'} and finite"
        )
    return result


class DetachedLocalManager(Manager):
    """Native Pulsar commands supervised outside the server process session.

    All managers using one staging directory form one FIFO capacity pool.
    Cleanup requires both a verified terminal result and an explicit client
    collection acknowledgment.  Stopping the server never stops a tool.
    """

    manager_type = "detached_local"

    def __init__(self, name, app, **kwds):
        # Configuration errors must fail before base setup or any threads.
        self.num_concurrent_jobs = concurrent_jobs(kwds.get("num_concurrent_jobs", 1))
        self.cancel_grace_seconds = _seconds(
            kwds.get("cancel_grace_seconds", 10), "cancel_grace_seconds", True
        )
        self.poll_interval = _seconds(kwds.get("poll_interval", 0.5), "poll_interval")
        self.supervisor_respawn_interval = _seconds(
            kwds.get("supervisor_respawn_interval", 3), "supervisor_respawn_interval"
        )
        if os.name != "posix":
            raise ValueError(
                "detached_local requires a POSIX host with flock and process sessions"
            )
        # Each setup is a fresh attempt, including resubmission of a Galaxy job.
        kwds.setdefault("assign_ids", "uuid")
        super().__init__(name, app, **kwds)
        self.staging_directory = str(Path(self.staging_directory).resolve())
        self._pool = Path(self.staging_directory) / POOL_DIRECTORY
        self._pool.mkdir(mode=0o700, exist_ok=True)
        self._shutdown = threading.Event()
        self._children = []
        with self._pool_lock():
            self._check_pool_configuration()
            self._reconcile_locked()
        self._housekeeper = threading.Thread(
            target=self._housekeep, daemon=True, name=f"pulsar-detached-{name}"
        )
        self._housekeeper.start()

    @contextmanager
    def _pool_lock(self):
        with (self._pool / "lock").open("a") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield

    @contextmanager
    def _preparation_lock(self, root):
        # Dependency resolution may install an environment. Serialize repeated
        # preparation of this attempt without blocking unrelated pool activity.
        with (root / ".pulsar-detached-preparation.lock").open("a") as handle:
            os.fchmod(handle.fileno(), 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield

    def _check_pool_configuration(self):
        path = self._pool / "configuration.json"
        expected = {"schema": 1, "num_concurrent_jobs": self.num_concurrent_jobs}
        current = worker.read_json(path)
        if current is None:
            worker.atomic_json(path, expected)
        elif current != expected:
            raise ValueError(
                "Conflicting detached_local capacity for the same staging_directory"
            )

    def system_properties(self):
        properties = dict(super().system_properties())
        properties["detached_local"] = {
            "schema": 1,
            "asynchronous_cancel": True,
            "collection_ack": True,
            "execution_policy": True,
        }
        return properties

    def _root(self, job_id):
        return Path(self.job_directory(str(job_id)).job_directory)

    def _read_manifest(self, root):
        manifest = worker.read_json(root / worker.MANIFEST_FILE)
        if manifest is None:
            return None
        worker._validate_manifest(manifest)
        if (
            manifest["job_id"] != root.name
            or Path(manifest["job_directory"]).resolve() != root.resolve()
        ):
            raise ValueError(
                "Detached manifest does not belong to its staging directory"
            )
        if manifest.get("phase") not in ("queued", "launching"):
            raise ValueError("Unknown detached admission state; retaining execution")
        submitted_at = manifest.get("submitted_at")
        if (
            isinstance(submitted_at, bool)
            or not isinstance(submitted_at, int)
            or submitted_at <= 0
        ):
            raise ValueError("Invalid detached submission ordering record")
        return manifest

    def _record(self, root, name, manifest):
        record = worker.read_json(root / name)
        if record is not None and (
            not isinstance(record, dict)
            or record.get("schema") != 1
            or record.get("job_id") != manifest["job_id"]
            or record.get("token") != manifest["token"]
        ):
            raise ValueError(f"Detached {name} does not belong to this execution")
        return record

    def _base_record(self, manifest):
        return {"schema": 1, "job_id": manifest["job_id"], "token": manifest["token"]}

    def _terminal_result(self, root, manifest):
        if manifest["host_identity"] != worker.host_identity():
            return None
        result = self._record(root, worker.RESULT_FILE, manifest)
        if result is None:
            return None
        return_code = result.get("return_code", result.get("returncode"))
        if (
            result.get("command_exit_confirmed") is not True
            or result.get("container_exit_confirmed") is not True
            or isinstance(return_code, bool)
            or not isinstance(return_code, int)
        ):
            return None
        return result

    def launch(
        self,
        job_id,
        command_line,
        submit_params=None,
        dependencies_description=None,
        env=None,
        setup_params=None,
    ):
        job_id = str(job_id)
        root = self._root(job_id)
        with self._preparation_lock(root):
            # Submission retries are reconnection, never a fresh execution.
            if (root / worker.MANIFEST_FILE).exists():
                with self._pool_lock():
                    self._read_manifest(root)
                    self._reconcile_locked()
                return
            if self._was_cancelled(job_id):
                with self._pool_lock():
                    self._confirm_cancelled_before_launch_locked(root, job_id)
                return
            policy = worker.read_json(
                root / "configs" / "detached_execution.json", {"schema": 1}
            )
            if not isinstance(policy, dict) or policy.get("schema") != 1:
                raise ValueError("Unsupported detached execution policy schema")
            container_configuration = worker.read_json(
                root / "configs" / "container_config.json"
            )
            script = self._prepare_run(
                job_id,
                command_line,
                dependencies_description=dependencies_description,
                env=env or [],
                setup_params=setup_params,
            )
            manifest = self._new_manifest(root, job_id, script, policy)
            if container_configuration:
                manifest["entry_point_config"] = container_configuration.get(
                    "entry_point_config", container_configuration
                )
                # Interactive tool commands conventionally expose these paths.
                for directory in ("working/import", "working/tmp"):
                    (root / directory).mkdir(parents=True, exist_ok=True)
            worker._validate_manifest(manifest)
            shutil.copyfile(worker.__file__, root / worker.WORKER_FILE)
            os.chmod(root / worker.WORKER_FILE, 0o600)
            with self._pool_lock():
                # kill() can record cancellation while preparation is blocked.
                # Publish Stop first so a crash during manifest publication
                # cannot make an already cancelled command eligible to start.
                cancelled = self._was_cancelled(job_id)
                if cancelled:
                    worker.atomic_json(
                        root / worker.STOP_FILE, self._base_record(manifest)
                    )
                worker.atomic_json(root / worker.MANIFEST_FILE, manifest)
                if cancelled:
                    self._cancel_queued(root, manifest)
                self._reconcile_locked()

    def _new_manifest(self, root, job_id, script, policy=None):
        policy = policy or {}
        return {
            "schema": 1,
            "job_id": job_id,
            "token": uuid.uuid4().hex,
            "job_directory": str(root),
            "working_directory": str(root / "working"),
            "command_script": str(Path(script).resolve()),
            "stdout": self._job_stdout_path(job_id),
            "stderr": self._job_stderr_path(job_id),
            "environment": new_clean_env(),
            "cancel_grace_seconds": self.cancel_grace_seconds,
            "poll_interval": self.poll_interval,
            "host_identity": worker.host_identity(),
            "containers": policy.get("containers", []),
            "limits": policy.get("limits", {}),
            "phase": "queued",
            "submitted_at": time.time_ns(),
        }

    def confirm_cancelled_before_launch(self, job_id):
        """Complete cancellation only after the proxy has stopped staging.

        The caller proves preprocessing has returned. The attempt lock then
        waits for command preparation to return, so no preparation writer can
        race a terminal result or eventual collection. If launch was already
        accepted, retain its normal worker-controlled termination protocol.
        """
        job_id = str(job_id)
        root = self._root(job_id)
        with self._preparation_lock(root):
            with self._pool_lock():
                self._confirm_cancelled_before_launch_locked(root, job_id)

    def _confirm_cancelled_before_launch_locked(self, root, job_id):
        if not self._was_cancelled(job_id):
            raise ValueError("Cannot confirm an attempt without a cancellation request")
        manifest = self._read_manifest(root)
        if manifest is None:
            manifest = self._new_manifest(root, job_id, root / "command.sh")
            manifest["cancelled_before_launch"] = True
            worker.atomic_json(root / worker.STOP_FILE, self._base_record(manifest))
            worker.atomic_json(root / worker.MANIFEST_FILE, manifest)
        else:
            worker.atomic_json(root / worker.STOP_FILE, self._base_record(manifest))
        if (
            manifest["phase"] == "queued"
            and manifest["host_identity"] == worker.host_identity()
        ):
            self._cancel_queued(root, manifest)
        self._reconcile_locked()

    def _cancel_queued(self, root, manifest):
        worker.atomic_json(root / worker.STOP_FILE, self._base_record(manifest))
        worker.atomic_json(
            root / worker.RESULT_FILE,
            {
                **self._base_record(manifest),
                "stopped": True,
                "return_code": 143,
                "command_exit_confirmed": True,
                "container_exit_confirmed": True,
                "finished_at": time.time(),
            },
        )
        self._write_return_code_if_unset(manifest["job_id"], "143")

    def _spawn_worker(self, root, manifest):
        manifest["supervisor_requested_at"] = time.time()
        worker.atomic_json(root / worker.MANIFEST_FILE, manifest)
        arguments = [
            sys.executable,
            str(root / worker.WORKER_FILE),
            str(root / worker.MANIFEST_FILE),
            "--recover",
        ]
        with (root / ".pulsar-detached-supervisor.log").open("ab") as output:
            os.fchmod(output.fileno(), 0o600)
            process = subprocess.Popen(
                arguments,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                start_new_session=True,
                close_fds=True,
                env=new_clean_env(),
            )
        self._children.append(process)

    def _ensure_worker(self, root, manifest):
        if manifest["host_identity"] != worker.host_identity():
            return
        live = self._record(root, worker.LIVE_FILE, manifest)
        if live and live.get("phase") not in (
            "starting",
            "recovering",
            "starting_command",
            "gated",
            "running",
            "stopping",
            "retained",
            "finished",
        ):
            raise ValueError("Unknown detached supervisor state; retaining execution")
        # Access-denied means unknown; it is never permission to adopt a PID.
        if live and worker.identity_alive(live.get("worker_identity")) is not False:
            return
        if (
            time.time() - manifest.get("supervisor_requested_at", 0)
            < self.supervisor_respawn_interval
        ):
            return
        self._spawn_worker(root, manifest)

    def _reconcile_locked(self):
        self._children = [
            process for process in self._children if process.poll() is None
        ]
        active = 0
        queued = []
        for path in sorted(
            Path(self.staging_directory).glob(f"*/{worker.MANIFEST_FILE}")
        ):
            root = path.parent
            try:
                manifest = self._read_manifest(root)
                result = self._terminal_result(root, manifest)
                if result:
                    self._write_return_code_if_unset(
                        manifest["job_id"],
                        str(result.get("return_code", result.get("returncode"))),
                    )
                    self._maybe_clean_locked(root, manifest)
                elif manifest["host_identity"] != worker.host_identity():
                    active += 1
                elif manifest.get("phase") == "queued":
                    if self._record(
                        root, worker.STOP_FILE, manifest
                    ) or self._was_cancelled(manifest["job_id"]):
                        self._cancel_queued(root, manifest)
                        self._maybe_clean_locked(root, manifest)
                    else:
                        queued.append(
                            (
                                manifest["submitted_at"],
                                manifest["job_id"],
                                root,
                                manifest,
                            )
                        )
                else:
                    active += 1
                    self._ensure_worker(root, manifest)
            except Exception:
                # Corrupt/foreign records cannot release capacity or authorize
                # collection. Keep unrelated jobs manageable and log evidence.
                active += 1
                log.exception("Retaining uncertain detached execution at %s", root)
        for _, _, root, manifest in sorted(queued):
            if self.num_concurrent_jobs and active >= self.num_concurrent_jobs:
                break
            manifest["phase"] = "launching"
            worker.atomic_json(root / worker.MANIFEST_FILE, manifest)
            active += 1
            try:
                self._spawn_worker(root, manifest)
            except Exception:
                # The durable reservation remains and is retried on recovery.
                log.exception("Unable to start detached supervisor at %s", root)

    def _housekeep(self):
        while not self._shutdown.wait(self.poll_interval):
            try:
                with self._pool_lock():
                    self._reconcile_locked()
            except Exception:
                log.exception("Detached local pool reconciliation failed")

    def get_status(self, job_id):
        root = self._root(job_id)
        with self._pool_lock():
            try:
                manifest = self._read_manifest(root)
                if manifest is None:
                    return status.QUEUED
                result = self._terminal_result(root, manifest)
                if result:
                    self._write_return_code_if_unset(
                        str(job_id),
                        str(result.get("return_code", result.get("returncode"))),
                    )
                    if result.get("failure"):
                        return status.FAILED
                    return (
                        status.CANCELLED if result.get("stopped") else status.COMPLETE
                    )
                if manifest["host_identity"] != worker.host_identity():
                    return status.RUNNING
                return (
                    status.QUEUED
                    if manifest.get("phase") == "queued"
                    else status.RUNNING
                )
            except Exception:
                log.exception(
                    "Cannot determine detached execution status for %s", job_id
                )
                return status.RUNNING

    def kill(self, job_id):
        root = self._root(job_id)
        with self._pool_lock():
            self._record_cancel(str(job_id))
            manifest = self._read_manifest(root)
            if manifest is None:
                return
            worker.atomic_json(root / worker.STOP_FILE, self._base_record(manifest))
            if (
                manifest.get("phase") == "queued"
                and manifest["host_identity"] == worker.host_identity()
            ):
                self._cancel_queued(root, manifest)
            self._reconcile_locked()

    def job_stderr_contents(self, job_id):
        contents = super().job_stderr_contents(job_id)
        try:
            root = self._root(job_id)
            manifest = self._read_manifest(root)
            result = self._terminal_result(root, manifest) if manifest else None
            if result and result.get("failure"):
                contents += f"\nDetached execution: {result['failure']}\n".encode()
        except (OSError, ValueError, TypeError, KeyError):
            # An uncertain result is not an alternative source of job streams.
            pass
        return contents

    def clean(self, job_id):
        root = self._root(job_id)
        with self._pool_lock():
            if not root.exists():
                return
            manifest = self._read_manifest(root)
            if manifest is None:
                return
            worker.atomic_json(root / CLEAN_FILE, self._base_record(manifest))
            self._maybe_clean_locked(root, manifest)

    def acknowledge_collection(self, job_id):
        """Confirm the client committed collected outputs; repeated calls are safe."""
        root = self._root(job_id)
        with self._pool_lock():
            if not root.exists():
                return True
            manifest = self._read_manifest(root)
            if manifest is None or self._terminal_result(root, manifest) is None:
                return False
            worker.atomic_json(root / ACK_FILE, self._base_record(manifest))
            self._maybe_clean_locked(root, manifest)
            return True

    def _maybe_clean_locked(self, root, manifest):
        if (
            self._terminal_result(root, manifest) is not None
            and self._record(root, CLEAN_FILE, manifest)
            and self._record(root, ACK_FILE, manifest)
        ):
            super().clean(manifest["job_id"])

    def shutdown(self, timeout=None):
        self._shutdown.set()
        self._housekeeper.join(timeout)
