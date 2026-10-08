"""Shared container launch behavior, independent of scheduler SDKs."""

from enum import Enum
from typing import Optional

from .client import (
    BaseMessageJobClient,
    BaseRemoteConfiguredJobClient,
    CONTAINER_STAGING_DIRECTORY,
)
from .container_job_config import CoexecutionContainerCommand
from .util import (
    ExternalId,
    to_base64_json,
)

PULSAR_CONTAINER_IMAGE = "galaxy/pulsar-pod-staging:0.15.0.0"
TOOL_EXECUTION_CONTAINER_COMMAND_TEMPLATE = """
path='%s/command_line';
while [ ! -e $path ];
    do sleep 1; echo "waiting for job script $path";
done;
echo 'running script';
sh $path;
echo 'ran script'"""


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
