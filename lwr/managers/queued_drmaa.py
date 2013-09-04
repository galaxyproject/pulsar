from lwr.managers.base.external import ExternalBaseManager
from lwr.drmaa import DrmaaSessionFactory
from string import Template

try:
    from drmaa import JobState
except ImportError:
    JobState = None


class DrmaaQueueManager(ExternalBaseManager):
    """
    Placeholder for DRMAA backed queue manager. Not yet implemented.
    """
    manager_type = "queued_drmaa"

    def __init__(self, name, app, **kwds):
        super(DrmaaQueueManager, self).__init__(name, app, **kwds)
        self.native_specification = kwds.get('native_specification', None)
        drmaa_session_factory_class = kwds.get('drmaa_session_factory_class', DrmaaSessionFactory)
        drmaa_session_factory = drmaa_session_factory_class()
        self.drmaa_session = drmaa_session_factory.get()

    def launch(self, job_id, command_line):
        self._check_execution_with_tool_file(job_id, command_line)
        attributes = self.__build_template_attributes(job_id, command_line)
        external_id = self.drmaa_session.run_job(**attributes)
        self._register_external_id(job_id, external_id)

    def __build_template_attributes(self, job_id, command_line):
        stdout_path = self._stdout_path(job_id)
        stderr_path = self._stderr_path(job_id)

        attributes = {
            "remoteCommand": self._setup_job_file(job_id, command_line),
            "jobName": self._job_name(job_id),
            "outputPath": ":%s" % stdout_path,
            "errorPath": ":%s" % stderr_path,
        }
        if self.native_specification:
            attributes["nativeSpecification"] = self.native_specification
        return attributes

    def _kill_external(self, external_id):
        self.drmaa_session.kill(external_id)

    def _get_status_external(self, external_id):
        drmaa_state = self.drmaa_session.job_status(external_id)
        return {
            JobState.UNDETERMINED: 'complete',
            JobState.QUEUED_ACTIVE: 'queued',
            JobState.SYSTEM_ON_HOLD: 'queued',
            JobState.USER_ON_HOLD: 'queued',
            JobState.USER_SYSTEM_ON_HOLD: 'queued',
            JobState.RUNNING: 'running',
            JobState.SYSTEM_SUSPENDED: 'queued',
            JobState.USER_SUSPENDED: 'queued',
            JobState.DONE: 'complete',
            JobState.FAILED: 'complete',  # Should be a FAILED state here as well
        }[drmaa_state]
