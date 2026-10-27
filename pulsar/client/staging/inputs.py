"""Input paths used when staging jobs."""

from os.path import exists

from galaxy.util.bunch import Bunch

CLIENT_INPUT_PATH_TYPES = Bunch(
    INPUT_PATH="input_path",
    INPUT_EXTRA_FILES_PATH="input_extra_files_path",
    INPUT_METADATA_PATH="input_metadata_path",
)


class ClientInput:
    """An input of a job, named by its path on Galaxy.

    ``path`` is always set: the job's command line and config files refer to the
    input by it, it is rewritten to where Pulsar stages the input, and it names
    the staged copy. Unless told otherwise, the input is read from ``path``.

    Galaxy may instead say where to fetch the input, so that ``path`` need not
    exist on Galaxy's disk: ``url`` for a file, or for an extra files directory
    ``extra_files``, mapping each file's path relative to the directory to its
    URL. Only remote transfers fetch from these URLs; any other action still
    reads ``path``.
    """

    def __init__(self, path, input_type, object_store_ref=None, url=None, extra_files=None):
        self.path = path
        self.input_type = input_type
        self.object_store_ref = object_store_ref
        self.url = url
        self.extra_files = extra_files

    @property
    def action_source(self):
        return {
            "path": self.path,
            "object_store_ref": self.object_store_ref,
            "url": self.url,
            "extra_files": self.extra_files,
        }


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
