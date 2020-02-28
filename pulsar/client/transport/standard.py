"""
Pulsar HTTP Client layer based on Python Standard Library (urllib2)
"""

from __future__ import with_statement

import requests


from ..exceptions import PulsarClientTransportError


class Urllib2Transport(object):

    def __init__(self, timeout=None, **kwargs):
        self.timeout = timeout

    def execute(self, url, method=None, data=None, input_path=None, output_path=None):
        exec_method = getattr(requests, method.lower() if method else 'get')
        kwargs = {'url': url, 'data': data}
        if input_path:
            kwargs['files'] = {'file': open(input_path, 'rb')}
        try:
            response = exec_method(**kwargs)
        except Exception as e:
            raise PulsarClientTransportError(transport_message=str(e))
        if output_path:
            with open(output_path, 'wb') as output:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # filter out keep-alive new chunks
                        output.write(chunk)
        else:
            return response.content
