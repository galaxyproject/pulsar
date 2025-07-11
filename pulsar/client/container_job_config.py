"""Setup config objects for Pulsar client container jobs.

In a traditional batch Pulsar setup, job configuration is configured per destination
by configuring the manager the Pulsar client connects to. In a container job setup,
there is no Pulsar server component and the Pulsar client is responsible for configuring
the job configuration. This module provides the necessary configuration objects and
documents how to map Galaxy job environment configuration objects to the container scheduling
infrastructure.
"""
import base64
import re
from typing import (
    Dict,
    List,
    NamedTuple,
    Optional,
)

from galaxy.util import listify
from pydantic import (
    BaseModel,
    Field,
)
from pydantictes.models import TesResources
from typing_extensions import Literal

from pulsar.managers.util.gcp_util import (
    batch_v1,
    ensure_client as ensure_gcp_client,
)
from pulsar.managers.util.tes import TesClient


DEFAULT_GCP_WALLTIME_LIMIT = 60 * 60 * 24  # Default wall time limit in seconds


class CoexecutionContainerCommand(NamedTuple):
    image: str
    command: str
    args: List[str]
    working_directory: str
    ports: Optional[List[int]] = None


def attribute_docs(gcp_class_name: str, attribute: str) -> Optional[str]:
    """
    Extracts the documentation string for a given attribute from a class docstring.

    Args:
        cls: The class object containing the docstring.
        attr_name: The attribute name to extract documentation for.

    Returns:
        A string containing the attribute's documentation, or None if not found.
    """
    gcp_class = getattr(batch_v1, gcp_class_name, None)
    if not gcp_class:
        return None

    doc = gcp_class.__doc__
    if not doc:
        return None

    lines = doc.expandtabs().splitlines()
    inside_attributes = False
    current_attr = None
    current_lines: List[str] = []
    attr_docs = {}

    attr_pattern = re.compile(r"        (\w*).*:.*")
    for line in lines:
        stripped = line.strip()

        if not inside_attributes:
            if stripped == "Attributes:":
                inside_attributes = True
            continue

        if inside_attributes:
            if line.startswith("        ") and not line.startswith("            "):  # attr line
                match = attr_pattern.match(line)
                if match:
                    if current_attr:
                        # Save previous attribute
                        attr_docs[current_attr] = "\n".join(current_lines).strip()
                    current_lines = []
                    current_attr = match.group(1)
                else:
                    continue
            elif line.startswith("            ") and current_attr:
                current_lines.append(stripped)

    if current_attr and current_lines:
        attr_docs[current_attr] = "\n".join(current_lines).strip()

    docs = attr_docs.get(attribute)
    if docs:
        return f"Docs from {gcp_class_name}.{attribute}:\n{docs}"
    else:
        return None


class GcpJobParams(BaseModel):
    project_id: str = Field(
        ..., description="GCP project ID to use for job creation."
    )
    credentials_file: Optional[str] = Field(
        None, description="Path to GCP service account credentials file."
    )
    region: str = Field(
        "us-central1", description="GCP region where the job will run."
    )
    walltime_limit: int = Field(
        DEFAULT_GCP_WALLTIME_LIMIT,
        description=f"Maximum wall time for the job in seconds. Maps to TaskSpec.max_run_duration.\n{attribute_docs('TaskSpec', 'max_run_duration')}"
    )
    retry_count: int = Field(
        2, description=f"Maximum number of retries for the job. Maps to TaskSpec.max_retry_count.\n{attribute_docs('TaskSpec', 'max_retry_count')}"
    )
    ssd_name: Optional[str] = Field(
        None, description=f"Name of the SSD volume to be mounted in the task. Maps to Volume.device_name.\n{attribute_docs('Volume', 'device_name')}"
    )
    disk_size: int = Field(
        375, description="Size of the shared local SSD disk in GB (must be a multiple of 375). Maps to AllocationPolicy.Disk.size_gb."
    )
    machine_type: str = Field(
        "n1-standard-1", description="Machine type for the job's VM."
    )
    labels: Optional[Dict[str, str]] = Field(None)


def parse_gcp_job_params(params: dict) -> GcpJobParams:
    """
    Parse GCP job parameters from a dictionary (e.g., Galaxy's job destination/environment params).
    """
    return GcpJobParams(**params)


