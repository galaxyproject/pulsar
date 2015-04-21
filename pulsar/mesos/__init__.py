""" This module and submodules contain code for interfacing the Apache Mesos framework.
"""
try:
    from mesos.interface import (
        Scheduler,
        Executor
    )
    from mesos.native import (
        MesosSchedulerDriver,
        MesosExecutorDriver
    )
except ImportError:
    Scheduler = object
    Executor = object
    MesosSchedulerDriver = None
    MesosExecutorDriver = None
try:
    from mesos.interface import mesos_pb2
except ImportError:
    mesos_pb2 = None

NO_MESOS_EXCEPTION = "Failed to import mesos module, please install mesos properly."
NO_MESOS_PROTO_EXCEPTION = "Failed to import mesos_pbs module, please install mesos properly."


def ensure_mesos_libs():
    """ Raise import error if mesos is not actually available. Original
    import errors above supressed because mesos is meant as an optional
    dependency for the Pulsar.
    """

    if MesosSchedulerDriver is None:
        raise Exception(NO_MESOS_EXCEPTION)

    if mesos_pb2 is None:
        raise Exception(NO_MESOS_PROTO_EXCEPTION)
