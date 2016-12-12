"""
"""
from pulsar.client.action_mapper import from_dict
import logging

log = logging.getLogger(__name__)


def preprocess(job_directory, setup_actions, action_executor):
    for setup_action in setup_actions:
        name = setup_action["name"]
        input_type = setup_action["type"]
        action = from_dict(setup_action["action"])
        path = job_directory.calculate_path(name, input_type)
        description = "Staging %s '%s' via %s to %s" % (input_type, name, action, path)
        log.debug(description)
        action_executor.execute(lambda: action.write_to_path(path), "action[%s]" % description)


__all__ = ('preprocess',)
