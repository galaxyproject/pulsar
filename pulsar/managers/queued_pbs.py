
from pulsar.managers.base import BaseManager

# try:
#     import pbs
# except ImportError:
#     pass


class PbsQueueManager(BaseManager):
    """
    Placeholder for PBS-python backed queue manager. Not yet implemented, for
    many situations this would be used the DRMAA or CLI+Torque managers may be
    better choices or at least stop gaps.
    """
    manager_type = "queued_pbs"

    def __init__(self, name, app, **kwds):
        super(PbsQueueManager, self).__init__(name, app, **kwds)
        raise NotImplementedError()
