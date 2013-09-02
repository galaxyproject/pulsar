from os import chmod
from stat import S_IEXEC, S_IWRITE, S_IREAD

from lwr.managers.base import DirectoryBaseManager
from lwr.drmaa import DrmaaSessionFactory
from string import Template

try:
    from drmaa import JobState
except ImportError:
    JobState = None

DEFAULT_JOB_NAME_TEMPLATE = "lwr_$job_id"

JOB_FILE_TEMPLATE = """#!/bin/sh
cd $working_directory
$command_line
echo $? > $return_code_path
"""


class DrmaaQueueManager(DirectoryBaseManager):
    """
    Placeholder for DRMAA backed queue manager. Not yet implemented.
    """
    manager_type = "queued_drmaa"

    def __init__(self, name, app, **kwds):
        super(DrmaaQueueManager, self).__init__(name, app, **kwds)
        self.external_ids = {}
        self.job_name_template = kwds.get('job_name_template', DEFAULT_JOB_NAME_TEMPLATE)
        self.native_specification = kwds.get('native_specification', None)
        drmaa_session_factory_class = kwds.get('drmaa_session_factory_class', DrmaaSessionFactory)
        drmaa_session_factory = drmaa_session_factory_class()
        self.drmaa_session = drmaa_session_factory.get()

    def launch(self, job_id, command_line):
        self._check_execution_with_tool_file(job_id, command_line)
        attributes = self.__build_template_attributes(job_id, command_line)
        self.external_ids[job_id] = self.drmaa_session.run_job(**attributes)

    def __build_template_attributes(self, job_id, command_line):
        stdout_path = self._stdout_path(job_id)
        stderr_path = self._stderr_path(job_id)

        attributes = {
            "remoteCommand": self.__setup_job_file(job_id, command_line),
            "jobName": self.__job_name(job_id),
            "outputPath": ":%s" % stdout_path,
            "errorPath": ":%s" % stderr_path,
        }
        if self.native_specification:
            attributes["nativeSpecification"] = self.native_specification
        return attributes

    def __setup_job_file(self, job_id, command_line):
        return_code_path = self._return_code_path(job_id)
        script_env = {
            'return_code_path': return_code_path,
            'command_line': command_line,
            'working_directory': self.working_directory(job_id)
        }

        template = Template(JOB_FILE_TEMPLATE)
        script_contents = template.safe_substitute(**script_env)
        self._write_job_file(job_id, "command.sh", script_contents)
        script_path = self._job_file(job_id, "command.sh")
        chmod(script_path, S_IEXEC | S_IWRITE | S_IREAD)
        return script_path

    def __job_name(self, job_id):
        return Template(self.job_name_template).safe_substitute(job_id=job_id)

    def kill(self, job_id):
        external_id = self.external_ids.get(job_id, None)
        if external_id:
            self.drmaa_session.kill(external_id)

    def get_status(self, job_id):
        external_id = self.external_ids.get(job_id)
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

    def setup_job(self, input_job_id, tool_id, tool_version):
        job_id = self._get_job_id(input_job_id)
        return self._setup_job_for_job_id(job_id, tool_id, tool_version)

    def _get_job_id(self, input_job_id):
        return str(self.id_assigner(input_job_id))
