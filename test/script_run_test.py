import os
from .test_utils import (
    TempDirectoryTestCase,
    test_pulsar_server,
)
from pulsar.scripts import run


class ScriptRunTestCase(TempDirectoryTestCase):

    def setUp(self):
        super().setUp()
        input1 = os.path.join(self._working_directory, "input1")
        open(input1, "w").write("Hello World!")
        self.input1 = input1

    def simple_test(self):
        app_conf = {}
        with test_pulsar_server(app_conf=app_conf) as server:
            url = server.application_url
            self._run([
                "--url", url,
                "--default_file_action", "transfer",
            ])
            self._check_outputs()

    def _run(self, pulsar_args):
        run_args = pulsar_args[:]
        run_args.extend([
            "--command", "echo `pwd` > output1; cp input1 output_test2",
            "--working_directory", self._working_directory,
            "--output", "output1",
            "--output_pattern", r"output_test\d",
            "--result_json", self._result,
        ])
        exit_code = run.main(run_args)
        if os.path.exists(self._result):
            print(open(self._result).read())
        else:
            assert False, "No result json file found"
        assert exit_code == 0

    def _check_outputs(self):
        output1 = os.path.join(self._working_directory, "output1")
        output_test2 = os.path.join(self._working_directory, "output_test2")
        # Prove it went somewhere else :)
        assert open(output1).read() != self._working_directory
        assert open(output_test2).read() == "Hello World!"

    @property
    def _result(self):
        return os.path.join(self.temp_directory, "r.json")

    @property
    def _working_directory(self):
        work_dir = os.path.join(self.temp_directory, "work")
        if not os.path.exists(work_dir):
            os.makedirs(work_dir)
        return work_dir
