import os
import subprocess

import pytest

from pulsar.managers.base.directory import PREPARE_DIRS_TEMPLATE


def _job_dir(tmp_path):
    dirs = {}
    for name in ("working", "outputs", "configs"):
        path = tmp_path / name
        path.mkdir()
        (path / "file.txt").write_text(f"{name} contents\n")
        dirs[name] = path
    (dirs["configs"] / "registry.xml").write_text("<registry/>")
    return dirs


def _run_prepare_dirs(dirs, preamble=""):
    script = preamble + PREPARE_DIRS_TEMPLATE.format(
        working_directory=dirs["working"],
        outputs_directory=dirs["outputs"],
        configs_directory=dirs["configs"],
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def _tree(directory):
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def test_prepare_dirs_restores_backup_only_created_after_successful_copy(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can read files without read permission")
    dirs = _job_dir(tmp_path)
    configs = dirs["configs"]
    unreadable = configs / "unreadable"
    unreadable.write_text("secret")
    unreadable.chmod(0)

    _run_prepare_dirs(dirs)
    assert not (tmp_path / "configs.orig").exists()

    unreadable.chmod(0o600)
    _run_prepare_dirs(dirs)
    assert _tree(tmp_path / "configs.orig") == _tree(configs)

    expected = _tree(configs)
    (configs / "registry.xml").write_text("")
    _run_prepare_dirs(dirs)
    assert _tree(configs) == expected


def test_prepare_dirs_skips_backup_when_stale_partial_cannot_be_removed(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can remove files from read-only directories")
    dirs = _job_dir(tmp_path)
    expected = _tree(dirs["configs"])
    stale = tmp_path / "configs.orig.partial" / "sub"
    stale.mkdir(parents=True)
    (stale / "f").write_text("stale")
    stale.chmod(0o555)

    _run_prepare_dirs(dirs)
    for path in tmp_path.rglob("sub"):
        path.chmod(0o755)

    assert not (tmp_path / "configs.orig").exists()
    assert _tree(dirs["configs"]) == expected


def test_prepare_dirs_rerun_after_killed_backup(tmp_path):
    # Simulates the job being killed while cp -R is filling the backup of configs.
    dirs = _job_dir(tmp_path)
    partial_copy_then_kill = f"""cp() {{
    if [ "$2" = "{dirs['configs']}" ]; then
        mkdir "$3"; : > "$3/registry.xml"; kill -KILL $$
    fi
    command cp "$@"
}}
"""
    interrupted = _run_prepare_dirs(dirs, preamble=partial_copy_then_kill)
    assert interrupted.returncode == -9

    result = _run_prepare_dirs(dirs)

    assert result.returncode == 0, result.stderr
    assert (dirs["configs"] / "registry.xml").read_text() == "<registry/>"
    for name, path in dirs.items():
        assert _tree(tmp_path / f"{name}.orig") == _tree(path)
