import logging
import os
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    NamedTuple,
    Optional,
)
from typing_extensions import Protocol

from pulsar.managers.util.tes import (
    ensure_tes_client,
    TesClient,
    TesExecutor,
    TesState,
    TesTask,
    tes_client_from_dict,
    tes_galaxy_instance_id,
    tes_resources,
)
from pulsar.managers.util.pykube_util import (
    ensure_pykube,
    find_job_object_by_name,
    find_pod_object_by_name,
    galaxy_instance_id,
    Job,
    job_object_dict,
    produce_unique_k8s_job_name,
    pull_policy,
    pykube_client_from_dict,
    stop_job,
)
from pulsar.managers import status as manager_status
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
from .job_directory import RemoteJobDirectory
from .setup_handler import build as build_setup_handler
from .util import (
    copy,
    ensure_directory,
    ExternalId,
    json_dumps,
    json_loads,
    MonitorStyle,
    to_base64_json,
)

log = logging.getLogger(__name__)

CACHE_WAIT_SECONDS = 3
TOOL_EXECUTION_CONTAINER_COMMAND_TEMPLATE = """
path='%s/command_line';
while [ ! -e $path ];
    do sleep 1; echo "waiting for job script $path";
done;
echo 'running script';
sh $path;
echo 'ran script'"""


PULSAR_CONTAINER_IMAGE = "galaxy/pulsar-pod-staging:0.15.0.0"
CONTAINER_STAGING_DIRECTORY = "/pulsar_staging/"


class OutputNotFoundException(Exception):

    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "No remote output found for path %s" % self.path


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
        self.files_endpoint = destination_params.get("files_endpoint", None)
        self.token_endpoint = destination_params.get("token_endpoint", None)

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
        launch_params = dict(command_line=command_line, job_id=self.job_id)
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
        launch_params = dict(command_line=command_line, job_id=self.job_id)
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

        if job_config and self.setup_handler.local:
            # Setup not yet called, job properties were inferred from
            # destination arguments. Hence, must have Pulsar setup job
            # before queueing.
            setup_params = _setup_params_from_job_config(job_config)
            launch_params["setup_params"] = setup_params
        return launch_params


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
            raise Exception("full_status() called for [%s] before a final status was properly cached with cilent manager." % job_id)
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
        self.client_manager.exchange.publish("kill", dict(job_id=self.job_id))


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
        self.shell.execute("nohup {} --base64 {} &".format(submit_command, base64_message))

    def kill(self):
        # TODO
        pass


class CoexecutionContainerCommand(NamedTuple):
    image: str
    command: str
    args: List[str]
    working_directory: str
    ports: Optional[List[int]] = None


class ExecutionType(str, Enum):
    # containers run one after each other with similar configuration
    # like in TES or AWS Batch
    SEQUENTIAL = "sequential"
    # containers run concurrently with the same file system - like K8S
    PARALLEL = "parallel"


