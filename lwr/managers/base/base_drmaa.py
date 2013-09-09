from .external import ExternalBaseManager
try:
    from drmaa import JobState
except ImportError:
    JobState = None


class BaseDrmaaManager(ExternalBaseManager):

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

    def _build_template_attributes(self, job_id, command_line):
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
