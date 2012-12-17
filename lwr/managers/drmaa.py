
from lwr.managers.base import Manager


class DrmaaQueueManager(Manager):
    """
    Placeholder for DRMAA backed queue manager. Not yet implemented.
    """
    manager_type = "queued_drmaa"

    def __init__(self, name, app, **kwds):
        super(DrmaaQueueManager, self).__init__(name, app, **kwds)
        raise NotImplementedError()