def gcp_job_template(params: GcpJobParams) -> "batch_v1.Job":
    ensure_gcp_client()

    # https://github.com/GoogleCloudPlatform/python-docs-samples/blob/main/batch/create/create_with_ssd.py
    task = batch_v1.TaskSpec()
    task.max_retry_count = params.retry_count
    task.max_run_duration = f"{params.walltime_limit}s"

    ssd_name = params.ssd_name or "pulsar_staging"

    volume = batch_v1.Volume()
    volume.device_name = ssd_name
    mount_path = f"/mnt/disks/{ssd_name}"
    volume.mount_path = mount_path
    task.volumes = [volume]

    # override the staging directory since we cannot set the location of this mount path
    # the way we can in K8S based on @jmchilton's initial testing.
    environment = batch_v1.Environment(
        variables={
            "PULSAR_CONFIG_OVERRIDE_STAGING_DIRECTORY": mount_path,
        }
    )
    task.environment = environment

    # Tasks are grouped inside a job using TaskGroups.
    # Currently, it's possible to have only one task group.
    group = batch_v1.TaskGroup()
    group.task_count = 1
    group.task_spec = task

    disk = batch_v1.AllocationPolicy.Disk()
    disk.type_ = "local-ssd"
    # The size of all the local SSDs in GB. Each local SSD is 375 GB,
    # so this value must be a multiple of 375 GB.
    # For example, for 2 local SSDs, set this value to 750 GB.
    disk.size_gb = params.disk_size
    assert disk.size_gb % 375 == 0

    # Policies are used to define on what kind of virtual machines the tasks will run on.
    # The allowed number of local SSDs depends on the machine type for your job's VMs.
    # In this case, we tell the system to use "n1-standard-1" machine type, which require to attach local ssd manually.
    # Read more about local disks here: https://cloud.google.com/compute/docs/disks/local-ssd#lssd_disk_options
    policy = batch_v1.AllocationPolicy.InstancePolicy()
    policy.machine_type = params.machine_type

    attached_disk = batch_v1.AllocationPolicy.AttachedDisk()
    attached_disk.new_disk = disk
    attached_disk.device_name = ssd_name
    policy.disks = [attached_disk]

    instances = batch_v1.AllocationPolicy.InstancePolicyOrTemplate()
    instances.policy = policy

    allocation_policy = batch_v1.AllocationPolicy()
    allocation_policy.instances = [instances]

    job = batch_v1.Job()
    job.task_groups = [group]
    job.allocation_policy = allocation_policy
    job.labels = params.labels or {}
    # We use Cloud Logging as it's an out of the box available option
    job.logs_policy = batch_v1.LogsPolicy()
    job.logs_policy.destination = batch_v1.LogsPolicy.Destination.CLOUD_LOGGING  # type: ignore[assignment]

    return job


def gcp_job_request(params: GcpJobParams, job: "batch_v1.Job", job_name: str) -> "batch_v1.CreateJobRequest":
    create_request = batch_v1.CreateJobRequest()
    create_request.job = job
    create_request.job_id = job_name
    region = params.region
    project_id = params.project_id
    create_request.parent = f"projects/{project_id}/locations/{region}"
    return create_request


def container_command_to_gcp_runnable(name: str, container: CoexecutionContainerCommand) -> "batch_v1.Runnable":
    runnable = batch_v1.Runnable()
    runnable.container = batch_v1.Runnable.Container()
    runnable.container.image_uri = container.image
    runnable.container.commands = [container.command] + container.args
    # ports not supported currently
    return runnable


def gcp_galaxy_instance_id(destination_params: Dict[str, str]) -> Optional[str]:
    return destination_params.get("galaxy_instance_id")


class BasicAuth(BaseModel):
    username: str = Field(..., description="Username for basic authentication.")
    password: str = Field(..., description="Password for basic authentication.")


class TesJobParams(TesResources):
    tes_url: str = Field(..., description="URL of the TES service.")
    authorization: Literal["none", "basic"] = Field(
        "none", description="Authorization type for TES service."
    )
    basic_auth: Optional[BasicAuth] = Field(None, description="Authorization for TES service.")


def parse_tes_job_params(params: dict) -> TesJobParams:
    """
    Parse GCP job parameters parameters from a dictionary (e.g., Galaxy's job destination/environment params).
    """
    legacy_style_keys = {
        "tes_cpu_cores": "cpu_cores",
        "tes_preemptible": "preemptible",
        "tes_ram_gb": "ram_gb",
        "tes_disk_gb": "disk_gb",
        "tes_zones": "zones",
        "tes_backend_parameters": "backend_parameters",
        "tes_backend_parameters_strict": "backend_parameters_strict",
        "tes_galaxy_instance_id": "galaxy_instance_id",
    }
    expanded_params = {}
    for key, value in params.items():
        if key in legacy_style_keys:
            new_key = legacy_style_keys[key]
            expanded_params[new_key] = value
        else:
            expanded_params[key] = value

    if "zones" in expanded_params:
        expanded_params["zones"] = listify(expanded_params["zones"])

    return TesJobParams(**expanded_params)


def tes_client_from_params(tes_params: TesJobParams) -> TesClient:
    tes_url = tes_params.tes_url
    assert tes_url
    auth_type = tes_params.authorization  # Default to "none"

    headers = {}

    if auth_type == "basic":
        basic_auth = tes_params.basic_auth
        username = basic_auth.username if basic_auth else None
        password = basic_auth.password if basic_auth else None
        if username and password:
            auth_string = f"{username}:{password}"
            auth_base64 = base64.b64encode(auth_string.encode()).decode()
            headers["Authorization"] = f"Basic {auth_base64}"

    return TesClient(url=tes_url, headers=headers)


def tes_resources(tes_params: TesJobParams) -> TesResources:
    # TesJobParams subclasses it so just pass through as is.
    return tes_params
