"""
"""
import logging

from pulsar.client.action_mapper import from_dict

log = logging.getLogger(__name__)


def preprocess(job_directory, setup_actions, action_executor, was_cancelled, object_store=None):
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
        description = "Staging {} '{}' via {} to {}".format(input_type, name, action, path)
        log.debug(description)
        action_executor.execute(lambda: action.write_to_path(path), "action[%s]" % description)


__all__ = ('preprocess',)
