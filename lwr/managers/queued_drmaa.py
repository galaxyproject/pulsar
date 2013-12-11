from .base.base_drmaa import BaseDrmaaManager


class DrmaaQueueManager(BaseDrmaaManager):
    """
    DRMAA backed queue manager.
    """
    manager_type = "queued_drmaa"

    def launch(self, job_id, command_line, submit_params={}, requirements=[]):
        self._check_execution_with_tool_file(job_id, command_line)
        attributes = self._build_template_attributes(job_id, command_line, requirements=requirements)
        external_id = self.drmaa_session.run_job(**attributes)
        self._register_external_id(job_id, external_id)

    def _kill_external(self, external_id):
        self.drmaa_session.kill(external_id)
