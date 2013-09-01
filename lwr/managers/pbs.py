
from lwr.managers.base import ManagerInterface


class PbsQueueManager(ManagerInterface):
    """
    Placeholder for DRMAA backed queue manager. Not yet implemented.
    """
    manager_type = "queued_pbs"

    def __init__(self, name, app, **kwds):
        super(PbsQueueManager, self).__init__(name, app, **kwds)
        raise NotImplementedError()