class CoexecutionLaunchMixin(BaseRemoteConfiguredJobClient):
    execution_type: ExecutionType
    pulsar_container_image: str

    def launch(
        self,
        command_line,
        dependencies_description=None,
        env=None,
        remote_staging=None,
        job_config=None,
        dynamic_file_sources=None,
        container_info=None,
        token_endpoint=None,
        pulsar_app_config=None
    ) -> Optional[ExternalId]:
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
        container = None
        guest_ports = None
        if container_info is not None:
            container = container_info.get("container_id")
            guest_ports = container_info.get("guest_ports")
        wait_after_submission = not (container and self.execution_type == ExecutionType.SEQUENTIAL)

        manager_name = self.client_manager.manager_name
        manager_type = "coexecution" if container is not None else "unqueued"
        pulsar_app_config = pulsar_app_config or {}
        manager_config = self._ensure_manager_config(
            pulsar_app_config, manager_name, manager_type,
        )

        if "staging_directory" not in manager_config and "staging_directory" not in pulsar_app_config:
            pulsar_app_config["staging_directory"] = CONTAINER_STAGING_DIRECTORY

        if self.amqp_key_prefix:
            pulsar_app_config["amqp_key_prefix"] = self.amqp_key_prefix

        if "monitor" not in manager_config:
            manager_config["monitor"] = MonitorStyle.BACKGROUND.value if wait_after_submission else MonitorStyle.NONE.value
        if "persistence_directory" not in pulsar_app_config:
            pulsar_app_config["persistence_directory"] = os.path.join(CONTAINER_STAGING_DIRECTORY, "persisted_data")
        elif "manager" in pulsar_app_config and manager_name != '_default_':
            log.warning(
                "'manager' set in app config but client has non-default manager '%s', this will cause communication"
                " failures, remove `manager` from app or client config to fix", manager_name)

        using_dependencies = container is None and dependencies_description is not None
        if using_dependencies and "dependency_resolution" not in pulsar_app_config:
            # Setup default dependency resolution for container above...
            dependency_resolution = {
                "cache": False,
                "use": True,
                "default_base_path": "/pulsar_dependencies",
                "cache_dir": "/pulsar_dependencies/_cache",
                "resolvers": [{  # TODO: add CVMFS resolution...
                    "type": "conda",
                    "auto_init": True,
                    "auto_install": True,
                    "prefix": '/pulsar_dependencies/conda',
                }, {
                    "type": "conda",
                    "auto_init": True,
                    "auto_install": True,
                    "prefix": '/pulsar_dependencies/conda',
                    "versionless": True,
                }]
            }
            pulsar_app_config["dependency_resolution"] = dependency_resolution
        base64_message = to_base64_json(launch_params)
        base64_app_conf = to_base64_json(pulsar_app_config)
        pulsar_container_image = self.pulsar_container_image

        wait_arg = "--wait" if wait_after_submission else "--no-wait"
        pulsar_container = CoexecutionContainerCommand(
            pulsar_container_image,
            "pulsar-submit",
            self._pulsar_script_args(manager_name, base64_message, base64_app_conf, wait_arg=wait_arg),
            "/",
            None,
        )

        tool_container = None  # Default to just use dependency resolution in Pulsar container
        if container:
            job_directory = self.job_directory
            command = TOOL_EXECUTION_CONTAINER_COMMAND_TEMPLATE % job_directory.job_directory
            ports = None
            if guest_ports:
                ports = [int(p) for p in guest_ports]

            tool_container = CoexecutionContainerCommand(
                container,
                "sh",
                ["-c", command],
                "/",
                ports,
            )

        pulsar_finish_container: Optional[CoexecutionContainerCommand] = None
        if not wait_after_submission:
            pulsar_finish_container = CoexecutionContainerCommand(
                pulsar_container_image,
                "pulsar-finish",
                self._pulsar_script_args(manager_name, base64_message, base64_app_conf),
                "/",
                None,
            )

        return self._launch_containers(pulsar_container, tool_container, pulsar_finish_container)

    def _pulsar_script_args(self, manager_name, base64_job, base64_app_conf, wait_arg=None):
        manager_args = []
        if manager_name != "_default_":
            manager_args.append("--manager")
            manager_args.append(manager_name)
        if wait_arg:
            manager_args.append(wait_arg)
        manager_args.extend(["--base64", base64_job, "--app_conf_base64", base64_app_conf])
        return manager_args

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

    def _launch_containers(
        self,
        pulsar_submit_container: CoexecutionContainerCommand,
        tool_container: Optional[CoexecutionContainerCommand],
        pulsar_finish_container: Optional[CoexecutionContainerCommand]
    ) -> Optional[ExternalId]:
        ...


class BaseMessageCoexecutionJobClient(BaseMessageJobClient):
    pulsar_container_image: str

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self.pulsar_container_image = destination_params.get("pulsar_container_image", PULSAR_CONTAINER_IMAGE)


