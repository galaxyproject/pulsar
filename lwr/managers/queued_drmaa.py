from lwr.managers.base import BaseManager
from lwr.drmaa import DrmaaSessionFactory


class DrmaaQueueManager(BaseManager):
    """
    Placeholder for DRMAA backed queue manager. Not yet implemented.
    """
    manager_type = "queued_drmaa"

    def __init__(self, name, app, **kwds):
        super(DrmaaQueueManager, self).__init__(name, app, **kwds)
        self.drmaa_session_factory = DrmaaSessionFactory()
