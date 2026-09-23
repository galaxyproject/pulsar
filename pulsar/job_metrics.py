"""Build Pulsar's job metrics configuration.

Pulsar and Galaxy are meant to be handed the same metrics configuration, and the
documentation tells deployers to keep the two files identical. They ship and upgrade
separately though, so that file will periodically name a plugin one side has and the other
does not - Galaxy's ``pulsar_transfer`` plugin, for instance, which Galaxy collects but which
instruments nothing on this side.

Pulsar's copy of the configuration exists for one purpose: producing the instrumentation
commands that go into the job script. A plugin this Pulsar has never heard of contributes no
commands, so it is logged and skipped rather than being a reason to refuse to start. Galaxy
still validates the same file strictly, which is where a mistyped plugin name gets caught.
"""

import logging
import os
from typing import (
    Any,
    Dict,
    List,
)

from galaxy.job_metrics import (
    instrumenters,
    JobMetrics,
)
from galaxy.util import plugin_config

log = logging.getLogger(__name__)

DEFAULT_JOB_METRICS_CONFIG_FILE = "job_metrics_conf.xml"


def build_job_metrics(config_dir: str, conf: Dict[str, Any]) -> JobMetrics:
    """Job metrics for a Pulsar app, skipping plugins this Pulsar does not have."""
    config_file = os.path.join(
        config_dir, conf.get("job_metrics_config_file", DEFAULT_JOB_METRICS_CONFIG_FILE)
    )
    if not os.path.exists(config_file):
        return JobMetrics(config_file)
    known_types = set(plugin_config.plugins_dict(instrumenters, "plugin_type"))
    configured = _plugin_dicts(plugin_config.plugin_source_from_path(config_file))
    available = [c for c in configured if c.get("type") in known_types]
    skipped = [str(c.get("type")) for c in configured if c.get("type") not in known_types]
    if skipped:
        log.info(
            "Skipping job metrics plugin(s) %s configured in %s - not available to this "
            "Pulsar, which knows %s. Nothing to do here if Galaxy collects them without "
            "instrumenting the job script; otherwise this Pulsar's galaxy-job-metrics is "
            "older than the configuration.",
            ", ".join(sorted(skipped)),
            config_file,
            ", ".join(sorted(known_types)),
        )
    return JobMetrics(conf_dict=available)


def _plugin_dicts(plugin_source: "plugin_config.PluginConfigSource") -> List[Dict[str, Any]]:
    """Normalize either configuration syntax to the list of dicts ``JobMetrics`` accepts.

    The XML reading mirrors ``plugin_config.__load_plugins_from_element``: the tag is the
    plugin type and the attributes are its keyword arguments. Child elements are ignored
    there too.
    """
    if plugin_source.type == "xml":
        return [dict(element.items(), type=element.tag) for element in plugin_source.source]
    configured = plugin_source.source or []
    if isinstance(configured, dict):
        configured = [configured]
    return [dict(config) for config in configured]


__all__ = ("build_job_metrics",)
