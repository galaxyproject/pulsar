from __future__ import print_function
from json import dumps
from getpass import getuser

from .base.base_drmaa import BaseDrmaaManager
from .util.sudo import sudo_popen
from ..managers import status

from galaxy.tools.deps.commands import which

from logging import getLogger
log = getLogger(__name__)

DEFAULT_CHOWN_WORKING_DIRECTORY_SCRIPT = "scripts/chown_working_directory.bash"
DEFAULT_DRMAA_KILL_SCRIPT = "scripts/drmaa_kill.bash"
DEFAULT_DRMAA_LAUNCH_SCRIPT = "scripts/drmaa_launch.bash"


class ExternalDrmaaQueueManager(BaseDrmaaManager):
    """
    DRMAA backed queue manager.
    """
    manager_type = "queued_external_drmaa"

    def __init__(self, name, app, **kwds):
        super(ExternalDrmaaQueueManager, self).__init__(name, app, **kwds)
        self.chown_working_directory_script = _handle_default(kwds.get('chown_working_directory_script', None), "chown_working_directory")
        self.drmaa_kill_script = _handle_default(kwds.get('drmaa_kill_script', None), "drmaa_kill")
        self.drmaa_launch_script = _handle_default(kwds.get('drmaa_launch_script', None), "drmaa_launch")
        self.production = str(kwds.get('production', "true")).lower() != "false"
        self.reclaimed = {}
        self.user_map = {}

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
        print(open(attributes['remoteCommand'], 'r').read())
        job_attributes_file = self._write_job_file(job_id, 'jt.json', dumps(attributes))
        user = submit_params.get('user', None)
        log.info("Submit as user %s" % user)
        if not user:
            raise Exception("Must specify user submit parameter with this manager.")
        self.__change_ownership(job_id, user)
        external_id = self.__launch(job_attributes_file, user).strip()
        self.user_map[external_id] = user
        self._register_external_id(job_id, external_id)

    def _kill_external(self, external_id):
        user = self.user_map[external_id]
        self.__sudo(self.drmaa_kill_script, "--external_id", external_id, user=user)

    def get_status(self, job_id):
        external_id = self._external_id(job_id)
        if not external_id:
            raise KeyError("Failed to find external id for job_id %s" % job_id)
        external_status = super(ExternalDrmaaQueueManager, self)._get_status_external(external_id)
        if external_status == status.COMPLETE and job_id not in self.reclaimed:
            self.reclaimed[job_id] = True
            self.__change_ownership(job_id, getuser())
        return external_status

    def __launch(self, job_attributes, user):
        return self.__sudo(self.drmaa_launch_script, "--job_attributes", str(job_attributes), user=user)

    def __change_ownership(self, job_id, username):
        cmds = [self.chown_working_directory_script, "--user", str(username)]
        if self.production:
            cmds.extend(["--job_id", job_id])
        else:
            # In testing, the loading working directory from server.ini doesn't
            # work. Need to reimagine how to securely map job_id to working
            # direcotry between test cases and production.
            cmds.extend(["--job_directory", str(self._job_directory(job_id).path)])
        # TODO: Verify ownership change.
        self.__sudo(*cmds)

    def __sudo(self, *cmds, **kwargs):
        p = sudo_popen(*cmds, **kwargs)
        stdout, stderr = p.communicate()
        assert p.returncode == 0, "%s, %s" % (stdout, stderr)
        return stdout


def _handle_default(value, script_name):
    """ There are two potential variants of these scripts,
    the Bash scripts that are meant to be run within PULSAR_ROOT
    for older-style installs and the binaries created by setup.py
    as part of a proper pulsar installation.

    This method first looks for the newer style variant of these
    scripts and returns the full path to them if needed and falls
    back to the bash scripts if these cannot be found.
    """
    if value:
        return value

    installed_script = which("pulsar-%s" % script_name.replace("_", "-"))
    if installed_script:
        return installed_script
    else:
        return "scripts/%s.bash" % script_name
