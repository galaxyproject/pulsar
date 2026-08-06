"""Unit tests for the cvmfsexec job-script helper (pulsar.managers.util.cvmfsexec)."""
import pytest

from pulsar.managers.util import cvmfsexec


def test_parse_none_disabled():
    assert cvmfsexec.parse(None) is None
    assert cvmfsexec.parse({}) is None


def test_parse_defaults():
    config = cvmfsexec.parse({
        "path": "/opt/cvmfsexec",
        "repositories": ["data.galaxyproject.org", "singularity.galaxyproject.org"],
    })
    assert config.mode == cvmfsexec.MODE_MOUNTREPO
    assert config.path == "/opt/cvmfsexec"
    assert config.repositories == ["data.galaxyproject.org", "singularity.galaxyproject.org"]


def test_parse_requires_path():
    with pytest.raises(ValueError):
        cvmfsexec.parse({"repositories": ["a"]})


def test_parse_requires_repositories():
    with pytest.raises(ValueError):
        cvmfsexec.parse({"path": "/opt/cvmfsexec"})


def test_parse_rejects_invalid_mode():
    with pytest.raises(ValueError):
        cvmfsexec.parse({"mode": "bogus", "path": "/x", "repositories": ["a"]})


def test_setup_commands_mountrepo():
    config = cvmfsexec.parse({
        "path": "/opt/cvmfsexec",
        "repositories": ["data.galaxyproject.org", "singularity.galaxyproject.org"],
    })
    commands = cvmfsexec.setup_commands(config, "/jobs/7")
    # Absolute job directory used directly (no $CVMFSEXEC_DIR shell variable).
    assert commands[0].startswith("cp /opt/cvmfsexec /jobs/7/cvmfsexec ")
    assert any(c.startswith("/jobs/7/cvmfsexec -v >/dev/null ") for c in commands)
    # Unmount cleanup is an EXIT handler (exit_handler_commands), not part of the
    # setup preamble, and nothing here claims the trap slot directly.
    assert not any("umountrepo" in c for c in commands)
    assert not any(c.startswith("trap ") for c in commands)
    # Each mount aborts the job with a diagnostic on failure (point 4).
    assert (
        "/jobs/7/.cvmfsexec/mountrepo data.galaxyproject.org "
        "|| { echo 'cvmfsexec: failed to mount data.galaxyproject.org' >&2; exit 1; }"
    ) in commands
    assert any(c.startswith("/jobs/7/.cvmfsexec/mountrepo singularity.galaxyproject.org ") for c in commands)
    assert not any("CVMFSEXEC_DIR" in c for c in commands)


def test_add_exit_handlers_mountrepo_unmounts():
    from pulsar.managers.util.job_script import ExitHandlers
    handlers = ExitHandlers()
    config = cvmfsexec.parse({
        "path": "/opt/cvmfsexec",
        "repositories": ["data.galaxyproject.org", "singularity.galaxyproject.org"],
    })
    cvmfsexec.add_exit_handlers(handlers, config, "/jobs/7")
    # cvmfsexec only contributes to the generic ExitHandlers collector.
    assert handlers.commands == ["/jobs/7/.cvmfsexec/umountrepo -a"]


def test_add_exit_handlers_namespace_is_noop():
    from pulsar.managers.util.job_script import ExitHandlers
    handlers = ExitHandlers()
    config = cvmfsexec.parse({
        "mode": "namespace",
        "path": "/opt/cvmfsexec",
        "repositories": ["data.galaxyproject.org"],
    })
    cvmfsexec.add_exit_handlers(handlers, config, "/jobs/7")
    assert handlers.commands == []


def test_setup_commands_quotes_shell_metacharacters():
    # A per-job override arrives over the wire; a repository (or path) carrying
    # shell metacharacters must be quoted, never interpolated raw.
    config = cvmfsexec.parse({
        "path": "/opt/cvmfsexec",
        "repositories": ["$(touch pwned)"],
    })
    commands = cvmfsexec.setup_commands(config, "/jobs/7")
    mount = next(c for c in commands if c.startswith("/jobs/7/.cvmfsexec/mountrepo "))
    assert mount.startswith("/jobs/7/.cvmfsexec/mountrepo '$(touch pwned)'")


def test_setup_commands_namespace_exports_env():
    config = cvmfsexec.parse({
        "mode": "namespace",
        "path": "/opt/cvmfsexec",
        "repositories": ["data.galaxyproject.org"],
    })
    # Namespace mode wraps the command in a fresh `bash -c`; the preamble exports
    # the shell state (tmp dirs, Galaxy env, and the setup function) that would
    # otherwise not cross the boundary.
    assert cvmfsexec.setup_commands(config, "/jobs/7") == [
        "export TMP TEMP TMPDIR",
        "export GALAXY_VIRTUAL_ENV _GALAXY_VIRTUAL_ENV GALAXY_LIB GALAXY_PYTHON",
        "export -f _galaxy_setup_environment",
    ]


def test_wrap_command_namespace():
    config = cvmfsexec.parse({
        "mode": "namespace",
        "path": "/opt/cvmfsexec",
        "repositories": ["data.galaxyproject.org", "singularity.galaxyproject.org"],
    })
    wrapped = cvmfsexec.wrap_command(config, "run_tool --flag")
    assert wrapped == (
        "/opt/cvmfsexec data.galaxyproject.org singularity.galaxyproject.org "
        "-- /bin/bash -c 'run_tool --flag'"
    )


def test_wrap_command_mountrepo_is_noop():
    config = cvmfsexec.parse({
        "path": "/opt/cvmfsexec",
        "repositories": ["singularity.galaxyproject.org"],
    })
    assert cvmfsexec.wrap_command(config, "run_tool") == "run_tool"
