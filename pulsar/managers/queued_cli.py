"""
Pulsar job manager that uses a CLI interface to a job queue (e.g. Torque's qsub,
qstat, etc...).
"""

from logging import getLogger
from typing import (
    cast,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
)

from pulsar.managers import (
    PULSAR_UNKNOWN_RETURN_CODE,
    status,
)
from pulsar.managers.util.env import EnvVar
from .base.external import ExternalBaseManager
from .util.cli import (
    CliInterface,
    split_params,
)
from .util.cli.job import job_states
from .util.external import (
    parse_external_id,
    SubmissionUncertain,
)
from .util.job_script import job_script

if TYPE_CHECKING:
    from galaxy.tool_util.deps.dependencies import DependenciesDescription

    from pulsar.core import PulsarApp
    from pulsar.managers.status import StateLiteral

log = getLogger(__name__)

# Translate the CLI plugins' job states into the Pulsar status vocabulary the
# stateful manager understands. The CLI plugins are shared with Galaxy, so
# job_states resolves to galaxy.model.Job.states when Galaxy is importable
# (OK == 'ok', ERROR == 'error') and to Pulsar's local fallback enum otherwise
# (OK == 'complete', ERROR == 'failed'). Keying on the enum member rather than
# its string value keeps this correct under both bindings. Mirrors the
# JobState -> status mapping in base/base_drmaa.py.
_CLI_STATE_TO_STATUS = {
    job_states.OK: status.COMPLETE,
    job_states.RUNNING: status.RUNNING,
    job_states.QUEUED: status.QUEUED,
    job_states.ERROR: status.FAILED,
}


