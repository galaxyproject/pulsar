from typing import TYPE_CHECKING

from pulsar.managers.base import BaseManager

if TYPE_CHECKING:
    from pulsar.core import PulsarApp
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

    def __init__(self, name: str, app: "PulsarApp", **kwds):
        super().__init__(name, app, **kwds)
        raise NotImplementedError()
