"""
Pulsar HTTP Client layer based on Python Standard Library (urllib2)
"""

from __future__ import with_statement

import mmap
import socket

from os.path import getsize
try:
    from urllib2 import urlopen, URLError
except ImportError:
    from urllib.request import urlopen
    from urllib.error import URLError
try:
    from urllib2 import Request
except ImportError:
    from urllib.request import Request

from ..exceptions import PulsarClientTransportError


class Urllib2Transport(object):

    def __init__(self, timeout=None, **kwrgs):
        self.timeout = timeout

    def _url_open(self, request, data):
        return urlopen(request, data, self.timeout)

    def execute(self, url, method=None, data=None, input_path=None, output_path=None):
        request = self.__request(url, data, method)
        input = None
        try:
            if input_path:
                size = getsize(input_path)
                if size:
                    input = open(input_path, 'rb')
                    data = mmap.mmap(input.fileno(), 0, access=mmap.ACCESS_READ)
                else:
                    data = b""
                request.add_header('Content-Length', str(size))
            try:
                response = self._url_open(request, data)
            except socket.timeout:
                raise PulsarClientTransportError(code=PulsarClientTransportError.TIMEOUT)
            except URLError as exc:
                raise PulsarClientTransportError(transport_message=exc.reason)
        finally:
            if input:
                input.close()
        if output_path:
            with open(output_path, 'wb') as output:
                while True:
                    buffer = response.read(1024)
                    if not buffer:
                        break
                    output.write(buffer)
            return response
        else:
            return response.read()

    def __request(self, url, data, method):
        request = Request(url=url, data=data)
        if method:
            request.get_method = lambda: method
        return request