class CliQueueManager(ExternalBaseManager):
    manager_type = "queued_cli"

    def __init__(self, name: str, app: "PulsarApp", **kwds):
        if kwds.get("job_plugin") == "EngageQueue":
            kwds.setdefault("assign_ids", "uuid")
        super().__init__(name, app, **kwds)
        self.cli_interface = CliInterface()
        self.shell_params, self.job_params = split_params(kwds)

    @property
    def recoverable_submission(self):
        if not self.job_params.get("plugin"):
            return False
        _, job_interface = self.__get_cli_plugins()
        return bool(getattr(job_interface, "idempotent_submission", False))

    def launch(
        self,
        job_id: str,
        command_line: str,
        submit_params: Dict[str, str] = {},
        dependencies_description: Optional["DependenciesDescription"] = None,
        env: List[EnvVar] = [],
        setup_params: Optional[Dict[str, str]] = None,
    ) -> None:
        self._check_execution_with_tool_file(job_id, command_line)
        shell, job_interface = self.__get_cli_plugins()
        if getattr(job_interface, "idempotent_submission", False):
            # Resource requests may vary per job. Connection/identity settings
            # remain manager configuration, never untrusted submit overrides.
            for name in ("cpus", "memory_mb", "timeout", "output_limit"):
                if name in submit_params:
                    job_interface.params[name] = submit_params[name]
        stdout_path = self._job_stdout_path(job_id)
        stderr_path = self._job_stderr_path(job_id)
        job_name = self._job_name(job_id)
        command_line = self._expand_command_line(
            job_id,
            command_line,
            dependencies_description,
            job_directory=self.job_directory(job_id).job_directory,
        )
        job_script_kwargs = self._job_template_env(
            job_id, command_line=command_line, env=env, setup_params=setup_params
        )
        extra_kwargs = job_interface.job_script_kwargs(
            stdout_path, stderr_path, job_name
        )
        job_script_kwargs.update(extra_kwargs)
        script = job_script(**job_script_kwargs)
        script_path = self._write_job_script(job_id, script)
        submission_command = job_interface.submit(script_path)
        cmd_out = shell.execute(submission_command)
        if cmd_out.returncode != 0:
            if getattr(job_interface, "idempotent_submission", False):
                self._recover_active_job(job_id)
                return
            log.warning("Failed to submit job - command was:\n%s" % submission_command)
            raise Exception("Failed to submit job, error was:\n%s" % cmd_out.stderr)
        external_id = parse_external_id(cmd_out.stdout.strip())
        if not external_id:
            if getattr(job_interface, "idempotent_submission", False):
                self._recover_active_job(job_id)
                return
            message_template = (
                "Failed to obtain external id for job_id %s and submission_command %s"
            )
            message = message_template % (job_id, submission_command)
            log.warning(message)
            raise Exception("Failed to obtain external id")
        try:
            self._register_external_id(job_id, external_id)
        except Exception as exc:
            if getattr(job_interface, "idempotent_submission", False):
                raise SubmissionUncertain("Accepted scheduler ID could not be persisted") from exc
            raise

    def __get_cli_plugins(self):
        return self.cli_interface.get_plugins(self.shell_params, self.job_params)

    def _kill_external(self, external_id: str) -> None:
        shell, job_interface = self.__get_cli_plugins()
        kill_command = job_interface.delete(external_id)
        result = shell.execute(kill_command)
        if result.returncode:
            raise RuntimeError("Scheduler has not confirmed cancellation")

    def get_status(self, job_id: str) -> "StateLiteral":
        if not self.job_params.get("plugin"):
            return super().get_status(job_id)
        shell, job_interface = self.__get_cli_plugins()
        if not getattr(job_interface, "confirms_cancellation", False):
            return super().get_status(job_id)
        external_id = self._external_id(job_id)
        if not external_id:
            try:
                self._recover_active_job(job_id)
            except Exception:
                log.warning("Submission lookup remains uncertain for job %s; retaining queued status", job_id, exc_info=True)
                return cast("StateLiteral", status.QUEUED)
            external_id = self._external_id(job_id)
        if not external_id:
            return cast("StateLiteral", status.QUEUED)
        if self._was_cancelled(job_id):
            # kill() may precede accepted-ID recovery or lose its transport
            # response. The durable intent remains pending until the executor
            # confirms stopped writers; its cancel operation is idempotent.
            try:
                self._kill_external(external_id)
            except Exception:
                log.warning("Cancellation delivery failed for job %s; polling will retry", job_id, exc_info=True)
        try:
            command = job_interface.get_single_status(external_id)
            result = shell.execute(command)
            if result.returncode:
                log.warning("Execution status remains uncertain for job %s; retaining running status", job_id)
                return cast("StateLiteral", status.RUNNING)
            state = job_interface.parse_single_status(result.stdout, external_id)
        except Exception:
            log.warning("Execution status remains uncertain for job %s; retaining running status", job_id, exc_info=True)
            return cast("StateLiteral", status.RUNNING)
        if state in (job_states.OK, job_states.ERROR):
            return_code = job_interface.parse_return_code(result.stdout)
            if return_code:
                previous = self.return_code(job_id)
                if not previous or previous == PULSAR_UNKNOWN_RETURN_CODE:
                    # A prepared script may have returned zero while an owned
                    # background container was still running. Its later
                    # cancellation/resource failure cannot remain a success.
                    self._write_job_file(job_id, "return_code", str(return_code))
        if self._was_cancelled(job_id) and state in (job_states.OK, job_states.ERROR):
            return cast("StateLiteral", status.CANCELLED)
        return cast("StateLiteral", _CLI_STATE_TO_STATUS.get(state, state))

    def _recover_active_job(self, job_id: str) -> None:
        try:
            super()._recover_active_job(job_id)
            return
        except Exception:
            shell, job_interface = self.__get_cli_plugins()
            recovery = getattr(job_interface, "recover_submission", None)
            if recovery is None:
                raise
        # Lookup only: an uncertain accepted submission must never be replayed.
        result = shell.execute(recovery(self._job_file(job_id, "command.sh")))
        external_id = parse_external_id(result.stdout.strip()) if result.returncode == 0 else None
        if not external_id:
            if job_interface.submission_missing(result):
                # The original submit process can survive its controller and
                # accept later. Absence now does not prove it is quiescent.
                raise SubmissionUncertain("No accepted execution is visible yet; the original submission may still complete")
            raise SubmissionUncertain("Unable to resolve the scheduler's accepted submission")
        try:
            self._register_external_id(job_id, external_id)
        except Exception as exc:
            raise SubmissionUncertain("Recovered scheduler ID could not be persisted") from exc

    def _get_status_external(self, external_id: str) -> "StateLiteral":
        shell, job_interface = self.__get_cli_plugins()
        status_command = job_interface.get_single_status(external_id)
        cmd_out = shell.execute(status_command)
        state = job_interface.parse_single_status(cmd_out.stdout, external_id)
        return cast("StateLiteral", _CLI_STATE_TO_STATUS.get(state, state))
