from logging import getLogger
from os import stat
from os.path import exists
from typing import TYPE_CHECKING, cast, Dict, List, Optional

if TYPE_CHECKING:
    from galaxy.tools.deps.dependencies import DependencyDescription
    from pulsar.core import PulsarApp
    from pulsar.managers.status import StateLiteral

from .base.external import ExternalBaseManager
from .util.condor import (
    build_submit_description,
    condor_stop,
    condor_submit,
    submission_params,
    summarize_condor_log,
)
from ..managers import status

log = getLogger(__name__)


class CondorQueueManager(ExternalBaseManager):
    """
    Job manager backend that plugs into Condor.
    """

    manager_type = "queued_condor"

    def __init__(self, name: str, app: "PulsarApp", **kwds):
        super().__init__(name, app, **kwds)
        self.submission_params = submission_params(**kwds)
        self.user_log_sizes: Dict[str, int] = {}
        self.state_cache: Dict[str, "StateLiteral"] = {}

    def launch(
        self,
        job_id: str,
        command_line: str,
        submit_params: Dict[str, str] = {},
        dependencies_description: Optional["DependencyDescription"] = None,
        env: List[Dict[str, str]] = [],
        setup_params: Optional[Dict[str, str]] = None,
    ) -> None:
        self._check_execution_with_tool_file(job_id, command_line)
        job_file_path = self._setup_job_file(
            job_id,
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            setup_params=setup_params,
        )
        log_path = self.__condor_user_log(job_id)
        open(log_path, "w")  # Touch log file

        submit_params.update(self.submission_params)
        build_submit_params = dict(
            executable=job_file_path,
            output=self._job_stdout_path(job_id),
            error=self._job_stderr_path(job_id),
            user_log=log_path,
            query_params=submit_params,
        )
        submit_file_contents = build_submit_description(**build_submit_params)
        submit_file = self._write_job_file(
            job_id, "job.condor.submit", submit_file_contents
        )
        external_id, message = condor_submit(submit_file)
        if not external_id:
            raise Exception(message)
        self._register_external_id(job_id, external_id)

    def __condor_user_log(self, job_id: str) -> str:
        return self._job_file(job_id, "job_condor.log")

    def _kill_external(self, external_id: str) -> None:
        failure_message = condor_stop(external_id)
        if failure_message:
            log.warn(
                "Failed to stop condor job with id {} - {}".format(
                    external_id, failure_message
                )
            )

    def get_status(self, job_id: str) -> "StateLiteral":
        external_id = self._external_id(job_id)
        if not external_id:
            raise Exception(
                "Failed to obtain external_id for job_id %s, cannot determine status."
                % job_id
            )
        log_path = self.__condor_user_log(job_id)
        if not exists(log_path):
            return cast("StateLiteral", status.COMPLETE)
        if external_id not in self.user_log_sizes:
            self.user_log_sizes[external_id] = -1
            self.state_cache[external_id] = cast("StateLiteral", status.QUEUED)
        log_size = stat(log_path).st_size
        if log_size == self.user_log_sizes[external_id]:
            return self.state_cache[external_id]
        return self.__get_state_from_log(external_id, log_path)

    # TODO is there a better way than cast("StateLiteral", ...) which I do at a few places?
    def __get_state_from_log(self, external_id: str, log_file: str) -> "StateLiteral":
        s1, s4, s7, s5, s9, log_size = summarize_condor_log(log_file, external_id)
        if s5 or s9:
            state = cast("StateLiteral", status.COMPLETE)
        elif s1 or s4 or s7:
            state = cast("StateLiteral", status.RUNNING)
        else:
            state = cast("StateLiteral", status.QUEUED)
        self.user_log_sizes[external_id] = log_size
        self.state_cache[external_id] = state
        return state

    def _deactivate_job(self, job_id: str) -> None:
        external_id = self._external_id(job_id)
        self.user_log_sizes.pop(external_id, None)
        self.state_cache.pop(external_id, None)
        super()._deactivate_job(job_id)
