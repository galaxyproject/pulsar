import logging
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
    "ensure_client",
    "gcp_client",
    "batch_v1",
    "get_gcp_job",
    "delete_gcp_job",
)
