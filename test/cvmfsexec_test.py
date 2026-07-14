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
    commands = cvmfsexec.setup_commands(config)
    assert commands[0] == 'export CVMFSEXEC_DIR="$(dirname "$_GALAXY_JOB_DIR")"'
    assert 'cp "/opt/cvmfsexec" "$CVMFSEXEC_DIR/cvmfsexec"' in commands
    assert 'trap "$CVMFSEXEC_DIR/.cvmfsexec/umountrepo -a" EXIT' in commands
    assert '"$CVMFSEXEC_DIR/.cvmfsexec/mountrepo" data.galaxyproject.org' in commands
    assert '"$CVMFSEXEC_DIR/.cvmfsexec/mountrepo" singularity.galaxyproject.org' in commands


def test_setup_commands_namespace_is_empty():
    config = cvmfsexec.parse({
        "mode": "namespace",
        "path": "/opt/cvmfsexec",
        "repositories": ["data.galaxyproject.org"],
    })
    assert cvmfsexec.setup_commands(config) == []


def test_wrap_command_namespace():
    config = cvmfsexec.parse({
        "mode": "namespace",
        "path": "/opt/cvmfsexec",
        "repositories": ["data.galaxyproject.org", "singularity.galaxyproject.org"],
    })
    wrapped = cvmfsexec.wrap_command(config, "run_tool --flag")
    assert wrapped == (
        '"/opt/cvmfsexec" data.galaxyproject.org singularity.galaxyproject.org '
        "-- /bin/bash -c 'run_tool --flag'"
    )


def test_wrap_command_mountrepo_is_noop():
    config = cvmfsexec.parse({
        "path": "/opt/cvmfsexec",
        "repositories": ["singularity.galaxyproject.org"],
    })
    assert cvmfsexec.wrap_command(config, "run_tool") == "run_tool"
