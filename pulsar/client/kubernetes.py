"""Container coexecution through Kubernetes."""

import logging
from typing import (
    Any,
    Dict,
    Optional,
)

from pulsar.managers import status as manager_status
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
from .client import CONTAINER_STAGING_DIRECTORY
from .coexecution import (
    BaseMessageCoexecutionJobClient,
    BasePollingCoexecutionJobClient,
    CoexecutionLaunchMixin,
    ExecutionType,
)
from .container_job_config import CoexecutionContainerCommand

log = logging.getLogger(__name__)


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
