"""Clients for HTTP, local, AMQP, CLI, and relay execution."""

import logging
import os
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
)

from typing_extensions import Protocol

from .action_mapper import (
    actions,
    path_type,
)
from .amqp_exchange import ACK_FORCE_NOACK_KEY
from .decorators import (
    parseJson,
    retry,
)
from .destination import submit_params
from .exceptions import OutputNotFoundException as OutputNotFoundException
from .job_directory import RemoteJobDirectory
from .setup_handler import build as build_setup_handler
from .util import (
    copy,
    ensure_directory,
    json_dumps,
    json_loads,
    MonitorStyle,
    to_base64_json,
)

log = logging.getLogger(__name__)

CACHE_WAIT_SECONDS = 3
CONTAINER_STAGING_DIRECTORY = "/pulsar_staging/"


class ClientManagerProtocol(Protocol):
    manager_name: str


class BaseJobClient:
    ensure_library_available: Optional[Callable[[], None]] = None

    def __init__(self, destination_params, job_id):
        precondition = self.__class__.ensure_library_available
        precondition and precondition()
        destination_params = destination_params or {}
        self.destination_params = destination_params
        self.assign_job_id(job_id)

        for attr in ["ssh_key", "ssh_user", "ssh_host", "ssh_port"]:
            setattr(self, attr, destination_params.get(attr, None))
        self.env = destination_params.get("env", [])
        # Optional cvmfsexec configuration; delivered to the Pulsar manager via
        # setup_params so it can override the manager's app.yml default.
        self.cvmfsexec = destination_params.get("cvmfsexec", None)
        self.files_endpoint = destination_params.get("files_endpoint", None)
        self.token_endpoint = destination_params.get("token_endpoint", None)
        self.external_id = destination_params.get("external_id", None)

        default_file_action = self.destination_params.get("default_file_action", "transfer")
        if default_file_action not in actions:
            raise Exception("Unknown Pulsar default file action type %s" % default_file_action)
        self.default_file_action = default_file_action
        self.action_config_path = self.destination_params.get("file_action_config", None)
        if self.action_config_path is None:
            self.file_actions = self.destination_params.get("file_actions", {})
        else:
            self.file_actions = None

        self.setup_handler = build_setup_handler(self, destination_params)

    def assign_job_id(self, job_id):
        self.job_id = job_id
        self._set_job_directory()

    def _set_job_directory(self):
        if "jobs_directory" in self.destination_params:
            pulsar_staging = self.destination_params["jobs_directory"]
            sep = self.destination_params.get("remote_sep", os.sep)
            job_directory = RemoteJobDirectory(
                remote_staging_directory=pulsar_staging,
                remote_id=self.job_id,
                remote_sep=sep,
            )
        else:
            job_directory = None
        self.job_directory = job_directory

    def setup(self, tool_id=None, tool_version=None, preserve_galaxy_python_environment=None):
        """
        Setup remote Pulsar server to run this job.
        """
        setup_args = {"job_id": self.job_id}
        if tool_id:
            setup_args["tool_id"] = tool_id
        if tool_version:
            setup_args["tool_version"] = tool_version
        if preserve_galaxy_python_environment:
            setup_args["preserve_galaxy_python_environment"] = preserve_galaxy_python_environment
        return self.setup_handler.setup(**setup_args)

    @property
    def prefer_local_staging(self):
        # If doing a job directory is defined, calculate paths here and stage
        # remotely.
        return self.job_directory is None


