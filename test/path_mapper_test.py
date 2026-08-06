import os.path

from pulsar.client import PathMapper
from pulsar.client.action_mapper import path_type
from .test_utils import TempDirectoryTestCase

from galaxy.util.bunch import Bunch


class PathMapperTestCase(TempDirectoryTestCase):

    def test_input(self):
        local_path = os.path.join(os.path.dirname(self.temp_directory), "dataset1.dat")
        path_mapper = self._path_mapper(local_path, path_type.INPUT)
        new_path = path_mapper.remote_input_path_rewrite(local_path)
        assert new_path == "/scratch/staging/1/inputs/dataset1.dat"

    def test_output(self):
        local_path = os.path.join(os.path.dirname(self.temp_directory), "dataset1.dat")
        path_mapper = self._path_mapper(local_path, path_type.OUTPUT)
        new_path = path_mapper.remote_output_path_rewrite(local_path)
        assert new_path == "/scratch/staging/1/outputs/dataset1.dat"

    def test_output_workdir(self):
        local_path = os.path.join(self.temp_directory, "dataset1.dat")
        path_mapper = self._path_mapper(local_path, path_type.OUTPUT_WORKDIR)
        new_path = path_mapper.remote_output_path_rewrite(local_path)
        assert new_path == "/scratch/staging/1/working/dataset1.dat"

    def test_input_with_no_staging(self):
        local_path = os.path.join(os.path.dirname(self.temp_directory), "dataset1.dat")
        path_mapper = self._path_mapper(local_path, path_type.INPUT, staging_needed=False)
        new_path = path_mapper.remote_input_path_rewrite(local_path)
        assert new_path is None

    def test_output_with_no_staging(self):
        local_path = os.path.join(os.path.dirname(self.temp_directory), "dataset1.dat")
        path_mapper = self._path_mapper(local_path, path_type.OUTPUT, staging_needed=False)
        new_path = path_mapper.remote_output_path_rewrite(local_path)
        assert new_path is None

    def test_version_path(self):
        local_path = os.path.join(os.path.dirname(self.temp_directory), "GALAXY_VERSION_234")
        path_mapper = self._path_mapper(local_path, path_type.OUTPUT)
        new_path = path_mapper.remote_version_path_rewrite(local_path)
        assert new_path == "/scratch/staging/1/outputs/COMMAND_VERSION"

    def test_container_rewrite_applies_rewrite_action(self):
        action = Bunch(staging_needed=False, action_type="rewrite", path_rewrite=lambda helper: "/dist/cvmfs/img")
        path_mapper = self._container_path_mapper(action)
        assert path_mapper.check_for_container_rewrite("/cvmfs/img") == "/dist/cvmfs/img"

    def test_container_rewrite_warns_and_skips_staging_action(self):
        # A staging action matched for a container image (e.g. a broad "*any*"
        # rule) is a misconfiguration: warn and leave the path untouched.
        action = Bunch(staging_needed=True, action_type="remote_transfer")
        path_mapper = self._container_path_mapper(action)
        with self.assertLogs("pulsar.client.path_mapper", level="WARNING") as captured:
            assert path_mapper.check_for_container_rewrite("/cvmfs/img") is None
        assert any("container image path" in message for message in captured.output)

    def _container_path_mapper(self, action):
        path_mapper = PathMapper(
            client=None,
            remote_job_config=self.__test_remote_config(),
            local_working_directory=self.temp_directory,
            action_mapper=_ContainerActionMapper(action),
        )
        return path_mapper

    def _path_mapper(self, expected_path, expected_type, staging_needed=True):
        action_mapper = TestActionMapper(expected_path, expected_type, staging_needed)
        path_mapper = PathMapper(
            client=None,
            remote_job_config=self.__test_remote_config(),
            local_working_directory=self.temp_directory,
            action_mapper=action_mapper,
        )
        return path_mapper

    def __test_remote_config(self):
        return dict(
            inputs_directory="/scratch/staging/1/inputs",
            outputs_directory="/scratch/staging/1/outputs",
            configs_directory="/scratch/staging/1/configs",
            working_directory="/scratch/staging/1/working",
            unstructured_files_directory="/scratch/staging/1/unstructured",
            system_properties=dict(separator="/"),
        )


class TestActionMapper:

    def __init__(self, expected_path, expected_type, staging_needed):
        self.expected_path = expected_path
        self.expected_type = expected_type
        self._action = Bunch(staging_needed=staging_needed)
        if not staging_needed:
            self._action.path_rewrite = lambda path: None

    def action(self, source, type):
        assert self.expected_path == source["path"]
        assert self.expected_type == type
        return self._action


class _ContainerActionMapper:
    """Returns a fixed action for CONTAINER lookups (container-rewrite tests)."""

    def __init__(self, action):
        self._action = action

    def action(self, source, type):
        assert type == path_type.CONTAINER
        return self._action
