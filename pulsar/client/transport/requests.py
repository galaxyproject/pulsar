import logging
import os
from typing import (
    BinaryIO,
    Dict,
)

import requests

try:
    import requests_toolbelt
except ImportError:
    requests_toolbelt = None  # type: ignore


log = logging.getLogger(__name__)


def post_file(url, path):
    with open(path, "rb") as f:
        if requests_toolbelt is not None:
            # Streaming multipart upload — avoids loading the whole file into memory.
            m = requests_toolbelt.MultipartEncoder(fields={"file": ("filename", f)})
            response = requests.post(url, data=m, headers={"Content-Type": m.content_type})
        else:
            log.warning(
                "Posting %s without requests_toolbelt: the entire file will be loaded into memory. "
                "Install requests_toolbelt (or pycurl, and use the curl transport) for streaming uploads.",
                path,
            )
            response = requests.post(url, files={'file': f})
        with response:
            response.raise_for_status()


def post_bytes(url, name, data, session=None, timeout=None):
    """POST an in-memory byte string as a multipart file upload.

    Companion to :func:`post_file` for callers that hold bytes rather than a
    path — e.g. streaming the growing tail of a job's stdout while it runs.
    Pass a ``requests.Session`` to reuse connections across calls.
    """
    poster = session if session is not None else requests
    with poster.post(url, files={"file": (name, data)}, timeout=timeout) as response:
        response.raise_for_status()


def get_file(url, path):
    with requests.get(url, stream=True) as response:
        response.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    f.flush()


def put_file(url, path, offset=0, size=None, headers=None) -> Dict[str, str]:
    """PUT ``size`` bytes of ``path`` from ``offset`` (by default the rest of the file) to ``url``.

    Streams the bytes with an exact Content-Length, as presigned object store uploads
    require, and returns the response headers (lower-cased names), e.g. a part's ETag.
    """
    if size is None:
        size = os.path.getsize(path) - offset
    with open(path, "rb") as source:
        source.seek(offset)
        body = _FileRange(source, size)
        with requests.put(url, data=body, headers=headers or {}) as response:
            response.raise_for_status()
            return {name.lower(): value for name, value in response.headers.items()}


class _FileRange:
    """At most ``size`` bytes of an open file, read in chunks; its length sets Content-Length."""

    def __init__(self, source: BinaryIO, size: int):
        self._source = source
        self._remaining = size
        self._size = size

    def __len__(self) -> int:
        return self._size

    def read(self, length: int = -1) -> bytes:
        if length < 0 or length > self._remaining:
            length = self._remaining
        data = self._source.read(length)
        self._remaining -= len(data)
        return data
