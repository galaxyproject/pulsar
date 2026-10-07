import importlib.util
import os
import sys

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
