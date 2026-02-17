import logging
import re
from typing import (
    Any,
    Optional,
)

try:
    from google.cloud import batch_v1  # type: ignore
    from google.oauth2 import service_account  # type: ignore
except ImportError as exc:
    service_account = None  # type: ignore[assignment]
    batch_v1 = None  # type: ignore[assignment]
    GCP_IMPORT_MESSAGE = (
        "The Python google-cloud-batch package is required to use "
        "this feature, please install it or correct the "
        f"following error:\nImportError {exc}"
    )

log = logging.getLogger(__name__)

# Default values for GCP Batch resource configuration
DEFAULT_MEMORY_MIB = 2048
DEFAULT_CPU_MILLI = 1000


def convert_cpu_to_milli(cpu_str):
    """
    Convert CPU specification to milli-cores.
    Supports formats like: "1", "1.5", "500m", "0.5"
    """
    if not cpu_str:
        return DEFAULT_CPU_MILLI

    cpu_str = str(cpu_str).strip()

    # Handle milli-core format (e.g., "500m")
    if cpu_str.endswith("m"):
        try:
            return int(cpu_str[:-1])
        except ValueError:
            log.warning("Invalid CPU format: %s, using default", cpu_str)
            return DEFAULT_CPU_MILLI

    # Handle decimal format (e.g., "1.5", "0.5")
    try:
        cpu_float = float(cpu_str)
        return int(cpu_float * 1000)
    except ValueError:
        log.warning("Invalid CPU format: %s, using default", cpu_str)
        return DEFAULT_CPU_MILLI


def convert_memory_to_mib(memory_str):
    """
    Convert memory specification to MiB.
    Supports formats like: "1Gi", "512Mi", "1024M", "1G", "2048"
    """
    if not memory_str:
        return DEFAULT_MEMORY_MIB

    memory_str = str(memory_str).strip()

    # Handle plain numbers (assume MiB)
    if memory_str.isdigit():
        return int(memory_str)

    # Extract number and unit
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Za-z]*)$", memory_str)
    if not match:
        log.warning("Invalid memory format: %s, using default", memory_str)
        return DEFAULT_MEMORY_MIB

    value = float(match.group(1))
    unit = match.group(2).lower()

    # Convert to MiB based on unit
    if unit in ["", "mib", "mi"]:
        return int(value)
    elif unit in ["gib", "gi"]:
        return int(value * 1024)  # GiB to MiB
    elif unit in ["mb", "m"]:
        return int(value * 1000 / 1024)  # MB to MiB (decimal to binary)
    elif unit in ["gb", "g"]:
        return int(value * 1000 * 1000 / 1024 / 1024)  # GB to MiB
    elif unit in ["kib", "ki"]:
        return int(value / 1024)  # KiB to MiB
    elif unit in ["kb", "k"]:
        return int(value * 1000 / 1024 / 1024)  # KB to MiB
    else:
        log.warning("Unknown memory unit: %s, treating as MiB", unit)
        return int(value)


