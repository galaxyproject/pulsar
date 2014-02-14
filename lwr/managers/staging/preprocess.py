from lwr.lwr_client.action_mapper import from_dict


def preprocess(job_directory, setup_actions):
    for setup_action in setup_actions:
        name = setup_action["name"]
        input_type = setup_action["type"]
        action = from_dict(setup_action["action"])
        path = job_directory.calculate_path(name, input_type)
        action.write_to_path(path)

__all__ = [preprocess]
