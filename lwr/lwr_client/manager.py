from .client import Client, InputCachingClient
from .transport import get_transport


class ClientManager(object):
    """
    Factory to create LWR clients, used to manage potential shared
    state between multiple client connections.
    """
    def __init__(self, **kwds):
        self.transport = get_transport(kwds.get('transport_type', None))
        self.client_class = InputCachingClient if kwds.get('cache', False) else Client

    def get_client(self, destination_params, job_id):
        return self.client_class(destination_params, job_id, transport=self.transport)