def compute_machine_type(cpu_milli, memory_mib, machine_type_family="n2"):
    """
    Compute an appropriate GCP machine type based on resource requirements.

    Selects the appropriate machine type variant based on CPU-to-memory ratio:
    - highcpu: ~0.9 GB per vCPU (CPU-intensive workloads)
    - standard: 4 GB per vCPU (balanced workloads)
    - highmem: 8 GB per vCPU (memory-intensive workloads)

    Args:
        cpu_milli: CPU requirement in milli-cores (1000 = 1 vCPU)
        memory_mib: Memory requirement in MiB
        machine_type_family: Machine family prefix (default: n2)

    Returns:
        Machine type string (e.g., "n2-standard-8", "n2-highmem-16")
    """
    # Valid sizes for n2 machine types
    valid_sizes = [2, 4, 8, 16, 32, 48, 64, 80, 96, 128]

    # Memory per vCPU for each variant (in GB)
    variants = {
        "highcpu": 0.9,  # ~0.9 GB per vCPU
        "standard": 4.0,  # 4 GB per vCPU
        "highmem": 8.0,  # 8 GB per vCPU
    }

    # Calculate minimum vCPUs needed for CPU requirement
    cpu_vcpus = max(1, (cpu_milli + 999) // 1000)  # Round up, minimum 1

    # Convert memory to GB
    memory_gb = memory_mib / 1024.0

    # Calculate memory per vCPU ratio based on request
    if cpu_vcpus > 0:
        requested_mem_per_vcpu = memory_gb / cpu_vcpus
    else:
        requested_mem_per_vcpu = memory_gb

    # Select variant based on memory-per-vCPU ratio
    if requested_mem_per_vcpu <= 2.0:
        variant = "highcpu"
        mem_per_vcpu = variants["highcpu"]
    elif requested_mem_per_vcpu <= 6.0:
        variant = "standard"
        mem_per_vcpu = variants["standard"]
    else:
        variant = "highmem"
        mem_per_vcpu = variants["highmem"]

    # Calculate minimum vCPUs needed for memory with selected variant
    memory_vcpus = max(1, int((memory_gb + mem_per_vcpu - 0.001) // mem_per_vcpu))

    # Take the larger of CPU and memory requirements
    min_vcpus = max(cpu_vcpus, memory_vcpus)

    # Find the smallest valid size that meets the requirement
    selected_size = None
    for size in valid_sizes:
        if size >= min_vcpus:
            selected_size = size
            break

    # If requirements exceed largest size, use the largest
    if selected_size is None:
        selected_size = valid_sizes[-1]
        log.warning(
            "Resource requirements (CPU: %d mCPU, Memory: %d MiB) exceed largest %s-%s size, using %s-%s-%d",
            cpu_milli,
            memory_mib,
            machine_type_family,
            variant,
            machine_type_family,
            variant,
            selected_size,
        )

    machine_type = f"{machine_type_family}-{variant}-{selected_size}"
    log.debug(
        "Computed machine type %s for resources: %d mCPU, %d MiB (%.1f GB/vCPU ratio)",
        machine_type,
        cpu_milli,
        memory_mib,
        requested_mem_per_vcpu,
    )
    return machine_type


def ensure_client():
    if batch_v1 is None:
        raise Exception(GCP_IMPORT_MESSAGE)


def gcp_client(credentials_file: Optional[str]) -> "batch_v1.BatchServiceClient":
    if credentials_file:
        credentials = service_account.Credentials.from_service_account_file(credentials_file)
        client = batch_v1.BatchServiceClient(credentials=credentials)
    else:
        client = batch_v1.BatchServiceClient()
    return client


def get_gcp_job(
    project_id: str,
    region: str,
    job_name: str,
    credentials_file: Optional[str] = None,
) -> "batch_v1.Job":
    """
    Retrieve a GCP Batch job by its name.

    Args:
        project_id: GCP project ID.
        region: GCP region where the job is located.
        job_name: Name of the job to retrieve.
        credentials_file: Path to GCP service account credentials file (optional).

    Returns:
        The GCP Batch job object.
    """
    ensure_client()
    client = gcp_client(credentials_file)
    return client.get_job(
        name=f"projects/{project_id}/locations/{region}/jobs/{job_name}"
    )


def delete_gcp_job(
    project_id: str,
    region: str,
    job_name: str,
    credentials_file: Optional[str] = None,
) -> Any:
    ensure_client()
    client = gcp_client(credentials_file)
    return client.delete_job(
        name=f"projects/{project_id}/locations/{region}/jobs/{job_name}"
    )


__all__ = (
    "DEFAULT_CPU_MILLI",
    "DEFAULT_MEMORY_MIB",
    "batch_v1",
    "compute_machine_type",
    "convert_cpu_to_milli",
    "convert_memory_to_mib",
    "delete_gcp_job",
    "ensure_client",
    "gcp_client",
    "get_gcp_job",
)
