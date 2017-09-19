from .base.base_drmaa import BaseDrmaaManager

import logging
log = logging.getLogger(__name__)


class DrmaaQueueManager(BaseDrmaaManager):
    """
    DRMAA backed queue manager.
    """
    manager_type = "queued_drmaa"

    def launch(self, job_id, command_line, submit_params={}, dependencies_description=None, env=[], setup_params=None):
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
        log.info("Submitted DRMAA job with Pulsar job id %s and external id %s", job_id, external_id)
        self._register_external_id(job_id, external_id)

    def _kill_external(self, external_id):
        self.drmaa_session.kill(external_id)
        log.info("Killed DRMAA job with external id %s", external_id)
