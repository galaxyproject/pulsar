from os import chmod, getenv
from os.path import join
from stat import S_IEXEC, S_IWRITE, S_IREAD
from string import Template

from lwr.persistence import JobMetadataStore

from .directory import DirectoryBaseManager
from ..util.job_script import job_script

DEFAULT_JOB_NAME_TEMPLATE = "lwr_$job_id"


class ExternalBaseManager(DirectoryBaseManager):

    def __init__(self, name, app, **kwds):
        super(ExternalBaseManager, self).__init__(name, app, **kwds)
        self.external_ids = self._build_persistent_store(ExternalIdStore, "ext_ids")
        self.galaxy_home = kwds.get('galaxy_home', None)
        self.job_name_template = kwds.get('job_name_template', DEFAULT_JOB_NAME_TEMPLATE)

    def clean(self, job_id):
        super(ExternalBaseManager, self).clean(job_id)
        self.external_ids.free(job_id)

    def setup_job(self, input_job_id, tool_id, tool_version):
        job_id = self._get_job_id(input_job_id)
        return self._setup_job_for_job_id(job_id, tool_id, tool_version)

    def kill(self, job_id):
        external_id = self._external_id(job_id)
        if external_id:
            self._kill_external(external_id)

    def get_status(self, job_id):
        external_id = self._external_id(job_id)
        if not external_id:
            raise KeyError("Failed to find external id for job_id %s" % job_id)
        return self._get_status_external(external_id)

    def _galaxy_lib(self):
        galaxy_home = self.galaxy_home or getenv('GALAXY_HOME', None)
        galaxy_lib = None
        if galaxy_home and str(galaxy_home).lower() != 'none':
            galaxy_lib = join(galaxy_home, 'lib')
        return galaxy_lib

    def _setup_job_file(self, job_id, command_line):
        script_env = self._job_template_env(job_id, command_line=command_line)
        script = job_script(**script_env)
        return self._write_job_script(job_id, script)

    def _get_job_id(self, input_job_id):
        return str(self.id_assigner(input_job_id))

    def _register_external_id(self, job_id, external_id):
        self.external_ids.store(job_id, external_id)
        return external_id

    def _external_id(self, job_id):
        return self.external_ids.get(job_id, None)

    def _job_template_env(self, job_id, command_line=None):
        return_code_path = self._return_code_path(job_id)
        job_template_env = {
            'galaxy_lib': self._galaxy_lib(),
            'exit_code_path': return_code_path,
            'working_directory': self.working_directory(job_id),
            'job_id': job_id,
        }
        if command_line:
            job_template_env['command'] = command_line

        return job_template_env

    def _write_job_script(self, job_id, contents):
        self._write_job_file(job_id, "command.sh", contents)
        script_path = self._job_file(job_id, "command.sh")
        chmod(script_path, S_IEXEC | S_IWRITE | S_IREAD)
        return script_path

    def _job_name(self, job_id):
        env = self._job_template_env(job_id)
        return Template(self.job_name_template).safe_substitute(env)


class ExternalIdStore(JobMetadataStore):
    """
    """

    def __init__(self, path):
        super(ExternalIdStore, self).__init__(path)

    def store(self, job_id, external_id):
        super(ExternalIdStore, self)._store(job_id, external_id)

    def free(self, job_id):
        super(ExternalIdStore, self)._delete(job_id)

    def get(self, job_id, default):
        return super(ExternalIdStore, self)._get(job_id, default)