class BasePollingCoexecutionJobClient(BaseRemoteConfiguredJobClient):
    pulsar_container_image: str

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self.pulsar_container_image = destination_params.get("pulsar_container_image", PULSAR_CONTAINER_IMAGE)


def tes_state_to_pulsar_status(state: Optional[TesState]) -> str:
    state = state or TesState.UNKNOWN
    state_map = {
        TesState.UNKNOWN: manager_status.FAILED,
        TesState.INITIALIZING: manager_status.PREPROCESSING,
        TesState.RUNNING: manager_status.RUNNING,
        TesState.PAUSED: manager_status.RUNNING,
        TesState.COMPLETE: manager_status.COMPLETE,
        TesState.EXECUTOR_ERROR: manager_status.FAILED,
        TesState.SYSTEM_ERROR: manager_status.FAILED,
        TesState.CANCELED: manager_status.CANCELLED,
    }
    if state not in state_map:
        log.warning(f"Unknown tes state encountered [{state}]")
        return manager_status.FAILED
    else:
        return state_map[state]


def tes_state_is_complete(state: Optional[TesState]) -> bool:
    state = state or TesState.UNKNOWN
    state_map = {
        TesState.UNKNOWN: True,
        TesState.INITIALIZING: False,
        TesState.RUNNING: False,
        TesState.PAUSED: False,
        TesState.COMPLETE: True,
        TesState.EXECUTOR_ERROR: True,
        TesState.SYSTEM_ERROR: True,
        TesState.CANCELED: True,
    }
    if state not in state_map:
        log.warning(f"Unknown tes state encountered [{state}]")
        return True
    else:
        return state_map[state]


class LaunchesTesContainersMixin(CoexecutionLaunchMixin):
    """"""
    ensure_library_available = ensure_tes_client
    execution_type = ExecutionType.SEQUENTIAL

    def _launch_containers(
        self,
        pulsar_submit_container: CoexecutionContainerCommand,
        tool_container: Optional[CoexecutionContainerCommand],
        pulsar_finish_container: Optional[CoexecutionContainerCommand]
    ) -> ExternalId:
        volumes = [
            CONTAINER_STAGING_DIRECTORY,
        ]
        pulsar_container_executor = self._container_to_executor(pulsar_submit_container)
        executors = [pulsar_container_executor]
        if tool_container:
            tool_container_executor = self._container_to_executor(tool_container)
            executors.append(tool_container_executor)

            assert pulsar_finish_container
            pulsar_finish_executor = self._container_to_executor(pulsar_finish_container)
            executors.append(pulsar_finish_executor)

        name = self._tes_job_name
        tes_task = TesTask(
            name=name,
            executors=executors,
            volumes=volumes,
            resources=tes_resources(self.destination_params)
        )
        created_task = self._tes_client.create_task(tes_task)
        return ExternalId(created_task.id)

    def _container_to_executor(self, container: CoexecutionContainerCommand) -> TesExecutor:
        if container.ports:
            raise Exception("exposing container ports not possible via TES")
        return TesExecutor(
            image=container.image,
            command=[container.command] + container.args,
            workdir=container.working_directory,
        )

    @property
    def _tes_client(self) -> TesClient:
        return tes_client_from_dict(self.destination_params)

    @property
    def _tes_job_name(self):
        # currently just _k8s_job_prefix... which might be fine?
        job_id = self.job_id
        job_name = produce_unique_k8s_job_name(app_prefix="pulsar", job_id=job_id, instance_id=self.instance_id)
        return job_name

    def _setup_tes_client_properties(self, destination_params):
        self.instance_id = tes_galaxy_instance_id(destination_params)

    def kill(self):
        self._tes_client.cancel_task(self.job_id)

    def clean(self):
        pass

    def raw_check_complete(self) -> Dict[str, Any]:
        tes_task: TesTask = self._tes_client.get_task(self.job_id, "FULL")
        tes_state = tes_task.state
        return {
            "status": tes_state_to_pulsar_status(tes_state),
            "complete": "true" if tes_state_is_complete(tes_state) else "false",  # Ancient John, what were you thinking?
        }


