import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from .base.base_drmaa import BaseDrmaaManager

if TYPE_CHECKING:
    from galaxy.tools.deps.dependencies import DependencyDescription

log = logging.getLogger(__name__)


class DrmaaQueueManager(BaseDrmaaManager):
    """
    DRMAA backed queue manager.
    """

    manager_type = "queued_drmaa"

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
        attributes = self._build_template_attributes(
            job_id,
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            submit_params=submit_params,
            setup_params=setup_params,
        )
        external_id = self.drmaa_session.run_job(**attributes)
        log.info(
            "Submitted DRMAA job with Pulsar job id %s and external id %s",
            job_id,
            external_id,
        )
        self._register_external_id(job_id, external_id)

    def _kill_external(self, external_id: str) -> None:
        self.drmaa_session.kill(external_id)
        log.info("Killed DRMAA job with external id %s", external_id)