class JobClient(BaseJobClient):
    """
    Objects of this client class perform low-level communication with a remote Pulsar server.

    **Parameters**

    destination_params : dict or str
        connection parameters, either url with dict containing url (and optionally `private_token`).
    job_id : str
        Galaxy job/task id.
    """

    def __init__(self, destination_params, job_id, job_manager_interface):
        super().__init__(destination_params, job_id)
        self.job_manager_interface = job_manager_interface

    def launch(self, command_line, dependencies_description=None, env=None, remote_staging=None, job_config=None,
               dynamic_file_sources=None, token_endpoint=None):
        """
        Queue up the execution of the supplied `command_line` on the remote
        server. Called launch for historical reasons, should be renamed to
        enqueue or something like that.

        **Parameters**

        command_line : str
            Command to execute.
        """
        launch_params = {"command_line": command_line, "job_id": self.job_id}
        submit_params_dict = submit_params(self.destination_params)
        if submit_params_dict:
            launch_params['params'] = json_dumps(submit_params_dict)
        if dependencies_description:
            launch_params['dependencies_description'] = json_dumps(dependencies_description.to_dict())
        if env:
            launch_params['env'] = json_dumps(env)
        if remote_staging:
            launch_params['remote_staging'] = json_dumps(remote_staging)
        if job_config and 'touch_outputs' in job_config:
            # message clients pass the entire job config
            launch_params['submit_extras'] = json_dumps({'touch_outputs': job_config['touch_outputs']})
        if token_endpoint is not None:
            launch_params["token_endpoint"] = json_dumps({'token_endpoint': token_endpoint})
        if self.cvmfsexec is not None:
            launch_params['cvmfsexec'] = json_dumps(self.cvmfsexec)

        if job_config and self.setup_handler.local:
            # Setup not yet called, job properties were inferred from
            # destination arguments. Hence, must have Pulsar setup job
            # before queueing.
            setup_params = _setup_params_from_job_config(job_config)
            launch_params['setup_params'] = json_dumps(setup_params)
        if dynamic_file_sources is not None:
            launch_params["dynamic_file_sources"] = json_dumps(dynamic_file_sources)
        return self._raw_execute("submit", launch_params)

    def full_status(self):
        """ Return a dictionary summarizing final state of job.
        """
        return self.raw_check_complete()

    def kill(self):
        """
        Cancel remote job, either removing from the queue or killing it.
        """
        return self._raw_execute("cancel", {"job_id": self.job_id})

    @retry()
    @parseJson()
    def raw_check_complete(self):
        """
        Get check_complete response from the remote server.
        """
        check_complete_response = self._raw_execute("status", {"job_id": self.job_id})
        return check_complete_response

    def get_status(self):
        check_complete_response = self.raw_check_complete()
        # Older Pulsar instances won't set status so use 'complete', at some
        # point drop backward compatibility.
        status = check_complete_response.get("status", None)
        return status

    def clean(self):
        """
        Cleanup the remote job.
        """
        self._raw_execute("clean", {"job_id": self.job_id})

    @parseJson()
    def remote_setup(self, **setup_args):
        """
        Setup remote Pulsar server to run this job.
        """
        return self._raw_execute("setup", setup_args)

    def put_file(self, path, input_type, name=None, contents=None, action_type='transfer'):
        if not name:
            name = os.path.basename(path)
        args = {"job_id": self.job_id, "name": name, "type": input_type}
        input_path = path
        if contents:
            input_path = None
        # action type == 'message' should either copy or transfer
        # depending on default not just fallback to transfer.
        if action_type in ['transfer', 'message']:
            if isinstance(contents, str):
                contents = contents.encode("utf-8")
            message = "Uploading path [%s] (action_type: [%s])"
            log.debug(message, path, action_type)
            return self._upload_file(args, contents, input_path)
        elif action_type == 'copy':
            path_response = self._raw_execute('path', args)
            pulsar_path = json_loads(path_response)['path']
            _copy(path, pulsar_path)
            return {'path': pulsar_path}

    def fetch_output(self, path, name, working_directory, action_type, output_type):
        """
        Fetch (transfer, copy, etc...) an output from the remote Pulsar server.

        **Parameters**

        path : str
            Local path of the dataset.
        name : str
            Remote name of file (i.e. path relative to remote staging output
            or working directory).
        working_directory : str
            Local working_directory for the job.
        action_type : str
            Where to find file on Pulsar (output_workdir or output). legacy is also
            an option in this case Pulsar is asked for location - this will only be
            used if targetting an older Pulsar server that didn't return statuses
            allowing this to be inferred.
        """
        if output_type in ['output_workdir', 'output_metadata']:
            self._populate_output_path(name, path, action_type, output_type)
        elif output_type == 'output':
            self._fetch_output(path=path, name=name, action_type=action_type)
        else:
            raise Exception("Unknown output_type %s" % output_type)

    def _raw_execute(self, command, args=None, data=None, input_path=None, output_path=None):
        if args is None:
            args = {}
        return self.job_manager_interface.execute(command, args, data, input_path, output_path)

    def _fetch_output(self, path, name=None, check_exists_remotely=False, action_type='transfer'):
        if not name:
            # Extra files will send in the path.
            name = os.path.basename(path)

        self._populate_output_path(name, path, action_type, path_type.OUTPUT)

    def _populate_output_path(self, name, output_path, action_type, path_type):
        ensure_directory(output_path)
        if action_type == 'transfer':
            self.__raw_download_output(name, self.job_id, path_type, output_path)
        elif action_type == 'copy':
            pulsar_path = self._output_path(name, self.job_id, path_type)['path']
            _copy(pulsar_path, output_path)

    @parseJson()
    def _upload_file(self, args, contents, input_path):
        return self._raw_execute("upload_file", args, contents, input_path)

    @parseJson()
    def _output_path(self, name, job_id, output_type):
        return self._raw_execute("path",
                                 {"name": name,
                                  "job_id": self.job_id,
                                  "type": output_type})

    @retry()
    def __raw_download_output(self, name, job_id, output_type, output_path):
        output_params = {
            "name": name,
            "job_id": self.job_id,
            "type": output_type
        }
        self._raw_execute("download_output", output_params, output_path=output_path)

    def job_ip(self):
        """Return a entry point ports dict (if applicable)."""
        return None


