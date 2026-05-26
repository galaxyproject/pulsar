"""Static capability snapshot collection for a Pulsar app.

A ``PulsarCapabilities`` is a serializable summary of what a Pulsar
server is configured to do — staging paths, dependency resolvers,
container runtimes available on the host — so that Galaxy can read it
at job-build time and adjust (or refuse) requests that the remote does
not actually support.

The data is collected on demand by the relay publisher in
``messaging.bind_app`` (lazily, only when relay mode is active and the
``message_queue_publish_capabilities`` knob is on). It is never recomputed
within a process; consumers fetch the latest snapshot via the relay's REST
topic-messages endpoint.

Schema is versioned (``SCHEMA_VERSION``); bumping it is a wire-breaking
change for consumers, so add new optional fields rather than reshape
existing ones.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import (
    asdict,
    dataclass,
    field,
)
from typing import (
    TYPE_CHECKING,
    List,
    Optional,
    Union,
)

from galaxy.tool_util.deps.resolvers.conda import CondaDependencyResolver

from pulsar import __version__ as pulsar_version

if TYPE_CHECKING:
    from pulsar.core import PulsarApp
    from pulsar.managers.stateful import StatefulManagerProxy

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass
class DependencyResolverInfo:
    type: str
    disabled: bool = False
    versionless: bool = False
    auto_init: Optional[bool] = None
    auto_install: Optional[bool] = None
    prefix: Optional[str] = None


@dataclass
class ContainerRuntimeInfo:
    docker_available: bool = False
    singularity_available: bool = False
    apptainer_available: bool = False


@dataclass
class ManagerCapabilities:
    name: str
    type: str
    num_concurrent_jobs: Union[int, str, None] = None


@dataclass
class PulsarCapabilities:
    schema_version: int
    manager_name: str
    pulsar_version: str
    staging_directory: str
    persistence_directory: Optional[str]
    tool_dependency_dir: Optional[str]
    dependency_resolvers: List[DependencyResolverInfo] = field(default_factory=list)
    conda_available: bool = False
    container_runtime: ContainerRuntimeInfo = field(default_factory=ContainerRuntimeInfo)
    manager: Optional[ManagerCapabilities] = None

    def to_dict(self) -> dict:
        return asdict(self)


def collect_capabilities(app: "PulsarApp", manager: "StatefulManagerProxy") -> PulsarCapabilities:
    """Build the capabilities snapshot for a single manager on this app."""
    resolvers = _collect_dependency_resolvers(app)
    manager_caps = _collect_manager(manager)
    return PulsarCapabilities(
        schema_version=SCHEMA_VERSION,
        manager_name=manager_caps.name,
        pulsar_version=pulsar_version,
        staging_directory=app.staging_directory,
        persistence_directory=app.persistence_directory,
        tool_dependency_dir=_tool_dependency_dir(app),
        dependency_resolvers=resolvers,
        conda_available=_conda_available(resolvers),
        container_runtime=_detect_container_runtime(),
        manager=manager_caps,
    )


def _collect_dependency_resolvers(app: "PulsarApp") -> List[DependencyResolverInfo]:
    out: List[DependencyResolverInfo] = []
    for r in app.dependency_manager.dependency_resolvers:
        # ``resolver_type`` and ``versionless`` are class attributes on
        # concrete subclasses, not the base — probe defensively rather
        # than narrow the loop type to every known subclass.
        rt = getattr(r, "resolver_type", None)
        if not rt:
            continue
        info = DependencyResolverInfo(
            type=str(rt),
            disabled=r.disabled,
            versionless=bool(getattr(r, "versionless", False)),
        )
        if isinstance(r, CondaDependencyResolver):
            info.auto_init = bool(r.auto_init)
            info.auto_install = bool(r.auto_install)
            info.prefix = str(r.prefix) if r.prefix else None
        out.append(info)
    return out


def _conda_available(resolvers: List[DependencyResolverInfo]) -> bool:
    """A conda resolver is enabled and conda is reachable on this host.

    "Reachable" means either the conda binary is on PATH or the resolver's
    configured prefix exists on disk — Galaxy on the requesting side wants
    to know whether ``dependency_resolution=remote`` will actually find
    something to run.
    """
    for r in resolvers:
        if r.type != "conda" or r.disabled:
            continue
        if shutil.which("conda"):
            return True
        if r.prefix and os.path.isdir(r.prefix):
            return True
    return False


def _detect_container_runtime() -> ContainerRuntimeInfo:
    return ContainerRuntimeInfo(
        docker_available=bool(shutil.which("docker")),
        singularity_available=bool(shutil.which("singularity")),
        apptainer_available=bool(shutil.which("apptainer")),
    )


def _collect_manager(manager: "StatefulManagerProxy") -> ManagerCapabilities:
    underlying = manager._proxied_manager
    # ``manager_type`` is a class attribute set on each concrete manager
    # implementation but not on the proxy or its base. The ``work_threads``
    # attribute is queued_python-only — falling back to a public
    # ``num_concurrent_jobs`` covers any future manager that exposes one.
    mtype = getattr(type(underlying), "manager_type", "unknown")
    work_threads = getattr(underlying, "work_threads", None)
    num: Union[int, str, None]
    if work_threads is not None:
        try:
            num = len(work_threads)
        except TypeError:
            num = None
    else:
        num = getattr(underlying, "num_concurrent_jobs", None)
    return ManagerCapabilities(name=manager.name, type=str(mtype), num_concurrent_jobs=num)


def _tool_dependency_dir(app: "PulsarApp") -> Optional[str]:
    base = getattr(app.dependency_manager, "default_base_path", None)
    return str(base) if base else None
