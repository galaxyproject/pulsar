import os

from .curl import curl_available
from .curl import PycurlTransport
from .requests import requests_multipart_post_available
from .ssh import rsync_get_file, scp_get_file
from .ssh import rsync_post_file, scp_post_file
from .standard import Urllib2Transport

if curl_available:
    from .curl import get_file
    from .curl import post_file
elif requests_multipart_post_available:
    from .requests import get_file
    from .requests import post_file
else:
    from .poster import get_file
    from .poster import post_file


def get_transport(transport_type=None, os_module=os, transport_params=None):
    transport_type = _get_transport_type(transport_type, os_module)
    if not transport_params:
        transport_params = {}
    if transport_type == 'urllib':
        transport = Urllib2Transport(**transport_params)
    else:
        transport = PycurlTransport(**transport_params)
    return transport


def _get_transport_type(transport_type, os_module):
    if not transport_type:
        use_curl = os_module.getenv('PULSAR_CURL_TRANSPORT', "0")
        # If PULSAR_CURL_TRANSPORT is unset or set to 0, use default,
        # else use curl.
        if use_curl.isdigit() and not int(use_curl):
            transport_type = 'urllib'
        else:
            transport_type = 'curl'
    return transport_type


__all__ = (
    'get_transport',
    'get_file',
    'post_file',
    'rsync_get_file',
    'rsync_post_file',
    'scp_get_file',
    'scp_post_file',
)
