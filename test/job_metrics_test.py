"""Tests for building Pulsar's job metrics configuration."""
import os

import pytest
from galaxy.job_metrics import JobMetrics

from pulsar.job_metrics import build_job_metrics
from .test_utils import temp_directory

GALAXY_ONLY_PLUGIN = "pulsar_transfer"


def _write(directory, name, contents):
    path = os.path.join(directory, name)
    with open(path, "w") as fh:
        fh.write(contents)
    return path


def _conf(directory, name):
    return {"job_metrics_config_file": name}


def test_missing_config_file_keeps_the_default_of_core_only():
    with temp_directory() as directory:
        metrics = build_job_metrics(directory, _conf(directory, "nope.yml"))
        assert metrics.default_job_instrumenter.get_configured_plugin("core") is not None
        assert metrics.default_job_instrumenter.get_configured_plugin("hostname") is None


def test_yaml_config_loads_plugins():
    with temp_directory() as directory:
        _write(directory, "metrics.yml", "- type: core\n- type: hostname\n")
        metrics = build_job_metrics(directory, _conf(directory, "metrics.yml"))
        assert metrics.default_job_instrumenter.get_configured_plugin("core") is not None
        assert metrics.default_job_instrumenter.get_configured_plugin("hostname") is not None


def test_xml_config_loads_plugins_with_their_options():
    with temp_directory() as directory:
        _write(directory, "metrics.xml", '<job_metrics><core /><cpuinfo verbose="true" /></job_metrics>')
        metrics = build_job_metrics(directory, _conf(directory, "metrics.xml"))
        cpuinfo = metrics.default_job_instrumenter.get_configured_plugin("cpuinfo")
        assert cpuinfo is not None
        assert cpuinfo.verbose
        assert metrics.default_job_instrumenter.get_configured_plugin("core") is not None


def test_unknown_plugin_is_skipped_rather_than_fatal():
    with temp_directory() as directory:
        name = "metrics.yml"
        _write(directory, name, "- type: core\n- type: not_a_real_plugin\n")
        with pytest.raises(Exception):
            JobMetrics(os.path.join(directory, name))
        metrics = build_job_metrics(directory, _conf(directory, name))
        assert metrics.default_job_instrumenter.get_configured_plugin("core") is not None
        assert metrics.default_job_instrumenter.get_configured_plugin("not_a_real_plugin") is None


def test_unknown_plugin_is_skipped_in_xml_too():
    with temp_directory() as directory:
        _write(directory, "metrics.xml", "<job_metrics><core /><not_a_real_plugin /></job_metrics>")
        metrics = build_job_metrics(directory, _conf(directory, "metrics.xml"))
        assert metrics.default_job_instrumenter.get_configured_plugin("core") is not None


def test_a_config_of_only_unknown_plugins_configures_nothing():
    with temp_directory() as directory:
        _write(directory, "metrics.yml", f"- type: {GALAXY_ONLY_PLUGIN}_from_the_future\n")
        metrics = build_job_metrics(directory, _conf(directory, "metrics.yml"))
        assert metrics.default_job_instrumenter.pre_execute_commands("/job/dir") is None


def test_a_galaxy_side_plugin_never_instruments_the_job_script():
    with temp_directory() as directory:
        _write(directory, "metrics.yml", f"- type: core\n- type: {GALAXY_ONLY_PLUGIN}\n")
        metrics = build_job_metrics(directory, _conf(directory, "metrics.yml"))
        instrumenter = metrics.default_job_instrumenter
        assert instrumenter.get_configured_plugin("core") is not None
        commands = instrumenter.pre_execute_commands(directory)
        assert GALAXY_ONLY_PLUGIN not in commands
