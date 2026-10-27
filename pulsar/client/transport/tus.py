"""Minimal tus 1.0.0 client for staging outputs back to Galaxy.

All requests of one upload - the creation POST, every PATCH and the final job
files POST - go through one ``requests.Session``, so they share a single
keep-alive connection. tuspy sends each chunk with a module-level
``requests.patch``, which opens a new TCP and TLS connection per chunk.
"""
import logging
import os
import re
import time
from typing import (
    BinaryIO,
    Optional,
)
from urllib.parse import (
    urljoin,
    urlparse,
)

import requests

from .transient import is_transient_http_error

log = logging.getLogger(__name__)

DEFAULT_PULSAR_TUS_CHUNK_SIZE = 10**7
PULSAR_TUS_CHUNK_SIZE = int(os.getenv('PULSAR_TUS_CHUNK_SIZE', DEFAULT_PULSAR_TUS_CHUNK_SIZE))
# Retries of a failed chunk, each resuming from the offset the server reports.
# The counter resets after every successful chunk.
PULSAR_TUS_RETRIES = int(os.getenv('PULSAR_TUS_RETRIES', 10))
PULSAR_TUS_RETRY_DELAY = float(os.getenv('PULSAR_TUS_RETRY_DELAY', 30))
# Seconds to wait to connect, and between bytes sent or received, before a tus
# request counts as failed and is retried. Without it a stalled connection
# would block stage-out forever.
PULSAR_TUS_TIMEOUT = float(os.getenv('PULSAR_TUS_TIMEOUT', 60))
TUS_HEADERS = {"Tus-Resumable": "1.0.0"}
# The server may still be finishing a PATCH whose response was lost.
TUS_CONFLICT_STATUSES = frozenset({409, 423})


class TusUploadError(requests.HTTPError):
    """A tus request failed or the server broke the protocol.

    A ``requests.HTTPError`` carrying the response, like the final job files
    POST raises, so stage-out classifies it by status code and never downgrades
    it to a warning.
    """


def tus_upload_file(url: str, path: str) -> None:
    tus_url = find_tus_endpoint(url)
    with requests.Session() as session:
        upload_session_url = _tus_upload(
            session, tus_url, path, PULSAR_TUS_CHUNK_SIZE, PULSAR_TUS_RETRIES, PULSAR_TUS_RETRY_DELAY, PULSAR_TUS_TIMEOUT
        )
        tus_session_id = upload_session_url.rsplit("/", 1)[1]
        # job_key and such are encoded in the URL but this route expects a POST body
        # and if it has one Galaxy sticks the URL parameters into the "payload" object
        # for the controller. So encoded session_id in the POST body - it probably
        # all belongs there anyway. No timeout: Galaxy may copy a large file
        # before it answers.
        post_response = session.post(url, data={"session_id": tus_session_id})
        post_response.raise_for_status()


def _tus_upload(
    session: requests.Session,
    tus_url: str,
    path: str,
    chunk_size: int,
    retries: int = 0,
    retry_delay: float = 0,
    timeout: Optional[float] = None,
) -> str:
    size = os.path.getsize(path)
    # Create the upload even for an empty file, which then needs no PATCH.
    response = session.post(tus_url, headers=dict(TUS_HEADERS, **{"Upload-Length": str(size)}), timeout=timeout)
    location = response.headers.get("Location")
    if not response.ok or location is None:
        raise TusUploadError(
            f"Failed to create tus upload at {tus_url}: status {response.status_code}, {response.text[:500]}", response=response
        )
    upload_url = urljoin(tus_url, location)

    offset = 0
    failures = 0
    resync = False
    with open(path, "rb") as f:
        while offset < size:
            try:
                if resync:
                    # Resume from what the server has, which may be more or less than we sent.
                    response = session.head(upload_url, headers=TUS_HEADERS, timeout=timeout)
                    offset = _upload_offset(response, upload_url, -1, size)
                    resync = False
                else:
                    offset = _upload_chunk(session, upload_url, f, offset, size, chunk_size, timeout)
                    failures = 0
            except requests.RequestException as e:
                if failures >= retries or not _is_retryable(e):
                    raise
                failures += 1
                log.warning(
                    "tus upload of %s to %s failed at offset %d (%s), retry %d of %d in %s s",
                    path, upload_url, offset, e, failures, retries, retry_delay,
                )
                time.sleep(retry_delay)
                resync = True
    return upload_url


def _is_retryable(e: requests.RequestException) -> bool:
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return e.response.status_code in TUS_CONFLICT_STATUSES or is_transient_http_error(e)
    return False


def _upload_chunk(
    session: requests.Session, upload_url: str, f: BinaryIO, offset: int, size: int, chunk_size: int, timeout: Optional[float]
) -> int:
    f.seek(offset)
    chunk = f.read(min(chunk_size, size - offset))
    if not chunk:
        raise OSError(f"{f.name} shrank to {offset} bytes during tus upload of {size} bytes")
    headers = dict(TUS_HEADERS, **{
        "Upload-Offset": str(offset),
        "Content-Type": "application/offset+octet-stream",
    })
    response = session.patch(upload_url, data=chunk, headers=headers, timeout=timeout)
    return _upload_offset(response, upload_url, offset, size)


def _upload_offset(response: requests.Response, upload_url: str, after: int, size: int) -> int:
    """Return the response's ``Upload-Offset``, which must be in ``(after, size]``."""
    if not response.ok:
        raise TusUploadError(
            f"{response.request.method} {upload_url} failed: status {response.status_code}, {response.text[:500]}",
            response=response,
        )
    new_offset = response.headers.get("Upload-Offset")
    if new_offset is None or not re.fullmatch("[0-9]+", new_offset) or not after < int(new_offset) <= size:
        raise TusUploadError(
            f"tus server at {upload_url} returned Upload-Offset {new_offset!r}, expected above {after} and at most {size}",
            response=response,
        )
    return int(new_offset)


def find_tus_endpoint(job_files_endpoint: str) -> str:
    parsed = urlparse(job_files_endpoint)
    job_files_url_path = parsed.path
    tus_endpoint = re.sub(r"jobs/[^/]*/files", "job_files/resumable_upload", job_files_url_path, count=1)

    new_url = parsed._replace(path=tus_endpoint)
    return new_url.geturl()
