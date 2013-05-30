from .client import Client
from .transport import get_transport


class ClientManager(object):
    """
    Factory to create LWR clients, used to manage potential shared
    state between multiple client connections.
    """
    def __init__(self, **kwds):
        self.transport = get_transport(kwds.get('transport_type', None))

    def get_client(self, destination_params, job_id):
        return Client(destination_params, job_id, transport=self.transport)
