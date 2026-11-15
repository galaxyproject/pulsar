"""Shared container launch behavior, independent of scheduler SDKs."""

from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from .client import (
    BaseMessageJobClient,
    BaseRemoteConfiguredJobClient,
    CONTAINER_STAGING_DIRECTORY,
)
from .container_job_config import CoexecutionContainerCommand
from .util import (
    ExternalId,
    to_base64_json,
    to_base64_zlib_json,
)

# The longest argument Linux passes to a program: MAX_ARG_STRLEN (32 pages)
# less the terminating NUL. Container runtimes exec pulsar-submit with the
# launch message as one argument.
MAX_ARGUMENT_LENGTH = 32 * 4096 - 1
PULSAR_CONTAINER_IMAGE = "galaxy/pulsar-pod-staging:0.15.0.2"
TOOL_EXECUTION_CONTAINER_COMMAND_TEMPLATE = """
path='%s/command_line';
while [ ! -e $path ];
    do sleep 1; echo "waiting for job script $path";
done;
echo 'running script';
sh $path;
echo 'ran script'"""


def job_message_arguments(launch_params: Dict[str, Any]) -> List[str]:
    """The pulsar-submit arguments carrying the launch message.

    A message that fits in one argument stays plain ``--base64``, which every
    staging image reads. A longer one, about 110 inputs or more, goes
    compressed as ``--base64_zlib``; staging images older than that option
    reject it when parsing their arguments.
    """
    message = to_base64_json(launch_params)
    if len(message) <= MAX_ARGUMENT_LENGTH:
        return ["--base64", message]
    compressed = to_base64_zlib_json(launch_params)
    if len(compressed) > MAX_ARGUMENT_LENGTH:
        raise Exception(
            f"The launch message of job {launch_params.get('job_id')} is too large to start a container with: "
            f"{len(compressed)} bytes compressed, and a container argument can be at most {MAX_ARGUMENT_LENGTH}."
        )
    return ["--base64_zlib", compressed]


class ExecutionType(str, Enum):
    # containers run one after each other with similar configuration
    # like in TES or AWS Batch
    SEQUENTIAL = "sequential"
    # containers run concurrently with the same file system - like K8S
    PARALLEL = "parallel"


class CoexecutionLaunchMixin(BaseRemoteConfiguredJobClient):
    execution_type: ExecutionType
    pulsar_container_image: str

    def default_staging_directory(self, destination_params):
        return CONTAINER_STAGING_DIRECTORY

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
        pulsar_app_config = self.get_pulsar_app_config(
            pulsar_app_config=pulsar_app_config,
            container=container,
            wait_after_submission=wait_after_submission,
            manager_name=manager_name,
            manager_type=manager_type,
            dependencies_description=dependencies_description,
        )

        job_message_args = job_message_arguments(launch_params)
        base64_app_conf = to_base64_json(pulsar_app_config)
        pulsar_container_image = self.pulsar_container_image

        wait_arg = "--wait" if wait_after_submission else "--no-wait"
        pulsar_container = CoexecutionContainerCommand(
            pulsar_container_image,
            "pulsar-submit",
            self._pulsar_script_args(manager_name, job_message_args, base64_app_conf, wait_arg=wait_arg),
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
                self._pulsar_script_args(manager_name, job_message_args, base64_app_conf),
                "/",
                None,
            )

        return self._launch_containers(pulsar_container, tool_container, pulsar_finish_container)

    def _pulsar_script_args(self, manager_name, job_message_args, base64_app_conf, wait_arg=None):
        manager_args = []
        if manager_name != "_default_":
            manager_args.append("--manager")
            manager_args.append(manager_name)
        if wait_arg:
            manager_args.append(wait_arg)
        manager_args.extend([*job_message_args, "--app_conf_base64", base64_app_conf])
        return manager_args

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
