from .base.base_drmaa import BaseDrmaaManager
from .util.drmaa import DrmaaSessionFactory


class DrmaaQueueManager(BaseDrmaaManager):
    """
    DRMAA backed queue manager.
    """
    manager_type = "queued_drmaa"

    def __init__(self, name, app, **kwds):
        super(DrmaaQueueManager, self).__init__(name, app, **kwds)
        self.native_specification = kwds.get('native_specification', None)
        drmaa_session_factory_class = kwds.get('drmaa_session_factory_class', DrmaaSessionFactory)
        drmaa_session_factory = drmaa_session_factory_class()
        self.drmaa_session = drmaa_session_factory.get()

    def launch(self, job_id, command_line, submit_params={}):
        self._check_execution_with_tool_file(job_id, command_line)
        attributes = self._build_template_attributes(job_id, command_line)
        external_id = self.drmaa_session.run_job(**attributes)
        self._register_external_id(job_id, external_id)

    def _kill_external(self, external_id):
        self.drmaa_session.kill(external_id)
