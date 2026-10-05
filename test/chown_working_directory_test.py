import getpass
import os
import subprocess

import pytest

from pulsar.scripts.chown_working_directory import main


def test_chown_to_current_user(tmp_path):
    main(["--user", getpass.getuser(), "--job_directory", str(tmp_path)])
    assert os.stat(tmp_path).st_uid == os.getuid()


def test_failed_chown_raises(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        main(["--user", getpass.getuser(), "--job_directory", str(tmp_path / "missing")])


def test_user_is_not_shell_interpreted(tmp_path):
    marker = tmp_path / "injected"
    with pytest.raises(subprocess.CalledProcessError):
        main(["--user", f"nobody'; touch '{marker}'; '", "--job_directory", str(tmp_path)])
    assert not marker.exists()