class BaseRemoteConfiguredJobClient(BaseJobClient):
    client_manager: ClientManagerProtocol

    def __init__(self, destination_params, job_id, client_manager):
        if "job_directory" not in destination_params:
            default_staging_directory = self.default_staging_directory(destination_params)
            if default_staging_directory:
                destination_params["jobs_directory"] = default_staging_directory
        super().__init__(destination_params, job_id)
        if not self.job_directory:
            error_message = "Message-queue based Pulsar client requires destination define a remote job_directory to stage files into."
            raise Exception(error_message)
        self.client_manager = client_manager
        self.amqp_key_prefix = self.destination_params.get("amqp_key_prefix")

    def _build_setup_message(self, command_line, dependencies_description, env, remote_staging, job_config,
                             dynamic_file_sources, token_endpoint):
        """
        """
        launch_params = {"command_line": command_line, "job_id": self.job_id}
        submit_params_dict = submit_params(self.destination_params)
        if submit_params_dict:
            launch_params['submit_params'] = submit_params_dict
        if dependencies_description:
            launch_params['dependencies_description'] = dependencies_description.to_dict()
        if env:
            launch_params['env'] = env
        if remote_staging:
            launch_params['remote_staging'] = remote_staging
            launch_params['remote_staging']['ssh_key'] = self.ssh_key
        launch_params['dynamic_file_sources'] = dynamic_file_sources
        launch_params['token_endpoint'] = token_endpoint
        if self.cvmfsexec is not None:
            launch_params['cvmfsexec'] = self.cvmfsexec

        if job_config and self.setup_handler.local:
            # Setup not yet called, job properties were inferred from
            # destination arguments. Hence, must have Pulsar setup job
            # before queueing.
            setup_params = _setup_params_from_job_config(job_config)
            launch_params["setup_params"] = setup_params
        return launch_params

    def default_staging_directory(self, destination_params):
        return None

    def get_pulsar_app_config(
        self,
        pulsar_app_config,
        container,
        wait_after_submission,
        manager_name,
        manager_type,
        dependencies_description,
    ):

        pulsar_app_config = pulsar_app_config or {}
        manager_config = self._ensure_manager_config(
            pulsar_app_config,
            manager_name,
            manager_type,
        )

        if (
            "staging_directory" not in manager_config and "staging_directory" not in pulsar_app_config
        ):
            pulsar_app_config["staging_directory"] = self.default_staging_directory(self.destination_params)

        if self.amqp_key_prefix:
            pulsar_app_config["amqp_key_prefix"] = self.amqp_key_prefix

        if "monitor" not in manager_config:
            manager_config["monitor"] = (
                MonitorStyle.BACKGROUND.value
                if wait_after_submission
                else MonitorStyle.NONE.value
            )
        if "persistence_directory" not in pulsar_app_config:
            pulsar_app_config["persistence_directory"] = os.path.join(
                CONTAINER_STAGING_DIRECTORY, "persisted_data"
            )
        elif "manager" in pulsar_app_config and manager_name != "_default_":
            log.warning(
                "'manager' set in app config but client has non-default manager '%s', this will cause communication"
                " failures, remove `manager` from app or client config to fix",
                manager_name,
            )

        using_dependencies = container is None and dependencies_description is not None
        if using_dependencies and "dependency_resolution" not in pulsar_app_config:
            # Setup default dependency resolution for container above...
            dependency_resolution = {
                "cache": False,
                "use": True,
                "default_base_path": "/pulsar_dependencies",
                "cache_dir": "/pulsar_dependencies/_cache",
                "resolvers": [
                    {  # TODO: add CVMFS resolution...
                        "type": "conda",
                        "auto_init": True,
                        "auto_install": True,
                        "prefix": "/pulsar_dependencies/conda",
                    },
                    {
                        "type": "conda",
                        "auto_init": True,
                        "auto_install": True,
                        "prefix": "/pulsar_dependencies/conda",
                        "versionless": True,
                    },
                ],
            }
            pulsar_app_config["dependency_resolution"] = dependency_resolution
        return pulsar_app_config

    def _ensure_manager_config(self, pulsar_app_config, manager_name, manager_type):
        if "manager" in pulsar_app_config:
            manager_config = pulsar_app_config["manager"]
        elif "managers" in pulsar_app_config:
            managers_config = pulsar_app_config["managers"]
            if manager_name not in managers_config:
                managers_config[manager_name] = {}
            manager_config = managers_config[manager_name]
        else:
            manager_config = {}
            pulsar_app_config["manager"] = manager_config
        if "type" not in manager_config:
            manager_config["type"] = manager_type
        return manager_config


