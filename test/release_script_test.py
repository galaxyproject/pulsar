import importlib.util
import os
import subprocess
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(__file__), os.pardir, "tools")

HISTORY = """History
-------

.. to_doc

---------------------
0.15.16.dev0
---------------------

* Fix a thing. `Pull Request 2`_


---------------------
0.15.15 (2026-07-13)
---------------------

* Older thing (thanks to `@someone`_). `Pull Request 1`_

.. github_links
.. _Pull Request 2: https://github.com/galaxyproject/pulsar/pull/2
.. _Pull Request 1: https://github.com/galaxyproject/pulsar/pull/1

.. _@someone: https://github.com/someone
"""


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _tool("release")


def test_release_then_start_next_version():
    released = release.mark_released(HISTORY, "0.15.16.dev0", "0.15.16", "2026-10-06")
    assert "\n0.15.16 (2026-10-06)\n" in released
    assert "dev0" not in released
    started = release.start_version(released, release.next_patch("0.15.16"))
    assert release.top_header(started) == "0.15.17.dev0"
    assert started.index("0.15.17.dev0") < started.index("0.15.16 (2026-10-06)")


def test_set_version():
    init = "__version__ = '0.15.16.dev0'\n\nPROJECT_NAME = \"pulsar\"\n"
    assert release.set_version(init, "0.15.16").startswith("__version__ = '0.15.16'\n")
    assert release.release_version("0.15.16.dev0") == "0.15.16"


def test_missing_history_prs_skips_dependabot_and_non_pr_merges():
    subjects = [
        "Merge pull request #3 from someone/feature",
        "Merge pull request #4 from galaxyproject/dependabot/pip/foo-1.2",
        "Merge pull request #2 from someone/fix",
        "Merge branch 'release_0.15'",
    ]
    assert release.missing_history_prs(HISTORY, subjects) == ["3"]


def test_missing_history_prs_accepts_wrapped_references():
    wrapped = HISTORY.replace("* Fix a thing. `Pull Request 2`_", "* Fix a thing. `Pull\n  Request 2`_")
    assert release.missing_history_prs(wrapped, ["Merge pull request #2 from someone/fix"]) == []


def test_merged_prs_follow_release_branches_but_not_fork_merges(tmp_path, monkeypatch):
    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init", "-q", "-b", "master")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    run("tag", "0.15.16")
    run("checkout", "-q", "-b", "release_0.15")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "fix")
    run("checkout", "-q", "-b", "fix", "0.15.16")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "fix 2")
    run("checkout", "-q", "release_0.15")
    run("-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "fix", "-m",
        "Merge pull request #7 from someone/fix")
    # A feature branch carrying a PR merged on a fork; only the upstream PR counts.
    run("checkout", "-q", "-b", "feature", "0.15.16")
    run("checkout", "-q", "-b", "fork_pr", "0.15.16")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "fork work")
    run("checkout", "-q", "feature")
    run("-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "fork_pr", "-m",
        "Merge pull request #5 from someone/fork_pr")
    run("checkout", "-q", "master")
    run("-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "feature", "-m",
        "Merge pull request #9 from someone/feature")
    run("-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "release_0.15", "-m",
        "Merge branch 'release_0.15'")
    monkeypatch.setattr(release, "PROJECT_DIRECTORY", str(tmp_path))
    assert sorted(release.missing_history_prs(HISTORY, release.merge_subjects("0.15.16"))) == ["7", "9"]


@pytest.mark.parametrize("branch,next_version,ok", [
    ("release_0.15", "0.15.17", True),
    ("release_0.15", "0.16.0", False),
    ("master", "0.16.0", True),
    ("master", "0.15.16", False),
])
def test_validate_next_version(branch, next_version, ok):
    if ok:
        release.validate_next_version("0.15.16", next_version, branch)
    else:
        with pytest.raises(release.ReleaseError):
            release.validate_next_version("0.15.16", next_version, branch)


def test_missing_targets():
    assert release.missing_targets(HISTORY) == []
    broken = HISTORY.replace("* Fix a thing.", "* Fix a thing (thanks to `@new`_).")
    assert release.missing_targets(broken) == ["@new"]


def test_repository_history_references_resolve():
    with open(os.path.join(release.PROJECT_DIRECTORY, release.HISTORY), encoding="utf-8") as f:
        assert release.missing_targets(f.read()) == []


def test_add_history_entry_goes_under_dev_header():
    sys.path.insert(0, release.PROJECT_DIRECTORY)
    bootstrap_history = _tool("bootstrap_history")
    history = bootstrap_history.add_entry(HISTORY, "* New thing. `Pull Request 3`_")
    assert release.top_header(history) == "0.15.16.dev0"
    assert history.index("0.15.16.dev0") < history.index("* New thing.") < history.index("* Fix a thing.")


@pytest.mark.parametrize("returncode,stdout,blocked", [
    (0, "[]", True),
    (1, "", True),
    (0, '[{"name": "Tests", "status": "completed", "conclusion": "success"}]', False),
    (0, '[{"name": "Tests", "status": "completed", "conclusion": "failure"}]', True),
])
def test_ci_problems(monkeypatch, returncode, stdout, blocked):
    monkeypatch.setattr(release.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        release.subprocess, "run",
        lambda *args, **kwds: subprocess.CompletedProcess(args, returncode, stdout, "boom"),
    )
    errors, _ = release.ci_problems("abc123")
    assert bool(errors) == blocked
