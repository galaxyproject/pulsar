"""Module defines a base class for Pulsar managers using DRMAA."""
import logging

try:
    from drmaa import JobState
except (OSError, ImportError):
    JobState = None

from .external import ExternalBaseManager
from ..util.drmaa import DrmaaSessionFactory

from pulsar.managers import status


log = logging.getLogger(__name__)

IGNORE_SUBMISSION_SPEC_MESSAGE = "Submission recieved native_specification but being overridden by manager specification."


class BaseDrmaaManager(ExternalBaseManager):
    """Base class for Pulsar managers using DRMAA."""

    def __init__(self, name, app, **kwds):
        """Setup native specification and drmaa session factory."""
        super(BaseDrmaaManager, self).__init__(name, app, **kwds)
        self.native_specification = kwds.get('native_specification', None)
        drmaa_session_factory_class = kwds.get('drmaa_session_factory_class', DrmaaSessionFactory)
        drmaa_session_factory = drmaa_session_factory_class()
        self.drmaa_session = drmaa_session_factory.get()

    def shutdown(self, timeout=None):
        """Cleanup DRMAA session and call shutdown of parent."""
        try:
            super(BaseDrmaaManager, self).shutdown(timeout)
        except Exception:
            pass
        self.drmaa_session.close()

    def _get_status_external(self, external_id):
        drmaa_state = self.drmaa_session.job_status(external_id)
        return {
            JobState.UNDETERMINED: status.COMPLETE,
            JobState.QUEUED_ACTIVE: status.QUEUED,
            JobState.SYSTEM_ON_HOLD: status.QUEUED,
            JobState.USER_ON_HOLD: status.QUEUED,
            JobState.USER_SYSTEM_ON_HOLD: status.QUEUED,
            JobState.RUNNING: status.RUNNING,
            JobState.SYSTEM_SUSPENDED: status.QUEUED,
            JobState.USER_SUSPENDED: status.QUEUED,
            JobState.DONE: status.COMPLETE,
            JobState.FAILED: status.COMPLETE,  # Should be a FAILED state here as well
        }[drmaa_state]

    def _build_template_attributes(self, job_id, command_line, dependencies_description=None, env=[], submit_params={}, setup_params=None):
        stdout_path = self._stdout_path(job_id)
        stderr_path = self._stderr_path(job_id)

        attributes = {
            "remoteCommand": self._setup_job_file(
                job_id,
                command_line,
                dependencies_description=dependencies_description,
                env=env,
                setup_params=setup_params
            ),
            "jobName": self._job_name(job_id),
            "outputPath": ":%s" % stdout_path,
            "errorPath": ":%s" % stderr_path,
        }
        submit_native_specification = submit_params.get("native_specification", None)
        native_specification = None
        if self.native_specification:
            native_specification = self.native_specification
            if submit_native_specification is not None:
                log.warn(IGNORE_SUBMISSION_SPEC_MESSAGE)
        elif submit_native_specification:
            native_specification = submit_params["native_specification"]

        if native_specification is not None:
            attributes["nativeSpecification"] = native_specification
            log.info("Submitting DRMAA job with nativeSpecification [%s]" % native_specification)
        else:
            log.debug("Not native specification supplied, DRMAA job will be submitted with default parameters.")
        return attributes


__all__ = ("BaseDrmaaManager",)
