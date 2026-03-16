"""
"""

import logging
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from pulsar.client.action_mapper import from_dict

if TYPE_CHECKING:
    from galaxy.objectstore import ObjectStore
    from pulsar.managers.base import JobDirectory
    from pulsar.managers.util.retry import RetryActionExecutor

log = logging.getLogger(__name__)


def preprocess(
    job_directory: "JobDirectory",
    setup_actions: List[Dict[str, str]],
    action_executor: "RetryActionExecutor",
    was_cancelled: Callable[[], Optional[bool]],
    object_store: Optional["ObjectStore"] = None,
):
    for setup_action in setup_actions:
        if was_cancelled():
            log.info("Exiting preprocessing, job is cancelled")
            return
        name = setup_action["name"]
        input_type = setup_action["type"]
        action = from_dict(setup_action["action"])
        if getattr(action, "inject_object_store", False):
            action.object_store = object_store
        path = job_directory.calculate_path(name, input_type)
        description = "Staging {} '{}' via {} to {}".format(
            input_type, name, action, path
        )
        log.debug(description)
        action_executor.execute(
            lambda: action.write_to_path(path), "action[%s]" % description
        )


__all__ = ("preprocess",)
