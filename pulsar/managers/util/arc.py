import logging
from enum import Enum
from typing import Optional

from pulsar.managers import status as state

try:
    import pyarcrest
    import pyarcrest.arc
except ImportError:
    pyarcrest = None

__all__ = ("ARCState", "arc_state_to_pulsar_state", "ensure_pyarc", "pyarcrest")


log = logging.getLogger(__name__)

PYARCREST_UNAVAILABLE_MESSAGE = (
    "Pulsar ARC client requires the Python package `pyarcrest` - but it is unavailable. Please install `pyarcrest`."
)

def ensure_pyarc():
    if pyarcrest is None:
        raise ImportError(PYARCREST_UNAVAILABLE_MESSAGE)


class ARCState(str, Enum):
    """
    ARC job states that the REST interface may report.

    References:
    - [1] https://www.nordugrid.org/arc/arc7/tech/rest/rest.html#rest-interface-job-states
    """

    ACCEPTING = "ACCEPTING"
    ACCEPTED = "ACCEPTED"
    PREPARING = "PREPARING"
    PREPARED = "PREPARED"
    SUBMITTING = "SUBMITTING"
    QUEUING = "QUEUING"
    RUNNING = "RUNNING"
    HELD = "HELD"
    EXITINGLRMS = "EXITINGLRMS"
    OTHER = "OTHER"
    EXECUTED = "EXECUTED"
    FINISHING = "FINISHING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    KILLING = "KILLING"
    KILLED = "KILLED"
    WIPED = "WIPED"


ARC_STATE_TO_PULSAR_STATE_MAP = {
    # Mapping from ARC REST interface job states to Pulsar job states.
    ARCState.ACCEPTING: state.PREPROCESSING,      # Session created, files can be uploaded; not yet processed.
    ARCState.ACCEPTED: state.PREPROCESSING,       # Detected by A-REX, can't proceed yet.
    ARCState.PREPARING: state.PREPROCESSING,      # Data stage-in, input data gathering.
    ARCState.PREPARED: state.QUEUED,              # Waiting in queue for batch submission.
    ARCState.SUBMITTING: state.QUEUED,            # Preparing for submission.
    ARCState.QUEUING: state.QUEUED,               # In batch system queue.
    ARCState.RUNNING: state.RUNNING,              # Running.
    ARCState.HELD: state.RUNNING,                 # On hold/suspended; keep as queued.
    ARCState.EXITINGLRMS: state.RUNNING,          # Finishing execution in batch system.
    ARCState.OTHER: state.RUNNING,                # Unknown state; treat as lost.
    ARCState.EXECUTED: state.POSTPROCESSING,      # Completed, waiting for post-processing.
    ARCState.FINISHING: state.POSTPROCESSING,     # Data stage-out, cleaning up.
    ARCState.FINISHED: state.COMPLETE,            # Successful completion.
    ARCState.FAILED: state.FAILED,                # Failed.
    ARCState.KILLING: state.CANCELLED,            # Being cancelled.
    ARCState.KILLED: state.CANCELLED,             # Killed by user.
    ARCState.WIPED: state.LOST,                   # Data deleted, treat as lost.
}


def arc_state_to_pulsar_state(arc_state: Optional[ARCState]) -> str:
    """
    Map ARC REST interface job states to Pulsar job states.

    Assign the Pulsar state FAILED to jobs whose ARC state does not match any of the states from the mapping
    ``ARC_STATE_TO_PULSAR_STATE_MAP``.
    """
    pulsar_state = ARC_STATE_TO_PULSAR_STATE_MAP.get(arc_state)

    if pulsar_state is None:
        log.warning(f"Unknown ARC state encountered [{arc_state}]")
        return state.FAILED

    return pulsar_state
