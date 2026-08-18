"""Job manager backed by HTCondor via the htcondor2 Python bindings.

The HTCondor mechanics are shared with Galaxy's ``htcondor`` job runner and
live in :mod:`pulsar.managers.util.condor.htcondor`; this module maps that
vocabulary onto Pulsar's job status vocabulary.

Unlike :mod:`pulsar.managers.queued_condor` this manager never shells out to
``condor_submit``/``condor_rm`` and reads the job event log through
``htcondor2.JobEventLog`` rather than by scraping the log's text.
"""
import logging
import threading
import time

from .base.external import ExternalBaseManager
from .util.condor import (
    build_submit_description,
    submission_params,
)
from .util.condor.htcondor import (
    classify_failure_event,
    classify_hold,
    DEFAULT_MAX_HELD_COUNT,
    FAILURE_MESSAGES,
    HOLD_MESSAGES,
    HOLD_REASON_MEMORY_LIMIT,
    HOLD_REASON_WALLTIME,
    HTCondorClientCache,
    HTCondorEventLogTracker,
    held_message,
    import_htcondor,
    MISSING_LOG_GRACE_SECONDS,
    MISSING_LOG_MESSAGE,
    normalize_condor_config,
    parse_walltime_seconds,
    periodic_hold_expression,
    STATUS_ERROR_GRACE_SECONDS,
)
from ..managers import status

log = logging.getLogger(__name__)

HTCONDOR_REMOVE_REASON = "Pulsar job stop request"

# The escalations below report FAILED rather than LOST. StatefulManagerProxy
# treats LOST as possibly transient - a manager also returns it for a job whose
# external id has not been recovered yet - so it never deactivates a job
# reported LOST. These escalations only fire once the grace period has elapsed,
# at which point the job really is over and has to be finished.


class _HTCondorJobState(HTCondorEventLogTracker):
    """Event-log bookkeeping for a single job, keyed by external (cluster) id."""

    def __init__(self, user_log, external_id, max_held_count, clock=time.monotonic):
        super().__init__(user_log, clock=clock)
        self.cluster_id = int(external_id)
        self.max_held_count = max_held_count
        self.running = False


