from os import chmod, getenv
from os.path import join
from stat import S_IEXEC, S_IWRITE, S_IREAD
from string import Template

from .directory import DirectoryBaseManager

DEFAULT_JOB_NAME_TEMPLATE = "lwr_$job_id"

DEFAULT_JOB_FILE_TEMPLATE = """#!/bin/sh
$galaxy_lib_export
cd $working_directory
$command_line
echo $? > $return_code_path
"""

GALAXY_LIB_EXPORT_TEMPLATE = '''
GALAXY_LIB='%s'
if [ -n "$PYTHONPATH" ]; then
    PYTHONPATH="$GALAXY_LIB:$PYTHONPATH"
else
    PYTHONPATH="$GALAXY_LIB"
fi
export PYTHONPATH
'''


class ExternalBaseManager(DirectoryBaseManager):

    def __init__(self, name, app, **kwds):
        super(ExternalBaseManager, self).__init__(name, app, **kwds)
        self.external_ids = {}
        self.galaxy_home = kwds.get('galaxy_home', None)
        self.job_name_template = kwds.get('job_name_template', DEFAULT_JOB_NAME_TEMPLATE)

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

    def _galaxy_lib_export(self):
        galaxy_home = self.galaxy_home or getenv('GALAXY_HOME', None)
        export = ''
        if galaxy_home and galaxy_home.lower() != 'none':
            export = GALAXY_LIB_EXPORT_TEMPLATE % join(galaxy_home, 'lib')
        return export

    def _setup_job_file(self, job_id, command_line, file_template=DEFAULT_JOB_FILE_TEMPLATE):
        script_env = self._job_template_env(job_id, command_line=command_line)
        template = Template(file_template)
        script_contents = template.safe_substitute(**script_env)
        return self._write_job_script(job_id, script_contents)

    def _get_job_id(self, input_job_id):
        return str(self.id_assigner(input_job_id))

    def _register_external_id(self, job_id, external_id):
        self.external_ids[job_id] = external_id
        return external_id

    def _external_id(self, job_id):
        return self.external_ids.get(job_id, None)

    def _job_template_env(self, job_id, command_line=None):
        return_code_path = self._return_code_path(job_id)
        job_template_env = {
            'galaxy_lib_export': self._galaxy_lib_export(),
            'return_code_path': return_code_path,
            'working_directory': self.working_directory(job_id),
            'job_id': job_id,
        }
        if command_line:
            job_template_env['command_line'] = command_line

        return job_template_env

    def _write_job_script(self, job_id, contents):
        self._write_job_file(job_id, "command.sh", contents)
        script_path = self._job_file(job_id, "command.sh")
        chmod(script_path, S_IEXEC | S_IWRITE | S_IREAD)
        return script_path

    def _job_name(self, job_id):
        env = self._job_template_env(job_id)
        return Template(self.job_name_template).safe_substitute(env)
