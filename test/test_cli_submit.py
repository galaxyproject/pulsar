import os
from abc import (
    ABC,
    abstractmethod,
)

import yaml

from .test_utils import (
    TempDirectoryTestCase,
    files_server,
    integration_test,
    skip_unless_module,
)

from pulsar.client import ClientOutputs, ClientInput
from pulsar.client.util import to_base64_json
from pulsar.scripts import submit


class BaseCliTestCase(ABC, TempDirectoryTestCase):

    def run_and_check_submission(self):
        # prepare job input directory
        input_directory = os.path.join(self.temp_directory, "input_files")
        os.makedirs(input_directory, exist_ok=False)
        self.setup_input_directory(input_directory)

        # prepare job output directory
        output_directory = os.path.join(self.temp_directory, "output_files")
        output_file_name = "dataset_1211231231231231231.dat"
        output_file_path = os.path.join(output_directory, output_file_name)
        os.makedirs(output_directory, exist_ok=False)

        # prepare Galaxy working directory
        galaxy_working_directory = os.path.join(self.temp_directory, "galaxy_working")
        os.makedirs(galaxy_working_directory, exist_ok=False)

        job_id = "0"
        with files_server("/", allow_multiple_downloads=True) as test_files_server:
            launch_params = self.setup_launch_params(
                job_id=job_id,
                files_endpoint=test_files_server.application_url,
                galaxy_working_directory=galaxy_working_directory,
                pulsar_staging_directory=self.staging_directory,
                input_directory=input_directory,
                output_file_path=output_file_path,
            )
            launch_params_base64 = to_base64_json(launch_params)

            # submit job and test results
            assert not os.path.exists(output_file_path)
            submit.main(["--base64", launch_params_base64] + self.encode_application())
            assert os.path.exists(output_file_path)
            out_contents = open(output_file_path).read()
            assert out_contents == "cow file contents\n", out_contents

    def setup_input_directory(self, directory):
        pass

    def setup_launch_params(
            self,
            *,
            job_id,
            files_endpoint,
            galaxy_working_directory,
            pulsar_staging_directory,
            output_file_path,
            **kwargs
    ):
        output_file_name = os.path.basename(output_file_path)
        pulsar_output = os.path.join(pulsar_staging_directory, job_id, "outputs", output_file_name)
        pulsar_input = os.path.join(pulsar_staging_directory, job_id, "inputs", "cow")
        action = {
            "name": "cow",
            "type": "input",
            "action": {
                "action_type": "message",
                "contents": "cow file contents\n"
            }
        }
        client_outputs = ClientOutputs(
            working_directory=galaxy_working_directory,
            output_files=[output_file_path],
        )
        launch_params = dict(
            command_line="cat '{}' > '{}'".format(pulsar_input, pulsar_output),
            job_id=job_id,
            setup_params=dict(
                job_id=job_id,
            ),
            setup=True,
            remote_staging={
                "setup": [action],
                "action_mapper": {
                    "default_action": "remote_transfer",
                    "files_endpoint": files_endpoint,
                },
                "client_outputs": client_outputs.to_dict(),
            },
        )
        return launch_params

    @abstractmethod
    def encode_application(self):
        pass

    @property
    def staging_directory(self):
        return os.path.join(self.temp_directory, "pulsar_staging")

    @property
    def config_directory(self):
        config_directory = os.path.join(self.temp_directory, "config")
        os.makedirs(config_directory, exist_ok=True)
        return config_directory


class CliFileAppConfigTestCase(BaseCliTestCase):

    @skip_unless_module("kombu")
    @integration_test
    def test(self):
        self.run_and_check_submission()

    def encode_application(self):
        app_conf = dict(
            staging_directory=self.staging_directory,
            message_queue_url="memory://submittest",
            conda_auto_init=False,
        )
        app_conf_path = os.path.join(self.config_directory, "app.yml")
        with open(app_conf_path, "w") as f:
            f.write(yaml.dump(app_conf))

        return ["--app_conf_path", app_conf_path]


class CliCommandLineAppConfigTestCase(BaseCliTestCase):

    @skip_unless_module("kombu")
    @integration_test
    def test(self):
        self.run_and_check_submission()

    def encode_application(self):
        app_conf = dict(
            staging_directory=self.staging_directory,
            message_queue_url="memory://submittest",
            conda_auto_init=False,
        )
        return ["--app_conf_base64", to_base64_json(app_conf)]
