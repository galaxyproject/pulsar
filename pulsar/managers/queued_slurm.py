"""
Pulsar job manager for Slurm that reports why a job failed.

DRMAA only says that a job failed, so the job's Slurm state is consulted to
tell Galaxy if a memory or time limit was the cause.
"""

import logging
import time
from typing import (
    cast,
    Dict,
    Optional,
    TYPE_CHECKING,
)

from pulsar.managers import status
from .queued_drmaa import DrmaaQueueManager
from .util import runner_states
from .util.slurm import (
    check_memory_limit,
    NOT_FOUND,
    slurm_job_info,
)

if TYPE_CHECKING:
    from pulsar.core import PulsarApp
    from pulsar.managers.status import StateLiteral

log = logging.getLogger(__name__)

# How long to wait for a failed job to leave COMPLETING before reporting the
# failure without a cause, Slurm may keep a job on a bad node there indefinitely.
COMPLETING_TIMEOUT_SECONDS = 120

SLURM_STATE_TO_RUNNER_STATE = {
    "TIMEOUT": runner_states.WALLTIME_REACHED,
    "OUT_OF_MEMORY": runner_states.MEMORY_LIMIT_REACHED,
    "NODE_FAIL": runner_states.NODE_FAILURE,
    "BOOT_FAIL": runner_states.NODE_FAILURE,
    "PREEMPTED": runner_states.PREEMPTED,
}


class SlurmQueueManager(DrmaaQueueManager):
    """
    DRMAA backed queue manager for Slurm clusters.
    """

    manager_type = "queued_slurm"

    def __init__(self, name: str, app: "PulsarApp", **kwds):
        super().__init__(name, app, **kwds)
        self._completing_since: Dict[str, float] = {}

    def get_status(self, job_id: str) -> "StateLiteral":
        job_status = super().get_status(job_id)
        if job_status != status.FAILED:
            return job_status
        external_id = self._external_id(job_id)
        assert external_id is not None
        try:
            slurm_info = slurm_job_info(external_id)
        except Exception:
            log.exception("Failed to determine Slurm state of failed job %s", job_id)
            return job_status
        slurm_state = slurm_info["JobState"]
        if slurm_state in ("COMPLETED", NOT_FOUND):
            # DRMAA loses track of jobs that exceed MinJobAge and reports them as failed.
            log.debug("Job %s was reported failed by DRMAA but Slurm state is %s, completing as successful", job_id, slurm_state)
            return cast("StateLiteral", status.COMPLETE)
        if slurm_state in ("PENDING", "RUNNING") or self.__wait_for_completing(job_id, slurm_state):
            return cast("StateLiteral", status.RUNNING)
        runner_state = self.__classify_failure(job_id, slurm_state)
        log.info("Job %s failed with Slurm state %s (runner state: %s)", job_id, slurm_state, runner_state)
        self._record_runner_state(job_id, runner_state, self.__failure_message(slurm_info))
        return job_status

    def _deactivate_job(self, job_id: str) -> None:
        super()._deactivate_job(job_id)
        self._completing_since.pop(job_id, None)

    def __wait_for_completing(self, job_id: str, slurm_state: str) -> bool:
        """Slurm only settles on why a job ended after it has left COMPLETING."""
        if slurm_state != "COMPLETING":
            return False
        completing_since = self._completing_since.setdefault(job_id, time.monotonic())
        return time.monotonic() - completing_since < COMPLETING_TIMEOUT_SECONDS

    def __classify_failure(self, job_id: str, slurm_state: str) -> Optional[str]:
        if slurm_state == "CANCELLED":
            # Jobs cancelled through Pulsar never get here, so this came from outside of Galaxy.
            if check_memory_limit(self._job_stderr_path(job_id)):
                return runner_states.MEMORY_LIMIT_REACHED
            return runner_states.CANCELLED
        return SLURM_STATE_TO_RUNNER_STATE.get(slurm_state)

    @staticmethod
    def __failure_message(slurm_info: Dict[str, str]) -> Optional[str]:
        reason = slurm_info.get("Reason", "")
        return f"Slurm reported: {reason}" if reason.startswith("RaisedSignal") else None


__all__ = ("SlurmQueueManager",)
