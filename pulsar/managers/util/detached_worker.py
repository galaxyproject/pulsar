"""Durable local execution supervision without Galaxy or Pulsar imports.

This file is copied into each job directory.  A small gated child records its
identity before it can execute the native Galaxy script.  Its separate exit
record lets a replacement supervisor recover a command that completed while
the original supervisor was unavailable.  Neither recovery nor a repeated
launch is permission to execute an already claimed command again.
"""

import argparse
import fcntl
import json
import math
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import (
    error as urlerror,
    request as urlrequest,
)

import psutil

MANIFEST_FILE = ".pulsar-detached-manifest.json"
LIVE_FILE = ".pulsar-detached-live.json"
RESULT_FILE = ".pulsar-detached-result.json"
STOP_FILE = ".pulsar-detached-stop.json"
WORKER_FILE = ".pulsar-detached-worker.py"
COMMAND_FILE = ".pulsar-detached-command.json"
START_FILE = ".pulsar-detached-start.json"
EXIT_FILE = ".pulsar-detached-exit.json"
WORKER_LOCK_FILE = ".pulsar-detached-worker.lock"
COMMAND_LOCK_FILE = ".pulsar-detached-command.lock"


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def atomic_json(path, data):
    path = Path(path)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(data, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _open_output(path):
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
    )
    try:
        os.fchmod(descriptor, 0o600)
        return os.fdopen(descriptor, "ab", buffering=0)
    except BaseException:
        os.close(descriptor)
        raise


def host_identity():
    """Identify the host and boot; saved PIDs never cross this boundary."""
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        boot_id = str(psutil.boot_time())
    return {"hostname": socket.gethostname(), "boot_id": boot_id}


def process_identity(pid):
    process = psutil.Process(int(pid))
    return {"pid": process.pid, "creation_time": process.create_time()}


def identity_alive(identity):
    """Return True/False, or None when identity cannot safely be established."""
    if not identity:
        return False
    try:
        process = psutil.Process(int(identity["pid"]))
        if abs(process.create_time() - float(identity["creation_time"])) > 0.01:
            return False
        return process.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, KeyError, TypeError, ValueError):
        return None


def _belongs(record, manifest):
    return (
        isinstance(record, dict)
        and record.get("job_id") == manifest["job_id"]
        and record.get("token") == manifest["token"]
    )


def _record(root, name, manifest):
    record = read_json(root / name)
    if record is not None and not _belongs(record, manifest):
        raise ValueError(f"Detached {name} does not belong to this execution")
    return record


def _base_record(manifest):
    return {"schema": 1, "job_id": manifest["job_id"], "token": manifest["token"]}


def _validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise ValueError("Unsupported detached manifest schema")
    if not isinstance(manifest.get("job_id"), str) or not manifest["job_id"]:
        raise ValueError("Detached job ID must be a nonempty string")
    token = manifest.get("token")
    if (
        not isinstance(token, str)
        or len(token) != 32
        or any(char not in "0123456789abcdef" for char in token)
    ):
        raise ValueError("Detached execution token must be a UUID hex string")
    for key in ("job_directory", "command_script", "stdout", "stderr"):
        if not isinstance(manifest.get(key), str) or not os.path.isabs(manifest[key]):
            raise ValueError(f"Detached {key} must be an absolute path")
    environment = manifest.get("environment")
    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise ValueError("Detached environment must contain string names and values")
    for name, default, allow_zero in (
        ("cancel_grace_seconds", 10, True),
        ("poll_interval", 0.5, False),
    ):
        raw = manifest.get(name, default)
        if isinstance(raw, bool):
            raise ValueError(f"Detached {name} must be a finite number")
        value = float(raw)
        if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
            raise ValueError(f"Detached {name} must be nonnegative/positive")
    if not isinstance(manifest.get("host_identity"), dict) or not all(
        isinstance(manifest["host_identity"].get(key), str)
        and manifest["host_identity"][key]
        for key in ("hostname", "boot_id")
    ):
        raise ValueError("Detached host identity is required")
    if "working_directory" in manifest and not os.path.isabs(
        manifest["working_directory"]
    ):
        raise ValueError("Detached working_directory must be absolute")
    for container in manifest.get("containers", []):
        if (
            container.get("container_type") != "docker"
            or not isinstance(container.get("container_name"), str)
            or not container["container_name"]
            or not isinstance(container.get("connection_configuration", {}), dict)
            or not container.get("expected_mount")
        ):
            raise ValueError(
                "Detached container descriptors require Docker name, connection, and expected mount"
            )
    _validate_limits(manifest.get("limits", {}))


