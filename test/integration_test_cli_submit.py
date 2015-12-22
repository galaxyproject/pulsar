import os
import yaml

from .test_utils import (
    TempDirectoryTestCase,
    files_server,
    integration_test,
)

from pulsar.client.util import to_base64_json
from pulsar.scripts import submit


class CliTestCase(TempDirectoryTestCase):

    @integration_test
    def test(self):
        # TODO: test unstaging, would actually require files server and some
        # sort MQ listening.
        with files_server("/"):  # as test_files_server:
            config_directory = os.path.join(self.temp_directory, "config")
            staging_directory = os.path.join(self.temp_directory, "staging")
            os.makedirs(config_directory)
            app_conf = dict(
                staging_directory=staging_directory,
                message_queue_url="memory://submittest"
            )
            app_conf_path = os.path.join(config_directory, "app.yml")
            with open(app_conf_path, "w") as f:
                f.write(yaml.dump(app_conf))

            job_id = "43"

            output_path = os.path.join(staging_directory, job_id, "out")
            launch_params = dict(
                command_line="echo 'moo' > '%s'" % output_path,
                job_id=job_id,
                setup_params=dict(
                    job_id=job_id,
                )
            )
            base64 = to_base64_json(launch_params)
            submit.main(["--base64", base64, "--app_conf_path", app_conf_path])
            out_contents = open(output_path, "r").read()
            assert out_contents == "moo\n", out_contents
