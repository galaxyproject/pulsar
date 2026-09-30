import io
import logging
import os.path
from contextlib import contextmanager

import requests

try:
    import pycurl
    from pycurl import (
        Curl,
        error,
        HTTP_CODE,
    )
    curl_available = True
except ImportError:
    curl_available = False

from ..exceptions import PulsarClientTransportError

PYCURL_UNAVAILABLE_MESSAGE = \
    "You are attempting to use the Pycurl version of the Pulsar client but pycurl is unavailable."

NO_SUCH_FILE_MESSAGE = "Attempt to post file %s to URL %s, but file does not exist."
POST_FAILED_MESSAGE = "Failed to post_file properly for url %s, remote server returned status code of %s."
GET_FAILED_MESSAGE = "Failed to get_file properly for url %s, remote server returned status code of %s."
# Bounded explicitly: libcurl before 8.3 follows redirect loops forever by default.
MAX_REDIRECTS = 5

log = logging.getLogger(__name__)


class PycurlTransport:

    def __init__(self, timeout=None, **kwrgs):
        self.timeout = timeout

    def execute(self, url, method=None, data=None, input_path=None, output_path=None):
        buf = _open_output(output_path)
        input_fh = None
        try:
            with _curl_object_for_url(url) as c:
                c.setopt(c.WRITEFUNCTION, buf.write)
                if method:
                    c.setopt(c.CUSTOMREQUEST, method)
                if input_path:
                    input_fh = open(input_path, "rb")
                    c.setopt(c.UPLOAD, 1)
                    c.setopt(c.READFUNCTION, input_fh.read)
                    filesize = os.path.getsize(input_path)
                    c.setopt(c.INFILESIZE, filesize)
                if data:
                    c.setopt(c.POST, 1)
                    if isinstance(data, str):
                        data = data.encode('UTF-8')
                    c.setopt(c.POSTFIELDS, data)
                if self.timeout:
                    c.setopt(c.TIMEOUT, self.timeout)
                _perform(c)
                if not output_path:
                    return buf.getvalue()
        finally:
            buf.close()
            if input_fh:
                input_fh.close()


def post_file(url, path):
    if not os.path.exists(path):
        # pycurl doesn't always produce a great exception for this,
        # wrap it in a better one.
        message = NO_SUCH_FILE_MESSAGE % (path, url)
        raise FileNotFoundError(message)
    with _curl_object_for_url(url) as c:
        c.setopt(c.HTTPPOST, [("file", (c.FORM_FILE, path.encode('ascii')))])
        _perform(c)
        status_code = int(c.getinfo(HTTP_CODE))
        if status_code != 200:
            raise PulsarClientTransportError(
                code=PulsarClientTransportError.NOT_200,
                transport_code=status_code,
                transport_message=POST_FAILED_MESSAGE % (url, status_code),
            )


def get_size(url) -> int:
    with requests.head(url, headers={"accept-encoding": "identity"}, allow_redirects=True) as response:
        if response.status_code >= 299:
            log.warning("Response to HEAD request for '%s' with status code %s, cannot resume download", url, response.status_code)
            return -1
        try:
            return int(response.headers["content-length"])
        except KeyError:
            log.error("'content-length' header not sent for '%s', cannot resume download", url)
            return -1


def get_file(url, path: str):
    resume_from = 0
    if os.path.exists(path):
        size = os.path.getsize(path)
        remote_size = get_size(url)
        if size and remote_size == size:
            # Already got the whole file, fixes https://github.com/galaxyproject/pulsar/issues/340
            return
        if size < remote_size:
            # We got some data left to download. With an unknown remote size, or a partial
            # file larger than the remote one (it changed), we start over.
            resume_from = size
    try:
        _download(url, path, resume_from)
    except PulsarClientTransportError as exc:
        if not (resume_from and _resume_refused(exc)):
            raise
        # The partial file can never be completed from here.
        log.info("server for %s cannot resume this transfer, downloading it again", url)
        _download(url, path, 0)


def _resume_refused(exc: PulsarClientTransportError) -> bool:
    if exc.code == PulsarClientTransportError.NOT_200:
        # The requested range is past the end of the (changed) remote file.
        return exc.transport_code == 416
    # The server ignores Range requests.
    return exc.transport_code == pycurl.E_RANGE_ERROR


def _download(url, path: str, resume_from: int):
    success_codes = [200, 206] if resume_from else [200]
    buf = _open_output(path, 'ab' if resume_from else 'wb')
    try:
        with _curl_object_for_url(url) as c:
            c.setopt(c.WRITEFUNCTION, buf.write)
            # Galaxy may redirect staging requests (e.g. to a presigned object store URL).
            c.setopt(c.FOLLOWLOCATION, 1)
            c.setopt(c.MAXREDIRS, MAX_REDIRECTS)
            if resume_from:
                log.info('transfer of %s will resume at %s bytes', url, resume_from)
                c.setopt(c.RESUME_FROM, resume_from)
            _perform(c)
            status_code = int(c.getinfo(HTTP_CODE))
            if status_code not in success_codes:
                raise PulsarClientTransportError(
                    code=PulsarClientTransportError.NOT_200,
                    transport_code=status_code,
                    transport_message=GET_FAILED_MESSAGE % (url, status_code),
                )
    finally:
        buf.close()


def _open_output(output_path, mode='wb'):
    return open(output_path, mode) if output_path else io.BytesIO()


@contextmanager
def _curl_object_for_url(url):
    c = _new_curl_object()
    try:
        c.setopt(c.URL, url.encode('ascii'))
        yield c
    finally:
        c.close()


def _new_curl_object():
    try:
        return Curl()
    except NameError:
        raise ImportError(PYCURL_UNAVAILABLE_MESSAGE)


def _perform(c):
    """Run a prepared transfer, converting pycurl's error into a structured one.

    Transport failures have to reach callers as PulsarClientTransportError —
    that is the type staging policy and retry classification key on, and a bare
    pycurl.error is invisible to both.
    """
    try:
        c.perform()
    except error as exc:
        raise PulsarClientTransportError(
            _error_curl_to_pulsar(exc.args[0]),
            transport_code=exc.args[0],
            transport_message=exc.args[1])


def _error_curl_to_pulsar(code):
    if code == pycurl.E_OPERATION_TIMEDOUT:
        return PulsarClientTransportError.TIMEOUT
    elif code == pycurl.E_COULDNT_CONNECT:
        return PulsarClientTransportError.CONNECTION_REFUSED
    return None


__all__ = [
    'PycurlTransport',
    'get_file',
    'post_file'
]
