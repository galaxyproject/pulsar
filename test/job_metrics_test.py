"""Tests for building Pulsar's job metrics configuration."""
import os

import pytest

from pulsar.job_metrics import build_job_metrics
from .test_utils import temp_directory

GALAXY_ONLY_PLUGIN = "pulsar"


def _write(directory, name, contents):
    path = os.path.join(directory, name)
    with open(path, "w") as fh:
        fh.write(contents)
    return path


def _conf(name):
    return {"job_metrics_config_file": name}


def test_missing_config_file_keeps_the_default_of_core_only():
    with temp_directory() as directory:
        metrics = build_job_metrics(directory, _conf("nope.yml"))
        assert metrics.default_job_instrumenter.get_configured_plugin("core") is not None
        assert metrics.default_job_instrumenter.get_configured_plugin("hostname") is None


@pytest.mark.parametrize(
    "name,contents,plugin,options",
    [
        ("metrics.yml", f"- type: core\n- type: hostname\n- type: {GALAXY_ONLY_PLUGIN}\n", "hostname", {}),
        (
            "metrics.xml",
            f'<job_metrics><core /><cpuinfo verbose="true" /><{GALAXY_ONLY_PLUGIN} /></job_metrics>',
            "cpuinfo",
            {"verbose": True},
        ),
    ],
)
def test_loads_known_plugins_and_skips_unknown_ones(name, contents, plugin, options):
    with temp_directory() as directory:
        _write(directory, name, contents)
        instrumenter = build_job_metrics(directory, _conf(name)).default_job_instrumenter
        assert instrumenter.get_configured_plugin("core") is not None
        configured = instrumenter.get_configured_plugin(plugin)
        assert configured is not None
        for option, value in options.items():
            assert getattr(configured, option) == value


def test_a_config_of_only_unknown_plugins_configures_nothing():
    with temp_directory() as directory:
        _write(directory, "metrics.yml", f"- type: {GALAXY_ONLY_PLUGIN}_from_the_future\n")
        metrics = build_job_metrics(directory, _conf("metrics.yml"))
        assert metrics.default_job_instrumenter.pre_execute_commands("/job/dir") is None
