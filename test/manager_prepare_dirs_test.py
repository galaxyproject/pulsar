import filecmp
import subprocess

from pulsar.managers.base.directory import PREPARE_DIRS_TEMPLATE


def _job_dir(tmp_path):
    dirs = {}
    for name in ("working", "outputs", "configs"):
        path = tmp_path / name
        path.mkdir()
        (path / "file.txt").write_text(f"{name} contents\n")
        dirs[name] = path
    (dirs["configs"] / "registry.xml").write_text("<registry/>\n")
    return dirs


def _prepare_dirs(dirs, preamble=""):
    script = preamble + PREPARE_DIRS_TEMPLATE.format(
        working_directory=dirs["working"],
        outputs_directory=dirs["outputs"],
        configs_directory=dirs["configs"],
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def _partial_configs_copy(dirs, then):
    return f"""cp() {{
    if [ "$2" = "{dirs['configs']}" ]; then
        mkdir "$3"; : > "$3/registry.xml"; {then}
    fi
    command cp "$@"
}}
"""


def _assert_same_tree(left, right):
    comparison = filecmp.dircmp(left, right)
    assert not comparison.left_only and not comparison.right_only and not comparison.diff_files
    _, mismatch, errors = filecmp.cmpfiles(left, right, comparison.common_files, shallow=False)
    assert not mismatch and not errors


def test_prepare_dirs_rerun_after_interrupted_backup(tmp_path):
    dirs = _job_dir(tmp_path)
    interrupted = _prepare_dirs(dirs, preamble=_partial_configs_copy(dirs, "kill -KILL $$"))
    assert interrupted.returncode == -9

    result = _prepare_dirs(dirs)

    assert result.returncode == 0, result.stderr
    assert (dirs["configs"] / "registry.xml").read_text() == "<registry/>\n"
    for name, path in dirs.items():
        _assert_same_tree(path, tmp_path / f"{name}.orig")


def test_prepare_dirs_leaves_no_backup_after_failed_copy(tmp_path):
    dirs = _job_dir(tmp_path)

    _prepare_dirs(dirs, preamble=_partial_configs_copy(dirs, "return 1"))

    assert not (tmp_path / "configs.orig").exists()
    _assert_same_tree(dirs["working"], tmp_path / "working.orig")
