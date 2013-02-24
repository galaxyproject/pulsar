from tempfile import mkdtemp
from contextlib import contextmanager
from shutil import rmtree
from lwr.util import JobDirectory
from os.path import join

from lwr.routes import _output_path


class TestManager(object):

    def setup_temp_directory(self):
        self.temp_directory = mkdtemp()
        self.job_directory = JobDirectory(self.temp_directory, '1')

    def cleanup_temp_directory(self):
        rmtree(self.temp_directory)

    def outputs_directory(self, job_id):
        return self.job_directory.outputs_directory()


@contextmanager
def _test_manager():
    manager = TestManager()
    manager.setup_temp_directory()
    yield manager
    manager.cleanup_temp_directory()


def test_output_path():
    with _test_manager() as manager:
        path = _output_path(manager, '1', 'moo', 'direct')
        assert path == join(manager.job_directory.outputs_directory(), 'moo')


def test_output_path_security():
    """
    Attempt to download a file outside of a valid result directory,
    ensure it fails.
    """
    with _test_manager() as manager:
        raised_exception = False
        try:
            _output_path(manager, '1', '../moo', 'direct')
        except:
            raised_exception = True
        assert raised_exception
