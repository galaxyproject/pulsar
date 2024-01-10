import os
import re
from typing import Dict
from urllib.parse import urlparse

import requests

try:
    from tusclient import client
    tus_client_available = True
except ImportError:
    tus_client_available = False

TUS_CLIENT_UNAVAILABLE_MESSAGE = \
    "You are attempting to use the Tus transport with the Pulsar client but tuspy is unavailable."
DEFAULT_PULSAR_TUS_CHUNK_SIZE = 10**7
PULSAR_TUS_CHUNK_SIZE = int(os.getenv('PULSAR_TUS_CHUNK_SIZE', DEFAULT_PULSAR_TUS_CHUNK_SIZE))


def tus_upload_file(url: str, path: str) -> None:
    if not tus_client_available:
        raise Exception(TUS_CLIENT_UNAVAILABLE_MESSAGE)

    storage = None
    metadata: Dict[str, str] = {}

    headers: Dict[str, str] = {}
    tus_url = find_tus_endpoint(url)
    my_client = client.TusClient(tus_url, headers=headers)
    uploader = my_client.uploader(path, metadata=metadata, url_storage=storage)
    uploader.chunk_size = PULSAR_TUS_CHUNK_SIZE
    uploader.upload()
    upload_session_url = uploader.url
    assert upload_session_url
    tus_session_id = upload_session_url.rsplit("/", 1)[1]
    # job_key and such are encoded in the URL but this route expects a POST body
    # and if it has one Galaxy sticks the URL parameters into the "payload" object
    # for the controller. So encoded session_id in the POST body - it probably
    # all belongs there anyway.
    post_response = requests.post(url, data={"session_id": tus_session_id})
    post_response.raise_for_status()


def find_tus_endpoint(job_files_endpoint: str) -> str:
    parsed = urlparse(job_files_endpoint)
    job_files_url_path = parsed.path
    tus_endpoint = re.sub(r"jobs/[^/]*/files", "job_files/resumable_upload", job_files_url_path, 1)

    new_url = parsed._replace(path=tus_endpoint)
    return new_url.geturl()