class TesPollingCoexecutionJobClient(BasePollingCoexecutionJobClient, LaunchesTesContainersMixin):
    """A client that co-executes pods via GA4GH TES and depends on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self._setup_tes_client_properties(destination_params)


class TesMessageCoexecutionJobClient(BaseMessageCoexecutionJobClient, LaunchesTesContainersMixin):
    """A client that co-executes pods via GA4GH TES and doesn't depend on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self._setup_tes_client_properties(destination_params)


class LaunchesK8ContainersMixin(CoexecutionLaunchMixin):
    """Mixin to provide K8 launch and kill interaction."""
    ensure_library_available = ensure_pykube
    execution_type = ExecutionType.PARALLEL

    def _launch_containers(
        self,
        pulsar_submit_container: CoexecutionContainerCommand,
        tool_container: Optional[CoexecutionContainerCommand],
        pulsar_finish_container: Optional[CoexecutionContainerCommand]
    ) -> None:
        assert pulsar_finish_container is None
        volumes = [
            {"name": "staging-directory", "emptyDir": {}},
        ]
        volume_mounts = [
            {"mountPath": CONTAINER_STAGING_DIRECTORY, "name": "staging-directory"},
        ]
        pulsar_container_dict = self._container_command_to_dict("pulsar-container", pulsar_submit_container)
        pulsar_container_resources = self._pulsar_container_resources
        if pulsar_container_resources:
            pulsar_container_dict["resources"] = pulsar_container_resources
        pulsar_container_dict["volumeMounts"] = volume_mounts

        container_dicts = [pulsar_container_dict]
        if tool_container:
            tool_container_dict = self._container_command_to_dict("tool-container", tool_container)
            tool_container_resources = self._tool_container_resources
            if tool_container_resources:
                tool_container_dict["resources"] = tool_container_resources
            tool_container_dict["volumeMounts"] = volume_mounts
            container_dicts.append(tool_container_dict)
        for container_dict in container_dicts:
            if self._default_pull_policy:
                container_dict["imagePullPolicy"] = self._default_pull_policy

        job_name = self._k8s_job_name
        template = {
            "metadata": {
                "labels": {"app": job_name},
            },
            "spec": {
                "volumes": volumes,
                "restartPolicy": "Never",
                "containers": container_dicts,
            }
        }
        spec = {"template": template}
        params = self.destination_params
        spec.update(self._job_spec_params(params))
        k8s_job_obj = job_object_dict(params, job_name, spec)
        pykube_client = self._pykube_client
        job = Job(pykube_client, k8s_job_obj)
        job.create()

    def _container_command_to_dict(self, name: str, container: CoexecutionContainerCommand) -> Dict[str, Any]:
        container_dict: Dict[str, Any] = {
            "name": name,
            "image": container.image,
            "command": [container.command],
            "args": container.args,
            "workingDir": container.working_directory,
        }
        ports = container.ports
        if ports:
            container_dict["ports"] = [{"containerPort": p} for p in ports]

        return container_dict

    def kill(self):
        job_name = self._k8s_job_name
        pykube_client = self._pykube_client
        job = find_job_object_by_name(pykube_client, job_name)
        if job:
            log.info("Kill k8s job with name %s" % job_name)
            stop_job(job)
        else:
            log.info("Attempted to kill k8s job but it is unavailable.")

    def clean(self):
        self.kill()  # pretty much the same here right?

    def job_ip(self):
        job_name = self._k8s_job_name
        pykube_client = self._pykube_client
        pod = find_pod_object_by_name(pykube_client, job_name)
        if pod:
            status = pod.obj['status']
        else:
            status = {}

        if 'podIP' in status:
            pod_ip = status['podIP']
            return pod_ip
        else:
            log.debug("Attempted to get ports dict but k8s pod unavailable")

    @property
    def _pykube_client(self):
        return pykube_client_from_dict(self.destination_params)

    @property
    def _k8s_job_name(self):
        job_id = self.job_id
        job_name = produce_unique_k8s_job_name(app_prefix="pulsar", job_id=job_id, instance_id=self.instance_id)
        return job_name

    def _job_spec_params(self, params):
        spec = {}
        if "k8s_walltime_limit" in params:
            spec["activeDeadlineSeconds"] = int(params["k8s_walltime_limit"])
        if "k8s_job_ttl_secs_after_finished" in params and params.get("k8s_cleanup_job") != "never":
            spec["ttlSecondsAfterFinished"] = int(params["k8s_job_ttl_secs_after_finished"])
        return spec

    @property
    def _pulsar_container_resources(self):
        params = self.destination_params
        return self._container_resources(params, container='pulsar')

    @property
    def _tool_container_resources(self):
        params = self.destination_params
        return self._container_resources(params, container='tool')

    def _container_resources(self, params, container=None):
        resources = {}
        for resource_param in ('requests_cpu', 'requests_memory', 'limits_cpu', 'limits_memory'):
            subkey, resource = resource_param.split('_', 1)
            if resource_param in params:
                if subkey not in resources:
                    resources[subkey] = {}
                resources[subkey][resource] = params[resource_param]
            if container is not None and container + '_' + resource_param in params:
                if subkey not in resources:
                    resources[subkey] = {}
                resources[subkey][resource] = params[container + '_' + resource_param]
        return resources

    def _setup_k8s_client_properties(self, destination_params):
        self.instance_id = galaxy_instance_id(destination_params)
        self._default_pull_policy = pull_policy(destination_params)


