"""Thin CLI adapter for the independent EngageQueue executor."""

import hashlib
import json
import shlex
from pathlib import Path
from string import Template

from ..job import (
    BaseJobExec,
    job_states,
)


class EngageQueue(BaseJobExec):
    """Submit prepared scripts; EngageQueue owns their execution lifetime."""

    idempotent_submission = True
    confirms_cancellation = True

    def _command(self, *arguments):
        state_dir = self.params.get("state_dir")
        if not state_dir:
            raise ValueError("EngageQueue requires job_state_dir on persistent local storage")
        command = [
            self.params.get("executable", "engagequeue"), "--state-dir", str(state_dir),
            "--execution-mode", "local",
            *[str(value) for value in arguments],
        ]
        if str(self.params.get("attach_only", False)).lower() == "true":
            command.insert(3, "--attach-only")
        return " ".join(shlex.quote(value) for value in command)

    @staticmethod
    def submission_key(script_file):
        # queued_cli selects UUID setup directories for idempotent executors.
        # A new Pulsar setup is a new attempt; transport retries reuse its key.
        path = str(Path(script_file).resolve()).encode()
        return "pulsar:" + hashlib.sha256(path).hexdigest()

    def job_script_kwargs(self, ofile, efile, job_name):
        self.stdout = ofile
        self.stderr = efile
        return {}

    def submit(self, script_file):
        state_dir = self.params.get("state_dir")
        if state_dir:
            marker = Path(str(state_dir)).expanduser().resolve() / "managed.json"
            if marker.exists() or marker.is_symlink():
                raise ValueError("Pulsar's EngageQueue adapter requires local state, not a managed Docker profile")
        arguments = [
            "submit", "--key", self.submission_key(script_file),
            "--pool", self.params.get("pool", "default"),
            "--cwd", str(Path(script_file).resolve().parent),
        ]
        for option in ("stdout", "stderr"):
            value = getattr(self, option, None)
            if value:
                arguments.extend(["--" + option, value])
        for option in ("timeout", "output_limit", "memory_mb", "cpus", "container_spec"):
            if self.params.get(option) is not None:
                value = self.params[option]
                if option == "container_spec":
                    directory = Path(script_file).resolve().parent
                    value = Template(str(value)).safe_substitute(job_directory=str(directory), job_id=directory.name)
                    value = str(directory / value) if not Path(value).is_absolute() else value
                arguments.extend(["--" + option.replace("_", "-"), value])
        if str(self.params.get("require_hard_limits", False)).lower() == "true":
            arguments.append("--require-hard-limits")
        arguments.extend(["--", "/bin/bash", str(Path(script_file).resolve())])
        return self._command(*arguments)

    def recover_submission(self, script_file):
        return self._command("lookup", self.submission_key(script_file))

    @staticmethod
    def submission_missing(result):
        return result.returncode == 3

    @staticmethod
    def parse_return_code(contents):
        value = json.loads(contents).get("returncode")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def delete(self, job_id):
        arguments = ["cancel", job_id]
        if str(self.params.get("cancel_wait", False)).lower() == "true":
            arguments.extend(["--wait", "--timeout", self.params.get("cancel_timeout", 120)])
        return self._command(*arguments)

    def get_status(self, job_ids=None):
        return self._command("list", "--json")

    def get_single_status(self, job_id):
        return self._command("status", job_id, "--json")

    @staticmethod
    def _state(record):
        return {
            "QUEUED": job_states.QUEUED,
            "STARTING": job_states.QUEUED,
            "RUNNING": job_states.RUNNING,
            "STOPPING": job_states.RUNNING,
            # LOST needs operator reconciliation and cannot authorize cleanup.
            "LOST": job_states.RUNNING,
            "SUCCEEDED": job_states.OK,
            "FAILED": job_states.ERROR,
            "CANCELLED": job_states.ERROR,
        }[record["state"]]

    def parse_status(self, status, job_ids):
        return {
            record["id"]: self._state(record)
            for record in json.loads(status)
            if job_ids is None or record["id"] in job_ids
        }

    def parse_single_status(self, status, job_id):
        record = json.loads(status)
        if record["id"] != job_id:
            raise ValueError("EngageQueue returned a different execution identity")
        return self._state(record)


__all__ = ("EngageQueue",)
