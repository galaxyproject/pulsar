import io
import logging
import os.path

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

log = logging.getLogger(__name__)


class PycurlTransport:

    def __init__(self, timeout=None, **kwrgs):
        self.timeout = timeout

    def execute(self, url, method=None, data=None, input_path=None, output_path=None):
        buf = _open_output(output_path)
        try:
            c = _new_curl_object_for_url(url)
            c.setopt(c.WRITEFUNCTION, buf.write)
            if method:
                c.setopt(c.CUSTOMREQUEST, method)
            if input_path:
                c.setopt(c.UPLOAD, 1)
                c.setopt(c.READFUNCTION, open(input_path, 'rb').read)
                filesize = os.path.getsize(input_path)
                c.setopt(c.INFILESIZE, filesize)
            if data:
                c.setopt(c.POST, 1)
                if isinstance(data, str):
                    data = data.encode('UTF-8')
                c.setopt(c.POSTFIELDS, data)
            if self.timeout:
                c.setopt(c.TIMEOUT, self.timeout)
            try:
                c.perform()
            except error as exc:
                raise PulsarClientTransportError(
                    _error_curl_to_pulsar(exc.args[0]),
                    transport_code=exc.args[0],
                    transport_message=exc.args[1])
            if not output_path:
                return buf.getvalue()
        finally:
            buf.close()


def post_file(url, path):
    if not os.path.exists(path):
        # pycurl doesn't always produce a great exception for this,
        # wrap it in a better one.
        message = NO_SUCH_FILE_MESSAGE % (path, url)
        raise Exception(message)
    c = _new_curl_object_for_url(url)
    c.setopt(c.HTTPPOST, [("file", (c.FORM_FILE, path.encode('ascii')))])
    c.perform()
    status_code = c.getinfo(HTTP_CODE)
    if int(status_code) != 200:
        message = POST_FAILED_MESSAGE % (url, status_code)
        raise Exception(message)


def get_size(url) -> int:
    response = requests.head(url, headers={"accept-encoding": "identity"})
    if response.status_code >= 299:
        log.warning("Response to HEAD request for '%s' with status code %s, cannot resume download", url, response.status_code)
        return -1
    try:
        return int(response.headers["content-length"])
    except KeyError:
        log.error("'content-length' header not sent for '%s', cannot resume download", url)
        return -1


def get_file(url, path: str):
    success_codes = [200]
    size = 0
    if os.path.exists(path):
        size = os.path.getsize(path)
        remote_size = get_size(url)
        if size and remote_size == size:
            # Already got the whole file, fixes https://github.com/galaxyproject/pulsar/issues/340
            return
        if remote_size == -1:
            # Don't know how large remote file is, so we'll have to start over
            size = 0
            buf = _open_output(path)
        else:
            # We got some data left to download
            buf = _open_output(path, 'ab')
            success_codes = [200, 206]
    else:
        # definitely a new download
        buf = _open_output(path)
    try:
        c = _new_curl_object_for_url(url)
        c.setopt(c.WRITEFUNCTION, buf.write)
        if size > 0:
            log.info('transfer of %s will resume at %s bytes', url, size)
            c.setopt(c.RESUME_FROM, size)
        c.perform()
        status_code = int(c.getinfo(HTTP_CODE))
        if status_code not in success_codes:
            message = GET_FAILED_MESSAGE % (url, status_code)
            raise Exception(message)
    finally:
        buf.close()


def _open_output(output_path, mode='wb'):
    return open(output_path, mode) if output_path else io.BytesIO()


def _new_curl_object_for_url(url):
    c = _new_curl_object()
    c.setopt(c.URL, url.encode('ascii'))
    return c


def _new_curl_object():
    try:
        return Curl()
    except NameError:
        raise ImportError(PYCURL_UNAVAILABLE_MESSAGE)


def _error_curl_to_pulsar(code):
    if code == pycurl.E_OPERATION_TIMEDOUT:
        return PulsarClientTransportError.TIMEOUT
    elif code == pycurl.E_COULDNT_CONNECT:
        return PulsarClientTransportError.CONNECTION_REFUSED
    return None


__all__ = [
    'PycurlTransport',
    'post_file',
    'get_file'
]
