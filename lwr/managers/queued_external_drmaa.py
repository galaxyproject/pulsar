from simplejson import dumps
from getpass import getuser

from .base.external import ExternalBaseManager
from .base.uses_drmaa import UsesDrmaa
from .util.drmaa import DrmaaSessionFactory
from .util.sudo import sudo_popen

DEFAULT_CHOWN_WORKING_DIRECTORY_SCRIPT = "scripts/chown_working_directory.bash"
DEFAULT_DRMAA_KILL_SCRIPT = "scripts/drmaa_kill.bash"
DEFAULT_DRMAA_LAUNCH_SCRIPT = "scripts/drmaa_launch.bash"


class ExternalDrmaaQueueManager(ExternalBaseManager, UsesDrmaa):
    """
    DRMAA backed queue manager.
    """
    manager_type = "queued_external_drmaa"

    def __init__(self, name, app, **kwds):
        super(ExternalDrmaaQueueManager, self).__init__(name, app, **kwds)
        self.native_specification = kwds.get('native_specification', None)
        self.chown_working_directory_script = kwds.get('chown_working_directory_script', DEFAULT_CHOWN_WORKING_DIRECTORY_SCRIPT)
        self.drmaa_kill_script = kwds.get('drmaa_kill_script', DEFAULT_DRMAA_KILL_SCRIPT)
        self.drmaa_launch_script = kwds.get('drmaa_launch_script', DEFAULT_DRMAA_LAUNCH_SCRIPT)
        self.reclaimed = {}
        drmaa_session_factory_class = kwds.get('drmaa_session_factory_class', DrmaaSessionFactory)
        drmaa_session_factory = drmaa_session_factory_class()
        self.drmaa_session = drmaa_session_factory.get()

    def launch(self, job_id, command_line, submit_params={}):
        self._check_execution_with_tool_file(job_id, command_line)
        attributes = self._build_template_attributes(job_id, command_line)
        job_attributes_file = self._write_job_file(job_id, 'jt.json', dumps(attributes))
        user = submit_params.get('username', None)
        if not user:
            raise Exception("Must specify user submit parameter with this manager.")
        self.__change_ownership(self, job_id, user)
        external_id = self.__launch(self, job_attributes_file).strip()
        self._register_external_id(job_id, external_id)

    def _kill_external(self, external_id):
        self.__sudo(self.drmaa_kill_script, "--external_id", external_id)

    def get_status(self, job_id):
        external_id = self._external_id(job_id)
        if not external_id:
            raise KeyError("Failed to find external id for job_id %s" % job_id)
        status = super(ExternalDrmaaQueueManager, self)._get_status_external(external_id)
        if status == "complete" and job_id not in self.reclaimed:
            self.reclaimed[job_id] = True
            self.__change_ownership(self, job_id, getuser())
        return status

    def __launch(self, job_attributes):
        self.__sudo(self.drmaa_launch_script, "--job_attributes", job_attributes)

    def __change_ownership(self, job_id, username):
        self.__sudo(self.chown_working_directory_script, "--job_id", job_id, "--user", username)

    def __sudo(**cmds):
        p = sudo_popen(**cmds)
        stdout, stderr = p.communicate()
        assert p.returncode == 0
        return stdout
