import re
import subprocess
from getpass import getuser
from json import dumps
from logging import getLogger
from typing import (
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
)

from galaxy.util import which

from .base.base_drmaa import BaseDrmaaManager
from .util.sudo import sudo_popen
from ..managers import status

if TYPE_CHECKING:
    from galaxy.tool_util.deps.dependencies import DependenciesDescription

    from pulsar.core import PulsarApp
    from pulsar.managers.status import StateLiteral

log = getLogger(__name__)

DEFAULT_CHOWN_WORKING_DIRECTORY_SCRIPT = "scripts/chown_working_directory.bash"
DEFAULT_DRMAA_KILL_SCRIPT = "scripts/drmaa_kill.bash"
DEFAULT_DRMAA_LAUNCH_SCRIPT = "scripts/drmaa_launch.bash"
DEFAULT_USER_MAPPING_TIMEOUT = 30

# A mapped username is handed to `sudo -u` and interpolated into a shell command
# by chown_working_directory, so it is constrained to a conservative POSIX
# username. Galaxy applies an equivalent constraint to the names it sends; the
# output of an operator-supplied mapping script carries no such guarantee.
VALID_MAPPED_USER = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._-]*")


class ExternalDrmaaQueueManager(BaseDrmaaManager):
    """
    DRMAA backed queue manager.
    """

    manager_type = "queued_external_drmaa"

    def __init__(self, name: str, app: "PulsarApp", **kwds):
        super().__init__(name, app, **kwds)
        self.chown_working_directory_script = _handle_default(
            kwds.get("chown_working_directory_script", None), "chown_working_directory"
        )
        self.drmaa_kill_script = _handle_default(
            kwds.get("drmaa_kill_script", None), "drmaa_kill"
        )
        self.drmaa_launch_script = _handle_default(
            kwds.get("drmaa_launch_script", None), "drmaa_launch"
        )
        self.user_mapping_script: Optional[str] = kwds.get("user_mapping_script", None)
        self.user_mapping_timeout = int(
            kwds.get("user_mapping_timeout", DEFAULT_USER_MAPPING_TIMEOUT)
        )
        self.production = str(kwds.get("production", "true")).lower() != "false"
        self.reclaimed: Dict[str, bool] = {}
        self.user_map: Dict[str, str] = {}

    def launch(
        self,
        job_id: str,
        command_line: str,
        submit_params: Dict[str, str] = {},
        dependencies_description: Optional["DependenciesDescription"] = None,
        env: List[Dict[str, str]] = [],
        setup_params: Optional[Dict[str, str]] = None,
    ) -> None:
        self._check_execution_with_tool_file(job_id, command_line)
        attributes = self._build_template_attributes(
            job_id,
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            submit_params=submit_params,
            setup_params=setup_params,
        )
        with open(attributes["remoteCommand"]) as fh:
            print(fh.read())
        job_attributes_file = self._write_job_file(job_id, "jt.json", dumps(attributes))
        user = submit_params.get("user", None)
        log.info("Submit as user %s" % user)
        if not user:
            raise Exception("Must specify user submit parameter with this manager.")
        user = self.__map_user(user)
        self.__change_ownership(job_id, user)
        external_id = self.__launch(job_attributes_file, user).strip()
        self.user_map[external_id] = user
        self._register_external_id(job_id, external_id)

    def _kill_external(self, external_id: str) -> None:
        user = self.user_map[external_id]
        self.__sudo(self.drmaa_kill_script, "--external_id", external_id, user=user)

    def get_status(self, job_id: str) -> "StateLiteral":
        external_id = self._external_id(job_id)
        if not external_id:
            raise KeyError("Failed to find external id for job_id %s" % job_id)
        external_status = super()._get_status_external(external_id)
        # Reclaim the working directory before Pulsar reads terminal job data.
        if status.is_job_done(external_status) and job_id not in self.reclaimed:
            self.reclaimed[job_id] = True
            self.__change_ownership(job_id, getuser())
        return external_status

    def __map_user(self, user: str) -> str:
        """Map the username supplied by the client onto one on this system.

        Returns the name unchanged when no mapping script is configured.

        The result is validated rather than trusted: it reaches `sudo -u` and a
        shell command, and unlike the name Galaxy sends it comes from a script
        this manager does not control.
        """
        script = self.user_mapping_script
        if not script:
            return user
        try:
            mapped_user = subprocess.check_output(
                [script, user],
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.user_mapping_timeout,
            ).strip()
        except subprocess.CalledProcessError as e:
            log.error("Could not map user %s: %s", user, e.stderr)
            raise Exception("User mapping script failed")
        except subprocess.TimeoutExpired:
            log.error(
                "User mapping script did not return within %s seconds mapping user %s",
                self.user_mapping_timeout,
                user,
            )
            raise Exception("User mapping script timed out")
        if not VALID_MAPPED_USER.fullmatch(mapped_user):
            # repr keeps a newline or quote in the value from garbling the log.
            log.error(
                "User mapping script returned an unusable username for %s: %r",
                user,
                mapped_user[:64],
            )
            raise Exception("User mapping script returned an invalid username")
        log.info("Mapped user %s to %s", user, mapped_user)
        return mapped_user

    def __launch(self, job_attributes_file: str, user: str) -> str:
        return self.__sudo(
            self.drmaa_launch_script,
            "--job_attributes",
            str(job_attributes_file),
            user=user,
        )

    def __change_ownership(self, job_id: str, username: str) -> None:
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

    def __sudo(self, *cmds, **kwargs) -> str:
        p = sudo_popen(*cmds, **kwargs)
        stdout, stderr = p.communicate()
        assert p.returncode == 0, "{}, {}".format(stdout, stderr)
        return stdout

    def _deactivate_job(self, job_id: str) -> None:
        external_id = self._external_id(job_id)
        if external_id is not None:
            del self.user_map[external_id]
        self.reclaimed.pop(job_id, None)
        super()._deactivate_job(job_id)


def _handle_default(value: Optional[str], script_name: str) -> str:
    """There are two potential variants of these scripts,
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