class MessagingClientManagerProtocol(ClientManagerProtocol):
    status_cache: Dict[str, Dict[str, Any]]


class BaseMessageJobClient(BaseRemoteConfiguredJobClient):
    client_manager: MessagingClientManagerProtocol

    def clean(self):
        del self.client_manager.status_cache[self.job_id]

    def full_status(self):
        job_id = self.job_id
        full_status = self.client_manager.status_cache.get(job_id, None)
        if full_status is None:
            raise Exception("full_status() called for [%s] before a final status was properly cached with client manager." % job_id)
        return full_status

    def _build_status_request_message(self):
        # Because this is used to poll, status requests will not be resent if we do not receive an acknowledgement
        update_params = {
            'request': 'status',
            'job_id': self.job_id,
            ACK_FORCE_NOACK_KEY: True,
        }
        return update_params


class MessageJobClient(BaseMessageJobClient):

    def launch(self, command_line, dependencies_description=None, env=None, remote_staging=None, job_config=None,
               dynamic_file_sources=None, token_endpoint=None):
        """
        """
        launch_params = self._build_setup_message(
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            remote_staging=remote_staging,
            job_config=job_config,
            dynamic_file_sources=dynamic_file_sources,
            token_endpoint=token_endpoint,
        )
        self.client_manager.exchange.publish("setup", launch_params)
        log.info("Job published to setup message queue: %s", self.job_id)
        return None

    def get_status(self):
        status_params = self._build_status_request_message()
        response = self.client_manager.exchange.publish("setup", status_params)
        log.info("Job status request published to setup message queue: %s", self.job_id)
        return response

    def kill(self):
        self.client_manager.exchange.publish("kill", {"job_id": self.job_id})


class MessageCLIJobClient(BaseMessageJobClient):

    def __init__(self, destination_params, job_id, client_manager, shell):
        super().__init__(destination_params, job_id, client_manager)
        self.remote_pulsar_path = destination_params["remote_pulsar_path"]
        self.shell = shell

    def launch(self, command_line, dependencies_description=None, env=None, remote_staging=None, job_config=None,
               dynamic_file_sources=None, token_endpoint=None):
        """
        """
        launch_params = self._build_setup_message(
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            remote_staging=remote_staging,
            job_config=job_config,
            dynamic_file_sources=dynamic_file_sources,
            token_endpoint=token_endpoint,
        )
        base64_message = to_base64_json(launch_params)
        submit_command = os.path.join(self.remote_pulsar_path, "scripts", "submit.bash")
        # TODO: Allow configuration of manager, app, and ini path...
        self.shell.execute(f"nohup {submit_command} --base64 {base64_message} &")

    def kill(self):
        # TODO
        pass


