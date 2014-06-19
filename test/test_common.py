""" For code shared between test_utils.py and check.py. Not sure this is the
best place - but check needs to not depend on test_utils so run_client_tests
can execute without webob dependency.
"""
import json
from os.path import join


def write_config(has_temp_directory, data, name="config.json"):
    try:
        temp_directory = has_temp_directory.temp_directory
    except AttributeError:
        temp_directory = has_temp_directory
    config_file = join(temp_directory, name)
    with open(config_file, "w") as f:
        if config_file.endswith(".json"):
            json.dump(data, f)
        else:
            import yaml
            yaml.dump(data, f)
    return config_file
