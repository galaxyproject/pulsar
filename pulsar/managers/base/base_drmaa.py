"""Module defines a base class for Pulsar managers using DRMAA."""

import logging
from typing import (
    cast,
    TYPE_CHECKING,
    Dict,
    List,
    Optional,
)
from typing_extensions import Literal

if TYPE_CHECKING:
    from galaxy.tools.deps.dependencies import DependencyDescription
    from pulsar.core import PulsarApp

try:
    from drmaa import JobState
except (OSError, ImportError, RuntimeError):
    JobState = None

from pulsar.managers import status
from .external import ExternalBaseManager
from ..util.drmaa import DrmaaSessionFactory

log = logging.getLogger(__name__)

IGNORE_SUBMISSION_SPEC_MESSAGE = "Submission recieved native_specification but being overridden by manager specification."


DrmaaJobStateLiteral = Literal[
    "undetermined",
    "queued_active",
    "system_on_hold",
    "user_on_hold",
    "user_system_on_hold",
    "running",
    "system_suspended",
    "user_suspended",
    "user_system_suspended",
    "done",
    "failed",
]


class BaseDrmaaManager(ExternalBaseManager):
    """Base class for Pulsar managers using DRMAA."""

    def __init__(self, name: str, app: "PulsarApp", **kwds):
        """Setup native specification and drmaa session factory."""
        super().__init__(name, app, **kwds)
        self.native_specification = kwds.get("native_specification", None)
        drmaa_session_factory_class = kwds.get(
            "drmaa_session_factory_class", DrmaaSessionFactory
        )
        drmaa_session_factory = drmaa_session_factory_class()
        self.drmaa_session = drmaa_session_factory.get()

    def shutdown(self, timeout: Optional[float] = None) -> None:
        """Cleanup DRMAA session and call shutdown of parent."""
        try:
            super().shutdown(timeout)
        except Exception:
            pass
        self.drmaa_session.close()

    def _get_status_external(self, external_id: str) -> status.StateLiteral:
        drmaa_state = cast(
            DrmaaJobStateLiteral, self.drmaa_session.job_status(external_id)
        )
        StateMapping = Dict[DrmaaJobStateLiteral, status.StateLiteral]
        STATE_MAP: StateMapping = {
            cast(DrmaaJobStateLiteral, JobState.UNDETERMINED): cast(
                status.StateLiteral, status.COMPLETE
            ),
            cast(DrmaaJobStateLiteral, JobState.QUEUED_ACTIVE): cast(
                status.StateLiteral, status.QUEUED
            ),
            cast(DrmaaJobStateLiteral, JobState.SYSTEM_ON_HOLD): cast(
                status.StateLiteral, status.QUEUED
            ),
            cast(DrmaaJobStateLiteral, JobState.USER_ON_HOLD): cast(
                status.StateLiteral, status.QUEUED
            ),
            cast(DrmaaJobStateLiteral, JobState.USER_SYSTEM_ON_HOLD): cast(
                status.StateLiteral, status.QUEUED
            ),
            cast(DrmaaJobStateLiteral, JobState.RUNNING): cast(
                status.StateLiteral, status.RUNNING
            ),
            cast(DrmaaJobStateLiteral, JobState.SYSTEM_SUSPENDED): cast(
                status.StateLiteral, status.QUEUED
            ),
            cast(DrmaaJobStateLiteral, JobState.USER_SUSPENDED): cast(
                status.StateLiteral, status.QUEUED
            ),
            cast(DrmaaJobStateLiteral, JobState.DONE): cast(
                status.StateLiteral, status.COMPLETE
            ),
            cast(DrmaaJobStateLiteral, JobState.FAILED): cast(
                status.StateLiteral, status.COMPLETE
            ),  # Should be a FAILED state here as well
        }
        return STATE_MAP[drmaa_state]

    def _build_template_attributes(
        self,
        job_id: str,
        command_line: str,
        dependencies_description: Optional["DependencyDescription"] = None,
        env: List[Dict[str, str]] = [],
        submit_params: Dict[str, str] = {},
        setup_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        stdout_path = self._job_stdout_path(job_id)
        stderr_path = self._job_stderr_path(job_id)
        working_directory = self.job_directory(job_id).working_directory()

        attributes = {
            "remoteCommand": self._setup_job_file(
                job_id,
                command_line,
                dependencies_description=dependencies_description,
                env=env,
                setup_params=setup_params,
            ),
            "jobName": self._job_name(job_id),
            "outputPath": ":%s" % stdout_path,
            "errorPath": ":%s" % stderr_path,
            "workingDirectory": working_directory,
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
            log.info(
                "Submitting DRMAA job with nativeSpecification [%s]"
                % native_specification
            )
        else:
            log.debug(
                "No native specification supplied, DRMAA job will be submitted with default parameters."
            )
        return attributes


__all__ = ("BaseDrmaaManager",)
