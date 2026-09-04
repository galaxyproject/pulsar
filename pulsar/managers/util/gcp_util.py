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

# Predefined N2 shapes, expressed as (vCPUs, memory GiB). N2 highmem-128
# is the one exception to the otherwise regular 8 GiB/vCPU highmem ratio.
N2_MACHINE_SHAPES = {
    "highcpu": [(size, size) for size in [2, 4, 8, 16, 32, 48, 64, 80, 96]],
    "standard": [(size, size * 4) for size in [2, 4, 8, 16, 32, 48, 64, 80, 96, 128]],
    "highmem": [(size, size * 8) for size in [2, 4, 8, 16, 32, 48, 64, 80, 96]] + [(128, 864)],
}


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

    Selects the appropriate N2 variant based on CPU-to-memory ratio, then
    chooses the smallest predefined shape that satisfies both requirements.

    Args:
        cpu_milli: CPU requirement in milli-cores (1000 = 1 vCPU)
        memory_mib: Memory requirement in MiB
        machine_type_family: Machine family prefix (default: n2)

    Returns:
        Machine type string (e.g., "n2-standard-8", "n2-highmem-16")
    """
    if machine_type_family != "n2":
        raise ValueError("Dynamic machine sizing currently supports only the n2 family")
    if cpu_milli <= 0 or memory_mib <= 0:
        raise ValueError("CPU and memory requirements must both be greater than zero")

    # Calculate minimum vCPUs needed for CPU requirement
    cpu_vcpus = max(1, (cpu_milli + 999) // 1000)  # Round up, minimum 1

    memory_gib = memory_mib / 1024.0
    requested_mem_per_vcpu = memory_gib / cpu_vcpus

    # Prefer the least memory-rich family that naturally fits the requested
    # ratio. If that family tops out before the CPU request, fall through to a
    # larger family rather than inventing an unsupported machine type.
    if requested_mem_per_vcpu <= 1.0:
        variants = ["highcpu", "standard", "highmem"]
    elif requested_mem_per_vcpu <= 4.0:
        variants = ["standard", "highmem"]
    else:
        variants = ["highmem"]

    for variant in variants:
        for vcpus, memory_gib_capacity in N2_MACHINE_SHAPES[variant]:
            if vcpus >= cpu_vcpus and memory_gib_capacity >= memory_gib:
                machine_type = f"n2-{variant}-{vcpus}"
                log.debug(
                    "Computed machine type %s for resources: %d mCPU, %d MiB (%.1f GiB/vCPU ratio)",
                    machine_type,
                    cpu_milli,
                    memory_mib,
                    requested_mem_per_vcpu,
                )
                return machine_type

    raise ValueError(
        "Predefined N2 machine types cannot satisfy resource requirements "
        f"(CPU: {cpu_milli} mCPU, memory: {memory_mib} MiB)"
    )


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