class RelayJobClient(BaseMessageJobClient):
    """Client that communicates with Pulsar via pulsar-relay.

    This client posts control messages (setup, status, kill) to the relay,
    which are then consumed by the Pulsar server. File transfers happen
    directly between Pulsar and Galaxy via HTTP.
    """

    def launch(self, command_line, dependencies_description=None, env=None, remote_staging=None, job_config=None,
               dynamic_file_sources=None, token_endpoint=None):
        """Submit a job by posting a setup message to the relay.

        Args:
            command_line: Command to execute on Pulsar
            dependencies_description: Tool dependencies
            env: Environment variables
            remote_staging: Remote staging configuration
            job_config: Job configuration
            dynamic_file_sources: Dynamic file sources
            token_endpoint: Token endpoint for file access

        Returns:
            None (async operation)
        """
        launch_params = self._build_setup_message(
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            remote_staging=remote_staging,
            job_config=job_config,
            dynamic_file_sources=dynamic_file_sources,
            token_endpoint=token_endpoint,
        )

        # Determine topic name based on manager
        manager_name = self.client_manager.manager_name
        topic = self.client_manager._make_topic_name("job_setup", manager_name)

        # Post message to relay
        self.client_manager.relay_transport.post_message(topic, launch_params)
        log.info("Job %s published to relay topic '%s'", self.job_id, topic)
        return None

    def get_status(self):
        """Request job status by posting a status request message to the relay.

        Returns:
            Cached status if available, None otherwise
        """
        manager_name = self.client_manager.manager_name
        topic = self.client_manager._make_topic_name("job_status_request", manager_name)

        status_params = {
            'job_id': self.job_id,
        }

        self.client_manager.relay_transport.post_message(topic, status_params)
        log.debug("Job status request for %s published to relay topic '%s'", self.job_id, topic)

        # Return cached status if available
        return self.client_manager.status_cache.get(self.job_id, {}).get('status', None)

    def kill(self):
        """Kill a job by posting a kill message to the relay."""
        manager_name = self.client_manager.manager_name
        topic = self.client_manager._make_topic_name("job_kill", manager_name)

        kill_params = {'job_id': self.job_id}
        self.client_manager.relay_transport.post_message(topic, kill_params)
        log.info("Job kill request for %s published to relay topic '%s'", self.job_id, topic)


class InputCachingJobClient(JobClient):
    """
    Beta client that cache's staged files to prevent duplication.
    """

    def __init__(self, destination_params, job_id, job_manager_interface, client_cacher):
        super().__init__(destination_params, job_id, job_manager_interface)
        self.client_cacher = client_cacher

    @parseJson()
    def _upload_file(self, args, contents, input_path):
        action = "upload_file"
        if contents:
            input_path = None
            return self._raw_execute(action, args, contents, input_path)
        else:
            event_holder = self.client_cacher.acquire_event(input_path)
            cache_required = self.cache_required(input_path)
            if cache_required:
                self.client_cacher.queue_transfer(self, input_path)
            while not event_holder.failed:
                available = self.file_available(input_path)
                if available['ready']:
                    token = available['token']
                    args["cache_token"] = token
                    return self._raw_execute(action, args)
                event_holder.event.wait(30)
            if event_holder.failed:
                raise Exception("Failed to transfer file %s" % input_path)

    @parseJson()
    def cache_required(self, path):
        return self._raw_execute("cache_required", {"path": path})

    @parseJson()
    def cache_insert(self, path):
        return self._raw_execute("cache_insert", {"path": path}, None, path)

    @parseJson()
    def file_available(self, path):
        return self._raw_execute("file_available", {"path": path})


def _copy(from_path, to_path):
    message = "Copying path [%s] to [%s]"
    log.debug(message, from_path, to_path)
    copy(from_path, to_path)


def _setup_params_from_job_config(job_config):
    job_id = job_config.get("job_id", None)
    tool_id = job_config.get("tool_id", None)
    tool_version = job_config.get("tool_version", None)
    preserve_galaxy_python_environment = job_config.get("preserve_galaxy_python_environment", None)
    # use_metadata ignored post Pulsar 0.14.12+ but keep setting it for older Pulsar's that
    # had hacks for pre-2017 Galaxies.
    return {
        "job_id": job_id,
        "tool_id": tool_id,
        "tool_version": tool_version,
        "use_metadata": True,
        "preserve_galaxy_python_environment": preserve_galaxy_python_environment,
    }