class HTCondorQueueManager(ExternalBaseManager):
    """
    Job manager backend that plugs into HTCondor through its Python bindings.
    """
    manager_type = "queued_htcondor"

    def __init__(self, name, app, **kwds):
        super().__init__(name, app, **kwds)
        self.submission_params = submission_params(**kwds)
        self.collector = kwds.get("htcondor_collector", None)
        self.schedd_name = kwds.get("htcondor_schedd", None)
        self.condor_config = normalize_condor_config(kwds.get("htcondor_config", None))
        self.request_walltime = kwds.get("request_walltime", None)
        self.max_held_count = int(kwds.get("max_held_count", DEFAULT_MAX_HELD_COUNT))
        self.htcondor = import_htcondor()
        self._clients = HTCondorClientCache(self.htcondor, remove_reason=HTCONDOR_REMOVE_REASON)
        self._job_states = {}
        self._lock = threading.Lock()
        # Injectable so tests can drive escalation without sleeping.
        self.clock = time.monotonic

    def launch(self, job_id, command_line, submit_params={}, dependencies_description=None, env=[], setup_params=None):
        self._check_execution_with_tool_file(job_id, command_line)
        job_file_path = self._setup_job_file(
            job_id,
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            setup_params=setup_params
        )
        log_path = self.__condor_user_log(job_id)
        open(log_path, 'w')  # Touch log file

        query_params = dict(submit_params)
        query_params.update(self.submission_params)
        # These configure this manager rather than HTCondor, so they are pulled
        # out before the rest of the params become the submit description.
        walltime = query_params.pop("request_walltime", self.request_walltime)
        max_held_count = int(query_params.pop("max_held_count", self.max_held_count))
        if walltime is not None and "periodic_hold" not in query_params:
            walltime_seconds = parse_walltime_seconds(str(walltime))
            if walltime_seconds is not None:
                query_params["periodic_hold"] = periodic_hold_expression(walltime_seconds)
            else:
                log.warning("Ignoring unparseable request_walltime [%s] for job %s", walltime, job_id)

        submit_file_contents = build_submit_description(
            executable=job_file_path,
            output=self._job_stdout_path(job_id),
            error=self._job_stderr_path(job_id),
            user_log=log_path,
            query_params=query_params,
        )
        external_id = self._client().submit(
            submit_file_contents,
            collector=self.collector,
            schedd_name=self.schedd_name,
        )
        log.info("Submitted HTCondor job with Pulsar job id %s and external id %s", job_id, external_id)
        self._register_external_id(job_id, external_id)
        with self._lock:
            self._job_states[job_id] = _HTCondorJobState(log_path, external_id, max_held_count, clock=self.clock)

    def get_status(self, job_id):
        if self._was_cancelled(job_id):
            return status.CANCELLED
        external_id = self._external_id(job_id)
        if not external_id:
            log.warning("Failed to find external id for job_id %s", job_id)
            return status.LOST
        return self.__status_from_event_log(job_id, external_id)

    def shutdown(self, timeout=None):
        """Shut down HTCondor clients (and any helper subprocesses)."""
        try:
            # ExternalBaseManager has no shutdown - only some manager bases do.
            parent_shutdown = getattr(super(), "shutdown", None)
            if parent_shutdown is not None:
                parent_shutdown(timeout)
        finally:
            self._clients.shutdown()

    def _kill_external(self, external_id):
        try:
            job_spec = int(external_id)
        except (TypeError, ValueError):
            job_spec = external_id
        self._client().remove(job_spec, collector=self.collector, schedd_name=self.schedd_name)
        log.info("Removed HTCondor job with external id %s", external_id)

    def _deactivate_job(self, job_id):
        with self._lock:
            job_state = self._job_states.pop(job_id, None)
        if job_state is not None:
            job_state.close_event_log()
        super()._deactivate_job(job_id)

    def _client(self):
        return self._clients.client_for_config(self.condor_config)

    def __condor_user_log(self, job_id):
        return self._job_file(job_id, 'job_condor.log')

    def __job_state(self, job_id, external_id):
        # Created lazily so that jobs recovered after a Pulsar restart pick up a
        # fresh event log handle without any extra recovery hook.
        job_state = self._job_states.get(job_id)
        if job_state is None:
            job_state = _HTCondorJobState(
                self.__condor_user_log(job_id), external_id, self.max_held_count, clock=self.clock
            )
            self._job_states[job_id] = job_state
        return job_state

    def __status_from_event_log(self, job_id, external_id):
        with self._lock:
            job_state = self.__job_state(job_id, external_id)
            try:
                summary = job_state.summarize(self.htcondor, job_state.cluster_id, job_state.running)
                job_state.clear_status_errors()
            except Exception:
                elapsed = job_state.note_status_error()
                if elapsed < STATUS_ERROR_GRACE_SECONDS:
                    log.warning(
                        "Transient error checking status of job %s (external id %s), failing after %ss",
                        job_id, external_id, STATUS_ERROR_GRACE_SECONDS
                    )
                    return status.RUNNING if job_state.running else status.QUEUED
                log.exception(
                    "Failed to check status of job %s (external id %s) for %.0fs", job_id, external_id, elapsed
                )
                return status.FAILED
            return self.__summary_to_status(job_id, external_id, job_state, summary)

    def __summary_to_status(self, job_id, external_id, job_state, summary):
        if summary.log_missing:
            elapsed = job_state.note_missing_log()
            if elapsed >= MISSING_LOG_GRACE_SECONDS:
                log.warning(
                    "Job %s (external id %s): %s (absent for %.0fs)",
                    job_id, external_id, MISSING_LOG_MESSAGE, elapsed
                )
                return status.FAILED
            return status.RUNNING if job_state.running else status.QUEUED
        job_state.clear_missing_log()

        if summary.job_released and job_state.held_count > 0:
            log.debug("Job %s (external id %s) released, resetting held count", job_id, external_id)
            job_state.held_count = 0

        if summary.job_complete:
            job_state.running = False
            return status.COMPLETE
        if summary.failure_event is not None:
            job_state.running = False
            failure = classify_failure_event(self.htcondor, summary.failure_event)
            log.warning(
                "Job %s (external id %s) failed: %s", job_id, external_id, FAILURE_MESSAGES[failure]
            )
            return status.FAILED
        if summary.job_held:
            job_state.running = False
            return self.__held_status(job_id, external_id, job_state, summary.hold_reason_code)

        job_state.running = summary.job_running
        return status.RUNNING if summary.job_running else status.QUEUED

    def __held_status(self, job_id, external_id, job_state, hold_reason_code):
        hold_reason = classify_hold(hold_reason_code)
        if hold_reason in (HOLD_REASON_MEMORY_LIMIT, HOLD_REASON_WALLTIME):
            log.warning(
                "Job %s (external id %s) held (HoldReasonCode=%s): %s",
                job_id, external_id, hold_reason_code, HOLD_MESSAGES[hold_reason]
            )
            return status.FAILED
        job_state.held_count += 1
        if 0 < job_state.max_held_count <= job_state.held_count:
            log.warning(
                "Job %s (external id %s): %s", job_id, external_id, held_message(job_state.held_count)
            )
            return status.FAILED
        log.debug(
            "Job %s (external id %s) held (HoldReasonCode=%s), held count %s/%s",
            job_id, external_id, hold_reason_code, job_state.held_count, job_state.max_held_count
        )
        return status.QUEUED
