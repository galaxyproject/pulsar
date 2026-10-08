import importlib.util
import os
import subprocess

import pytest

TOOLS = os.path.join(os.path.dirname(__file__), os.pardir, "tools")

CHANGELOG = """# History

<!-- towncrier release notes start -->

## 0.15.15 (2026-07-13)

- Older thing. [Pull Request 1](https://github.com/galaxyproject/pulsar/pull/1)
"""
FRAGMENTS = {"2.bugfix.md": "Fix a thing.\n"}


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _tool("release")


def test_set_version():
    init = "__version__ = '0.15.16.dev0'\n\nPROJECT_NAME = \"pulsar\"\n"
    assert release.set_version(init, "0.15.16").startswith("__version__ = '0.15.16'\n")
    assert release.release_version("0.15.16.dev0") == "0.15.16"


def test_missing_change_prs_skips_dependabot_labeled_and_non_pr_merges():
    subjects = [
        "Merge pull request #3 from someone/feature",
        "Merge pull request #4 from galaxyproject/dependabot/pip/foo-1.2",
        "Merge pull request #2 from someone/fix",
        "Merge pull request #6 from someone/ci",
        "Merge branch 'release_0.15'",
    ]
    documented = release.documented_prs(CHANGELOG, FRAGMENTS)
    assert release.missing_change_prs(documented, subjects, skipped={"6"}) == ["3"]


def test_documented_prs_reads_fragment_names_and_links():
    fragments = {
        "2.bugfix.md": "Fix.\n",
        "3.feature.2.md": "Feature.\n",
        "+docs.misc.md": "Also covers [Pull Request 8](https://github.com/galaxyproject/pulsar/pull/8).\n",
    }
    assert release.documented_prs(CHANGELOG, fragments) == {"1", "2", "3", "8"}


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
    documented = release.documented_prs(CHANGELOG, FRAGMENTS)
    assert sorted(release.missing_change_prs(documented, release.merge_subjects("0.15.16"))) == ["7", "9"]


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


def test_change_entry_credits_outside_authors():
    pr = {"title": "Fix the thing.", "user": {"login": "natefoo"}}
    assert release.change_entry(pr) == "Fix the thing (thanks to [@natefoo](https://github.com/natefoo)).\n"
    pr = {"title": "Fix the thing", "user": {"login": "jmchilton"}}
    assert release.change_entry(pr) == "Fix the thing.\n"


def test_repository_changelog_renders_with_pending_changes():
    release.towncrier("build", "--draft", "--version", "99.0.0")


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
