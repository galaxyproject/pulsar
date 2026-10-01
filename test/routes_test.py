import os
from os.path import join

import pytest

from pulsar.client.exceptions import UnsafePathError
from pulsar.web.routes import _output_path
from .test_utils import get_test_manager


def test_output_path():
    with get_test_manager() as manager:
        path = _output_path(manager, '1', 'moo', 'direct')
        assert path == join(manager.job_directory('1').outputs_directory(), 'moo')


def test_output_path_security():
    """
    Attempt to download a file outside of a valid result directory,
    ensure it fails.
    """
    with get_test_manager() as manager:
        raised_exception = False
        try:
            _output_path(manager, '1', '../moo', 'direct')
        except Exception:
            raised_exception = True
        assert raised_exception


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires os.mkfifo")
def test_output_path_refuses_fifo():
    """Serving a FIFO a tool left as an output would block the request indefinitely."""
    with get_test_manager() as manager:
        working_directory = manager.job_directory('1').working_directory()
        os.makedirs(working_directory)
        os.mkfifo(join(working_directory, 'out.fifo'))
        with pytest.raises(UnsafePathError):
            _output_path(manager, '1', 'out.fifo', 'output_workdir')