class K8sMessageCoexecutionJobClient(BaseMessageCoexecutionJobClient, LaunchesK8ContainersMixin):
    """A client that co-executes pods via Kubernetes and depends on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self._setup_k8s_client_properties(destination_params)


class K8sPollingCoexecutionJobClient(BasePollingCoexecutionJobClient, LaunchesK8ContainersMixin):
    """A client that co-executes pods via Kubernetes and doesn't depend on amqp."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self._setup_k8s_client_properties(destination_params)

    def full_status(self):
        status = self._raw_check_complete()
        return status

    def raw_check_complete(self):
        return self._raw_check_complete()

    def _raw_check_complete(self):
        job_name = self._k8s_job_name
        pykube_client = self._pykube_client
        job = find_job_object_by_name(pykube_client, job_name)
        job_failed = (job.obj['status']['failed'] > 0
                      if 'failed' in job.obj['status'] else False)
        job_active = (job.obj['status']['active'] > 0
                      if 'active' in job.obj['status'] else False)
        job_succeeded = (job.obj['status']['succeeded'] > 0
                         if 'succeeded' in job.obj['status'] else False)
        if job_failed:
            status = manager_status.FAILED
        elif job_succeeded > 0 and job_active == 0:
            status = manager_status.COMPLETE
        elif job_active >= 0:
            status = manager_status.RUNNING
        else:
            status = manager_status.FAILED

        return {
            "status": status,
            "complete": "true" if manager_status.is_job_done(status) else "false",  # Ancient John, what were you thinking?
        }


class LaunchesAwsBatchContainersMixin(CoexecutionLaunchMixin):
    """..."""
    execution_type = ExecutionType.SEQUENTIAL


class AwsBatchPollingCoexecutionJobClient(BasePollingCoexecutionJobClient, LaunchesAwsBatchContainersMixin):
    """A client that co-executes pods via AWS Batch and doesn't depend on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        raise NotImplementedError()


class AwsBatchMessageCoexecutionJobClient(BasePollingCoexecutionJobClient, LaunchesAwsBatchContainersMixin):
    """A client that co-executes pods via AWS Batch and depends on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        raise NotImplementedError()


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
    return dict(
        job_id=job_id,
        tool_id=tool_id,
        tool_version=tool_version,
        use_metadata=True,
        preserve_galaxy_python_environment=preserve_galaxy_python_environment,
    )
