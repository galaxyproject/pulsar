import os
import yaml

from .test_utils import (
    TempDirectoryTestCase,
    files_server,
    integration_test,
    skip_unless_module,
    temp_directory_persist,
)

from pulsar.client import ClientOutputs
from pulsar.client.util import to_base64_json
from pulsar.scripts import submit


class BaseCliTestCase(TempDirectoryTestCase):

    def run_and_check_submission(self):
        job_id = "0"
        galaxy_working = temp_directory_persist()
        output_name = "dataset_1211231231231231231.dat"
        galaxy_output = os.path.join(galaxy_working, output_name)
        pulsar_output = os.path.join(self.staging_directory, job_id, "outputs", output_name)
        pulsar_input = os.path.join(self.staging_directory, job_id, "inputs", "cow")
        with files_server("/") as test_files_server:
            files_endpoint = test_files_server.application_url
            action = {"name": "cow", "type": "input", "action": {"action_type": "message", "contents": "cow file contents\n"}}
            client_outputs = ClientOutputs(
                working_directory=galaxy_working,
                output_files=[os.path.join(galaxy_working, output_name)],
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
            base64 = to_base64_json(launch_params)
            assert not os.path.exists(galaxy_output)
            submit.main(["--base64", base64] + self._encode_application())
            assert os.path.exists(galaxy_output)
            out_contents = open(galaxy_output).read()
            assert out_contents == "cow file contents\n", out_contents

    @property
    def staging_directory(self):
        return os.path.join(self.temp_directory, "staging")

    @property
    def config_directory(self):
        config_directory = os.path.join(self.temp_directory, "config")
        os.makedirs(config_directory)
        return config_directory


class CliFileAppConfigTestCase(BaseCliTestCase):

    @skip_unless_module("kombu")
    @integration_test
    def test(self):
        self.run_and_check_submission()

    def _encode_application(self):
        app_conf = dict(
            staging_directory=self.staging_directory,
            message_queue_url="memory://submittest"
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

    def _encode_application(self):
        app_conf = dict(
            staging_directory=self.staging_directory,
            message_queue_url="memory://submittest"
        )
        return ["--app_conf_base64", to_base64_json(app_conf)]
