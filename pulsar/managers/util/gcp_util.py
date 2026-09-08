import logging
import math
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
BYTES_PER_MIB = 1024 * 1024
MEMORY_UNIT_TO_MIB = {
    "k": 1000 / BYTES_PER_MIB,
    "kb": 1000 / BYTES_PER_MIB,
    "ki": 1 / 1024,
    "kib": 1 / 1024,
    "m": 1000 * 1000 / BYTES_PER_MIB,
    "mb": 1000 * 1000 / BYTES_PER_MIB,
    "mi": 1,
    "mib": 1,
    "g": 1000 * 1000 * 1000 / BYTES_PER_MIB,
    "gb": 1000 * 1000 * 1000 / BYTES_PER_MIB,
    "gi": 1024,
    "gib": 1024,
}

# Predefined N2 shapes, expressed as (vCPUs, memory GiB). N2 highmem-128
# is the one exception to the otherwise regular 8 GiB/vCPU highmem ratio.
N2_MACHINE_SHAPES = {
    "highcpu": [(size, size) for size in [2, 4, 8, 16, 32, 48, 64, 80, 96]],
    "standard": [(size, size * 4) for size in [2, 4, 8, 16, 32, 48, 64, 80, 96, 128]],
    "highmem": [(size, size * 8) for size in [2, 4, 8, 16, 32, 48, 64, 80, 96]] + [(128, 864)],
}


def convert_cpu_to_milli(cpu):
    """
    Convert CPU specification to milli-cores.
    Supports formats like: "1", "1.5", "500m", "0.5"
    """
    if cpu is None:
        return DEFAULT_CPU_MILLI

    cpu_str = str(cpu).strip()
    if not cpu_str:
        raise ValueError("CPU specification cannot be empty")

    # Handle milli-core format (e.g., "500m")
    if cpu_str.endswith("m"):
        try:
            cpu_milli = int(cpu_str[:-1])
        except ValueError as exc:
            raise ValueError(f"Invalid CPU specification: {cpu!r}") from exc
        if cpu_milli <= 0:
            raise ValueError("CPU specification must be greater than zero")
        return cpu_milli

    # Handle decimal format (e.g., "1.5", "0.5")
    try:
        cpu_float = float(cpu_str)
    except ValueError as exc:
        raise ValueError(f"Invalid CPU specification: {cpu!r}") from exc
    if not math.isfinite(cpu_float) or cpu_float <= 0:
        raise ValueError("CPU specification must be a finite number greater than zero")
    cpu_milli = int(cpu_float * 1000)
    if cpu_milli <= 0:
        raise ValueError("CPU specification must be at least one milli-core")
    return cpu_milli


def convert_memory_to_mib(memory, bare_unit="mib"):
    """
    Convert a memory specification to MiB.

    ``bare_unit`` controls the meaning of an unsuffixed number. Generic GCP
    resource strings use MiB, while TPV's ``mem`` destination parameter uses
    GiB.
    Supports formats like: "1Gi", "512Mi", "1024M", "1G", "2048"
    """
    if memory is None:
        return DEFAULT_MEMORY_MIB

    if bare_unit not in ("mib", "gib"):
        raise ValueError(f"Unsupported bare memory unit: {bare_unit!r}")

    memory_str = str(memory).strip()
    if not memory_str:
        raise ValueError("Memory specification cannot be empty")

    # Extract number and unit
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([A-Za-z]*)", memory_str)
    if not match:
        raise ValueError(f"Invalid memory specification: {memory!r}")

    value = float(match.group(1))
    unit = match.group(2).lower() or bare_unit
    try:
        factor = MEMORY_UNIT_TO_MIB[unit]
    except KeyError as exc:
        raise ValueError(f"Unknown memory unit in specification: {memory!r}") from exc
    if not math.isfinite(value):
        raise ValueError("Memory specification must be a finite number")
    memory_mib = int(value * factor)
    if memory_mib <= 0:
        raise ValueError("Memory specification must resolve to at least one MiB")
    return memory_mib


def compute_machine_type(cpu_milli, memory_mib, machine_type_family="n2"):
    """
    Compute an appropriate GCP machine type based on resource requirements.

    Chooses the smallest predefined N2 shape that satisfies both requirements,
    preferring the least memory-rich variant when multiple shapes have the
    same vCPU count.

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

    # Choose the smallest-vCPU shape that satisfies the request, then the
    # least memory-rich variant at that size. The ratio of the request alone
    # is insufficient: a larger standard shape can be smaller and cheaper
    # than the high-memory shape selected from that ratio.
    candidates = []
    for variant, shapes in N2_MACHINE_SHAPES.items():
        for vcpus, memory_gib_capacity in shapes:
            if vcpus >= cpu_vcpus and memory_gib_capacity >= memory_gib:
                candidates.append((vcpus, memory_gib_capacity, variant))

    if candidates:
        vcpus, memory_gib_capacity, variant = min(candidates)
        machine_type = f"n2-{variant}-{vcpus}"
        log.debug(
            "Computed machine type %s for resources: %d mCPU, %d MiB (capacity: %d vCPU, %.1f GiB)",
            machine_type,
            cpu_milli,
            memory_mib,
            vcpus,
            memory_gib_capacity,
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
