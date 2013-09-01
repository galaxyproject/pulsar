
from lwr.managers.base import BaseManager

try:
    import pbs
except ImportError:
    pass


class PbsQueueManager(BaseManager):
    """
    Placeholder for DRMAA backed queue manager. Not yet implemented.
    """
    manager_type = "queued_pbs"

    def __init__(self, name, app, **kwds):
        super(PbsQueueManager, self).__init__(name, app, **kwds)
        raise NotImplementedError()
