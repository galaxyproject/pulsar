"""Input paths used when staging jobs."""

from os.path import exists

from galaxy.util.bunch import Bunch

CLIENT_INPUT_PATH_TYPES = Bunch(
    INPUT_PATH="input_path",
    INPUT_EXTRA_FILES_PATH="input_extra_files_path",
    INPUT_METADATA_PATH="input_metadata_path",
)


class ClientInput:

    def __init__(self, path, input_type, object_store_ref=None):
        self.path = path
        self.input_type = input_type
        self.object_store_ref = object_store_ref

    @property
    def action_source(self):
        return {"path": self.path, "object_store_ref": self.object_store_ref}


class ClientInputs:
    """Abstraction describing input datasets for a job."""

    def __init__(self, client_inputs):
        self.client_inputs = client_inputs

    def __iter__(self):
        return iter(self.client_inputs)

    @staticmethod
    def for_simple_input_paths(input_files):
        # Legacy: just assume extra files path based on inputs, probably not
        # the best behavior - ignores object store for instance.
        client_inputs = []
        for input_file in input_files:
            client_inputs.append(ClientInput(input_file, CLIENT_INPUT_PATH_TYPES.INPUT_PATH))
            files_path = "%s_files" % input_file[0:-len(".dat")]
            if exists(files_path):
                client_inputs.append(ClientInput(files_path, CLIENT_INPUT_PATH_TYPES.INPUT_EXTRA_FILES_PATH))

        return ClientInputs(client_inputs)
