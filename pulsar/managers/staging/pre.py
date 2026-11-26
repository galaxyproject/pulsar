"""
"""

import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
)

from pulsar.client.action_mapper import from_dict
from pulsar.client.util import add_executable_bits
from .failure import (
    input_staging_failure,
    raising_staging_failure,
)
from .metrics import (
    PREPROCESS,
    record_transfer,
)

if TYPE_CHECKING:
    from galaxy.objectstore import ObjectStore

    from pulsar.managers.base import JobDirectory
    from pulsar.managers.util.retry import RetryActionExecutor

log = logging.getLogger(__name__)


def preprocess(
    job_directory: "JobDirectory",
    setup_actions: List[Dict[str, Any]],
    action_executor: "RetryActionExecutor",
    was_cancelled: Callable[[], Optional[bool]],
    object_store: Optional["ObjectStore"] = None,
):
    """Stage in the job's inputs.

    Raises ``StagingFailure``, and only that, if the inputs could not be staged.
    """
    with raising_staging_failure("inputs"), record_transfer(job_directory, PREPROCESS) as metrics:
        for setup_action in setup_actions:
            if was_cancelled():
                log.info("Exiting preprocessing, job is cancelled")
                return
            name = setup_action["name"]
            input_type = setup_action["type"]
            try:
                action = from_dict(setup_action["action"])
                if getattr(action, "inject_object_store", False):
                    action.object_store = object_store
                path = job_directory.calculate_path(name, input_type)
                description = f"Staging {input_type} '{name}' via {action} to {path}"
                log.debug(description)
                action_executor.execute(
                    lambda action=action, path=path: action.write_to_path(path), "action[%s]" % description
                )
                if setup_action.get("executable") and not action.shares_source_inode:
                    add_executable_bits(path)
            except Exception as e:
                raise input_staging_failure(name, e) from e
            metrics.record_file(path)


__all__ = ("preprocess",)