def _validate_limits(limits):
    for key in ("walltime_seconds", "output_size_bytes", "output_directory_size_bytes"):
        value = limits.get(key)
        if value is not None and (
            isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) <= 0
        ):
            raise ValueError(f"Detached {key} must be finite and positive")
    directory = limits.get("output_directory")
    aggregate_limit = limits.get("output_directory_size_bytes")
    if (directory is None) != (aggregate_limit is None):
        raise ValueError(
            "Detached output_directory and output_directory_size_bytes must be supplied together"
        )
    if directory is not None and (
        not isinstance(directory, str) or not os.path.isabs(directory)
    ):
        raise ValueError("Detached output_directory must be an absolute path")


def docker_command(configuration, *arguments):
    prefix = []
    if configuration.get("sudo"):
        prefix.append(configuration.get("sudo_cmd") or "sudo")
    prefix.append(configuration.get("docker_cmd") or "docker")
    if configuration.get("host"):
        prefix.extend(["-H", configuration["host"]])
    return prefix + list(arguments)


def call_docker(configuration, *arguments, timeout=10):
    return subprocess.run(
        docker_command(configuration, *arguments),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def inspect_container(configuration, name, container_id=None, expected_mount=None):
    """Return state, immutable ID, and native inspect data, retaining uncertainty.

    A name alone cannot authorize signals. The expected job mount must match
    before an ID is adopted; all subsequent inspections still verify the name
    and mount. Daemon errors are not evidence that a container disappeared.
    """
    try:
        response = call_docker(
            configuration, "inspect", "--format", "{{json .}}", container_id or name
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown", container_id, None
    if response.returncode:
        if (
            "no such object:" in response.stderr.lower()
            or "no such container:" in response.stderr.lower()
        ):
            return "absent", container_id, None
        return "unknown", container_id, None
    try:
        info = json.loads(response.stdout)
        if isinstance(info, list):
            info = info[0]
        observed_id = info["Id"]
        if (
            not isinstance(observed_id, str)
            or not observed_id
            or info["Name"].lstrip("/") != name
        ):
            return "unknown", container_id, None
        if container_id and observed_id != container_id:
            return "unknown", container_id, None
        expected = (
            expected_mount
            if isinstance(expected_mount, dict)
            else {
                "source": expected_mount,
                "destination": expected_mount,
            }
        )
        if not expected.get("source") or not any(
            os.path.realpath(mount.get("Source", ""))
            == os.path.realpath(expected["source"])
            and mount.get("Destination")
            == expected.get("destination", expected["source"])
            and (
                "read_only" not in expected
                or mount.get("RW") is not bool(expected["read_only"])
            )
            for mount in info.get("Mounts", [])
        ):
            return "unknown", container_id, None
        state = info["State"]
        if state.get("Running") or state.get("Paused") or state.get("Restarting"):
            return "running", observed_id, info
        if state.get("Status") in ("created", "exited", "dead"):
            return state["Status"], observed_id, info
        # Removing is not terminal: the daemon still owns the mounted files.
        return "unknown", observed_id, info
    except (ValueError, KeyError, IndexError, TypeError):
        return "unknown", container_id, None


def output_size(paths):
    """Count actual outputs, without following directory or file symlinks."""
    size = 0
    seen = set()
    for raw in paths:
        path = Path(raw)
        if path.is_symlink():
            continue
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = (
                Path(root) / name
                for root, _, names in os.walk(path, followlinks=False)
                for name in names
            )
        else:
            continue
        for item in files:
            try:
                stat = item.lstat()
                if (
                    item.is_symlink()
                    or not item.is_file()
                    or (stat.st_dev, stat.st_ino) in seen
                ):
                    continue
                seen.add((stat.st_dev, stat.st_ino))
                size += stat.st_size
            except FileNotFoundError:
                continue
    return size


def exceeded_limit(manifest, started_at):
    limits = manifest.get("limits", {})
    if (
        limits.get("walltime_seconds")
        and started_at
        and time.time() - started_at >= float(limits["walltime_seconds"])
    ):
        return "walltime"
    # Galaxy's native output_size applies independently to every declared
    # output, not to the sum of all datasets produced by a job. Follow the
    # native stat behavior, including symlinked output files.
    if limits.get("output_size_bytes"):
        for path in limits.get("output_paths", []):
            try:
                size = os.stat(path).st_size
            except FileNotFoundError:
                continue
            if size > int(limits["output_size_bytes"]):
                return "output_size"
    # Aggregate directory enforcement is a separately named opt-in policy.
    if limits.get("output_directory_size_bytes") and output_size(
        [limits["output_directory"]]
    ) > int(limits["output_directory_size_bytes"]):
        return "output_directory_size"
    return None


def _entry_point_host(address, configuration):
    if address in ("::", "[::]"):
        return None
    if address != "0.0.0.0":
        return address
    method = configuration.get("get_ip_method")
    if method:
        kind, command = method.split(":", 1)
        if kind != "command":
            return None
        return subprocess.check_output(
            shlex.split(command), text=True, timeout=10
        ).strip()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("192.0.2.1", 1))
        return sock.getsockname()[0]


def publish_entry_points(manifest, snapshot, container_info):
    """Retry native port publication independently of Galaxy's process lifetime.

    The callback credential stays in the private manifest and is never logged.
    Successful or explicitly revoked publication is final and is not replayed.
    """
    if snapshot.get("entry_points_published") or snapshot.get("entry_points_revoked"):
        return
    configuration = manifest.get("entry_point_config")
    if isinstance(configuration, str):
        configuration = read_json(configuration)
    if not configuration:
        return
    info = container_info.get(configuration.get("container_name"))
    if not info:
        return
    ports = {}
    for key, bindings in info.get("NetworkSettings", {}).get("Ports", {}).items():
        tool_port, protocol = key.split("/", 1)
        if protocol != "tcp":
            continue
        for binding in bindings or []:
            address = _entry_point_host(binding["HostIp"], configuration)
            if address is None:
                continue
            ports[int(tool_port)] = {
                "tool_port": int(tool_port),
                "host": address,
                "port": int(binding["HostPort"]),
                "protocol": "http",
            }
    if not ports:
        return
    snapshot["entry_point_ports"] = ports
    callback = configuration.get("callback_url")
    if callback:
        try:
            request = urlrequest.Request(
                callback,
                data=json.dumps({"container_runtime": ports}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlrequest.urlopen(request, timeout=5) as response:
                if 200 <= response.status < 300:
                    snapshot["entry_points_published"] = True
        except urlerror.HTTPError as error:
            if error.code in (403, 410):
                snapshot["entry_points_revoked"] = True
        except (OSError, urlerror.URLError):
            pass
    else:
        atomic_json(Path(manifest["job_directory"]) / "container_runtime.json", ports)
        snapshot["entry_points_published"] = True


def command_group_status(identity, known_members=()):
    """Identify a dedicated command group, including surviving background writers.

    Once its leader exits, a previously observed member must establish group
    ownership.  A reused leader PID or an unrecognised group is retained rather
    than signalled or declared finished.
    """
    if not identity:
        return False, False, []
    leader_alive = identity_alive(identity)
    if leader_alive is None:
        return None, None, list(known_members)
    group_id = int(identity["pid"])
    try:
        current = process_identity(group_id)
    except psutil.NoSuchProcess:
        current = None
    except (psutil.AccessDenied, ValueError, TypeError):
        return leader_alive, None, list(known_members)
    if (
        current
        and abs(current["creation_time"] - float(identity["creation_time"])) > 0.01
    ):
        return False, None, list(known_members)
    members = []
    for process in psutil.process_iter():
        try:
            if os.getpgid(process.pid) != group_id or process.status() in (
                psutil.STATUS_ZOMBIE,
                psutil.STATUS_DEAD,
            ):
                continue
            members.append(process_identity(process.pid))
        except (psutil.NoSuchProcess, ProcessLookupError):
            continue
        except (psutil.AccessDenied, PermissionError):
            if (
                any(member["pid"] == process.pid for member in known_members)
                or process.pid == group_id
            ):
                return leader_alive, None, list(known_members)
    if not members:
        return leader_alive, None if leader_alive else False, []
    if leader_alive:
        return True, True, members
    known = any(
        member["pid"] == previous["pid"]
        and abs(member["creation_time"] - previous["creation_time"]) <= 0.01
        for member in members
        for previous in known_members
    )
    return False, True if known else None, members if known else list(known_members)


def signal_command(identity, signum, known_members=()):
    """Signal only a verified dedicated command group; never a bare saved PID."""
    leader_alive, group_alive, members = command_group_status(identity, known_members)
    if group_alive is not True:
        return
    pid = int(identity["pid"])
    try:
        if leader_alive is False:
            try:
                current = process_identity(pid)
                if abs(current["creation_time"] - identity["creation_time"]) > 0.01:
                    return
            except psutil.NoSuchProcess:
                pass
        if members:
            os.killpg(pid, signum)
    except ProcessLookupError:
        pass


def _command_gate(manifest):
    """Register before execution; require the supervisor's durable permission."""
    _validate_manifest(manifest)
    if manifest["host_identity"] != host_identity():
        return
    root = Path(manifest["job_directory"])
    with (root / COMMAND_LOCK_FILE).open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        # The claim remains after this process exits.  Taking its lock again
        # never grants permission to replay a previously claimed detached.
        if (
            _record(root, COMMAND_FILE, manifest) is not None
            or _record(root, EXIT_FILE, manifest) is not None
        ):
            return
        identity = process_identity(os.getpid())
        command = {
            **_base_record(manifest),
            "command_identity": identity,
            "phase": "gated",
        }
        atomic_json(root / COMMAND_FILE, command)
        interrupted = False

        def on_term(signum, frame):
            nonlocal interrupted
            interrupted = True

        # TERM reaches the native shell through the group.  Keep this recorder
        # alive long enough to persist its child's return code when possible.
        signal.signal(signal.SIGTERM, on_term)
        interval = float(manifest.get("poll_interval", 0.5))
        while True:
            stop = _record(root, STOP_FILE, manifest)
            grant = _record(root, START_FILE, manifest)
            if stop is not None or interrupted:
                code = 143
                break
            if grant is not None and grant.get("execution") is True:
                live = _record(root, LIVE_FILE, manifest)
                if live is None or live.get("command_identity") != identity:
                    raise ValueError(
                        "Detached command identity was not durably acknowledged"
                    )
                command.update(phase="executing", started_at=time.time())
                atomic_json(root / COMMAND_FILE, command)
                try:
                    with _open_output(manifest["stdout"]) as stdout:
                        with _open_output(manifest["stderr"]) as stderr:
                            process = subprocess.Popen(
                                [manifest["command_script"]],
                                cwd=manifest.get("working_directory", str(root)),
                                stdin=subprocess.DEVNULL,
                                stdout=stdout,
                                stderr=stderr,
                                env=manifest["environment"],
                            )
                            code = process.wait()
                except OSError as error:
                    code = 127
                    command["failure"] = (
                        f"Cannot execute native detached script: {type(error).__name__}"
                    )
                break
            time.sleep(interval)
        # Include group members that might otherwise be reparented after the
        # leader exits, before the supervisor's next observation.
        _, _, members = command_group_status(identity, [identity])
        atomic_json(
            root / EXIT_FILE,
            {
                **_base_record(manifest),
                "command_identity": identity,
                "command_members": members,
                "return_code": code,
                "stopped": bool(_record(root, STOP_FILE, manifest)) or interrupted,
                "failure": command.get("failure"),
                "finished_at": time.time(),
            },
        )


def _observe_command(root, manifest, snapshot):
    command = _record(root, COMMAND_FILE, manifest)
    if command:
        identity = command.get("command_identity")
        if snapshot["command_identity"] and snapshot["command_identity"] != identity:
            raise ValueError("Detached command identity changed after launch")
        snapshot["command_identity"] = identity
        snapshot["launch_intent"] = True
        if command.get("started_at"):
            snapshot["started_at"] = command["started_at"]
    exit_record = _record(root, EXIT_FILE, manifest)
    if exit_record:
        if exit_record.get("command_identity") != snapshot["command_identity"]:
            raise ValueError("Detached command exit belongs to a different process")
        snapshot["command_members"] = [
            *snapshot["command_members"],
            *exit_record.get("command_members", []),
        ]
    return exit_record


def _observe_containers(manifest, snapshot):
    container_states = {}
    container_info = {}
    for descriptor in manifest.get("containers", []):
        name = descriptor["container_name"]
        state, container_id, info = inspect_container(
            descriptor.get("connection_configuration", {}),
            name,
            snapshot["container_identities"].get(name),
            descriptor["expected_mount"],
        )
        container_states[name] = state
        if container_id:
            snapshot["container_identities"][name] = container_id
        if info:
            container_info[name] = info
    return container_states, container_info


def _stop_containers(
    manifest,
    snapshot,
    container_states,
    group_alive,
    last_container_action,
    interval,
    grace,
    publish,
):
    for descriptor in manifest.get("containers", []):
        name = descriptor["container_name"]
        state = container_states[name]
        container_id = snapshot["container_identities"].get(name)
        if not container_id or state not in ("running", "created"):
            continue
        if snapshot["termination_started"] is None:
            publish(termination_started=time.time())
        if time.time() - last_container_action.get(name, 0) < max(interval, 1):
            continue
        last_container_action[name] = time.time()
        configuration = descriptor.get("connection_configuration", {})
        try:
            if state == "created" and group_alive is False:
                call_docker(configuration, "rm", container_id)
            elif state == "running":
                elapsed = time.time() - snapshot["termination_started"]
                if elapsed < grace:
                    # Nonblocking daemon stop: continue polling the wrapper,
                    # limits, and every owned tool/metadata container.
                    call_docker(configuration, "kill", "--signal", "TERM", container_id)
                else:
                    call_docker(configuration, "kill", container_id)
        except (OSError, subprocess.SubprocessError):
            pass


def _grant_execution(root, manifest, snapshot, exit_record, stop, publish):
    identity = snapshot["command_identity"]
    if identity and _record(root, START_FILE, manifest) is None and exit_record is None:
        # Persist the exact child identity before granting execution.
        publish(phase="gated")
        if stop is None:
            atomic_json(
                root / START_FILE, {**_base_record(manifest), "execution": True}
            )


def supervise(manifest, recover=False):
    root = Path(manifest["job_directory"])
    previous = _record(root, LIVE_FILE, manifest) or {}
    command = _record(root, COMMAND_FILE, manifest)
    snapshot = {
        **_base_record(manifest),
        "worker_identity": process_identity(os.getpid()),
        "command_identity": (command or {}).get("command_identity")
        or previous.get("command_identity"),
        "command_members": previous.get("command_members", []),
        "launch_intent": bool(previous.get("launch_intent") or command),
        "termination_started": previous.get("termination_started"),
        "container_identities": previous.get("container_identities", {}),
        "entry_points_published": previous.get("entry_points_published", False),
        "entry_points_revoked": previous.get("entry_points_revoked", False),
        "entry_point_ports": previous.get("entry_point_ports"),
        "started_at": previous.get("started_at"),
        "phase": "recovering" if recover or previous else "starting",
        "updated_at": time.time(),
    }

    def publish(**changes):
        snapshot.update(changes, updated_at=time.time())
        atomic_json(root / LIVE_FILE, snapshot)

    def finish(code, stopped, failure=None):
        result = {
            **_base_record(manifest),
            "return_code": code,
            "returncode": code,
            "stopped": stopped,
            "command_exit_confirmed": True,
            "container_exit_confirmed": True,
            "container_identities": snapshot["container_identities"],
            "command_identity": snapshot["command_identity"],
            "finished_at": time.time(),
        }
        if failure:
            result["failure"] = failure
        publish(phase="finished")
        # Galaxy may remove the directory as soon as it collects this record.
        # Publishing it is the supervisor's final filesystem operation.
        atomic_json(root / RESULT_FILE, result)
        return code

    publish()
    interval = float(manifest.get("poll_interval", 0.5))
    grace = float(manifest.get("cancel_grace_seconds", 10))
    proc = None
    last_container_action = {}
    last_publication = 0
    while True:
        stop = _record(root, STOP_FILE, manifest)
        exit_record = _observe_command(root, manifest, snapshot)

        if not snapshot["launch_intent"]:
            if stop is not None:
                return finish(143, True)
            # This intent survives a fork window.  If no child ever registers,
            # recovery retains the job instead of risking duplicate execution.
            publish(phase="starting_command", launch_intent=True)
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    str(root / MANIFEST_FILE),
                    "--command-gate",
                ],
                cwd=root,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            continue

        identity = snapshot["command_identity"]
        _grant_execution(root, manifest, snapshot, exit_record, stop, publish)

        if identity:
            leader_alive, group_alive, members = command_group_status(
                identity, snapshot["command_members"]
            )
            snapshot["command_members"] = members
        else:
            leader_alive, group_alive = None, None

        if proc is not None:
            proc.poll()  # Reap this worker's gated child once it exits.

        limit = exceeded_limit(manifest, snapshot["started_at"])
        if limit and stop is None:
            stop = {
                **_base_record(manifest),
                "reason": limit,
                "requested_at": time.time(),
            }
            atomic_json(root / STOP_FILE, stop)
        container_states, container_info = _observe_containers(manifest, snapshot)

        ending = stop is not None or exit_record is not None or leader_alive is False
        if not ending and time.time() - last_publication >= max(interval, 1):
            last_publication = time.time()
            try:
                publish_entry_points(manifest, snapshot, container_info)
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                subprocess.SubprocessError,
            ):
                # Malformed/unavailable bindings cannot authorize job cleanup.
                # A subsequent successful inspect/publication may recover.
                pass
        if ending:
            _stop_containers(
                manifest,
                snapshot,
                container_states,
                group_alive,
                last_container_action,
                interval,
                grace,
                publish,
            )
        if ending and group_alive is True:
            if snapshot["termination_started"] is None:
                publish(
                    phase="stopping" if stop else "reaping",
                    termination_started=time.time(),
                )
            signum = (
                signal.SIGKILL
                if time.time() - snapshot["termination_started"] >= grace
                else signal.SIGTERM
            )
            signal_command(identity, signum, snapshot["command_members"])
        containers_exited = all(
            state in ("absent", "exited", "dead") for state in container_states.values()
        )
        if group_alive is False and containers_exited:
            if exit_record is not None:
                failure = (
                    f"Execution exceeded {stop['reason']} limit"
                    if stop
                    and stop.get("reason")
                    in ("walltime", "output_size", "output_directory_size")
                    else exit_record.get("failure")
                )
                return finish(
                    int(exit_record["return_code"]), stop is not None, failure
                )
            code = (proc.returncode if proc is not None else None) or (
                143 if stop else 1
            )
            return finish(
                code,
                stop is not None,
                None if stop else "Native command ended without an exit record",
            )
        publish(
            phase=(
                "retained"
                if group_alive is None or "unknown" in container_states.values()
                else ("stopping" if stop else "running")
            ),
            container_states=container_states,
        )
        time.sleep(interval)


def run(manifest, recover=False):
    _validate_manifest(manifest)
    root = Path(manifest["job_directory"])
    with (root / WORKER_LOCK_FILE).open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        if manifest["host_identity"] != host_identity():
            atomic_json(
                root / LIVE_FILE,
                {
                    **(_record(root, LIVE_FILE, manifest) or {}),
                    **_base_record(manifest),
                    "phase": "retained",
                    "worker_identity": process_identity(os.getpid()),
                    "failure": "Execution host or boot identity differs; saved processes will not be signalled or replayed",
                    "updated_at": time.time(),
                },
            )
            return 0
        result = _record(root, RESULT_FILE, manifest)
        if result is not None:
            if (
                result.get("command_exit_confirmed") is not True
                or result.get("container_exit_confirmed") is not True
            ):
                raise ValueError("Detached result has no terminal process proof")
            return int(result["return_code"])
        return supervise(manifest, recover=recover)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--recover", action="store_true")
    mode.add_argument("--command-gate", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    manifest = read_json(args.manifest)
    _validate_manifest(manifest)
    if args.command_gate:
        _command_gate(manifest)
    else:
        run(manifest, recover=args.recover)


if __name__ == "__main__":
    main()
