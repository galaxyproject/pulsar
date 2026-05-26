"""Unit tests for the capabilities collector.

The collector is exercised against a real ``StatefulManagerProxy`` /
``QueueManager`` (see ``test_collect_capabilities_against_real_queue_manager``)
so it fails on real contract drift rather than green-lighting hand-built
fakes that encode the same assumptions as the code under test.

The remaining helpers/doubles are intentionally minimal and limited to:
    * ``shutil.which`` patches at the OS boundary (conda/container detection),
    * a real ``CondaDependencyResolver`` subclass instance bypassing its heavy
      ``__init__`` (because the collector uses ``isinstance``),
    * a tiny ``_Resolver`` stub for non-conda resolver attribute checks,
    * a tiny ``_StubProxy`` for the two ``num_concurrent_jobs``-fallback
      branches in ``_collect_manager``, which are unreachable by any
      in-tree real manager (see comment on those tests).
"""
import json
from contextlib import contextmanager
from shutil import rmtree
from unittest import mock

import pytest
from galaxy.tool_util.deps.resolvers.conda import CondaDependencyResolver
from galaxy.util.bunch import Bunch

from pulsar import capabilities
from pulsar.capabilities import (
    ContainerRuntimeInfo,
    DependencyResolverInfo,
    _collect_dependency_resolvers,
    _collect_manager,
    _conda_available,
    _detect_container_runtime,
    collect_capabilities,
)
from pulsar.managers.queued import QueueManager
from pulsar.managers.stateful import StatefulManagerProxy

from .test_utils import (
    TestDependencyManager,
    minimal_app_for_managers,
)


@pytest.fixture
def no_host_binaries():
    """Pin ``shutil.which`` to None so container/conda detection is host-independent."""
    with mock.patch.object(capabilities.shutil, "which", return_value=None):
        yield


@contextmanager
def _real_queue_manager_proxy(app, name="_default_", num_concurrent_jobs=4):
    proxy = StatefulManagerProxy(QueueManager(name, app, num_concurrent_jobs=num_concurrent_jobs))
    try:
        yield proxy
    finally:
        try:
            proxy.shutdown()
        except Exception:
            pass


def test_collect_capabilities_against_real_queue_manager(no_host_binaries):
    """End-to-end: real ``StatefulManagerProxy(QueueManager(...))`` on a real
    minimal app. Asserts the contracts the publisher relies on
    (manager_type class attr, work_threads length, staging/persistence dirs,
    resolver list) — if any of these drift, this test breaks."""
    app = minimal_app_for_managers()
    try:
        with _real_queue_manager_proxy(app, num_concurrent_jobs=4) as proxy:
            caps = collect_capabilities(app, proxy)
            assert caps.schema_version == 1
            assert caps.manager_name == "_default_"
            assert caps.manager.type == "queued_python"
            assert caps.manager.num_concurrent_jobs == 4
            assert caps.staging_directory == app.staging_directory
            assert caps.persistence_directory == app.persistence_directory
            assert caps.dependency_resolvers == []
            assert caps.conda_available is False
            assert caps.container_runtime == ContainerRuntimeInfo()
    finally:
        try:
            rmtree(app.staging_directory)
        except Exception:
            pass


def test_to_dict_round_trips_through_json(no_host_binaries):
    app = minimal_app_for_managers()
    try:
        with _real_queue_manager_proxy(app, num_concurrent_jobs=1) as proxy:
            caps = collect_capabilities(app, proxy)
            decoded = json.loads(json.dumps(caps.to_dict()))
            assert decoded["manager"]["type"] == "queued_python"
            assert decoded["schema_version"] == 1
    finally:
        try:
            rmtree(app.staging_directory)
        except Exception:
            pass


def test_conda_resolver_present_and_conda_on_path():
    resolvers = [
        DependencyResolverInfo(type="conda", disabled=False, prefix="/srv/_conda"),
    ]
    with mock.patch.object(capabilities.shutil, "which", return_value="/usr/bin/conda"):
        assert _conda_available(resolvers) is True


def test_conda_resolver_present_but_not_on_path_or_disk(tmp_path, no_host_binaries):
    # ``missing`` is never created on disk, so the real ``isdir`` returns False.
    missing = tmp_path / "no_conda_here"
    resolvers = [
        DependencyResolverInfo(type="conda", disabled=False, prefix=str(missing)),
    ]
    assert _conda_available(resolvers) is False


def test_conda_resolver_disabled_means_unavailable_even_if_conda_on_path():
    resolvers = [
        DependencyResolverInfo(type="conda", disabled=True, prefix="/srv/_conda"),
    ]
    with mock.patch.object(capabilities.shutil, "which", return_value="/usr/bin/conda"):
        assert _conda_available(resolvers) is False


def test_conda_available_via_existing_prefix_on_disk(tmp_path, no_host_binaries):
    resolvers = [
        DependencyResolverInfo(type="conda", disabled=False, prefix=str(tmp_path)),
    ]
    assert _conda_available(resolvers) is True


@pytest.mark.parametrize("docker,singularity,apptainer", [
    (True, False, False),
    (False, True, False),
    (False, False, True),
    (True, True, True),
    (False, False, False),
])
def test_detect_container_runtime_cross_product(docker, singularity, apptainer):
    def fake_which(binary):
        return {
            "docker": "/usr/bin/docker" if docker else None,
            "singularity": "/usr/bin/singularity" if singularity else None,
            "apptainer": "/usr/bin/apptainer" if apptainer else None,
        }.get(binary)
    with mock.patch.object(capabilities.shutil, "which", side_effect=fake_which):
        cr = _detect_container_runtime()
    assert cr.docker_available is docker
    assert cr.singularity_available is singularity
    assert cr.apptainer_available is apptainer


def _make_conda_resolver(*, prefix, **attrs):
    """Build a real CondaDependencyResolver bypassing its heavy __init__.

    The collector uses ``isinstance(r, CondaDependencyResolver)`` to
    pick conda-specific fields, so the test fixture has to be a real
    subclass instance — duck-typed mocks won't match. ``prefix`` is a
    property reading ``self.conda_context.conda_prefix``, so we set the
    underlying field rather than trying to assign through the property.
    """
    class _CondaContext:
        def __init__(self, p):
            self.conda_prefix = p

    inst = CondaDependencyResolver.__new__(CondaDependencyResolver)
    inst.conda_context = _CondaContext(prefix)
    for k, v in attrs.items():
        setattr(inst, k, v)
    return inst


class _Resolver:
    """Minimal non-conda resolver stub.

    Resolver subclasses legitimately vary in attributes; the collector
    probes via ``getattr``/``isinstance``, so a stub at this boundary is
    correct rather than a real subclass.
    """

    def __init__(self, resolver_type, **attrs):
        self.resolver_type = resolver_type
        for k, v in attrs.items():
            setattr(self, k, v)


def test_collects_dependency_resolver_attributes():
    resolvers = [
        _Resolver("tool_shed_packages", versionless=False, disabled=False),
        _make_conda_resolver(
            disabled=True, auto_init=True, auto_install=False,
            prefix="/p", versionless=True,
        ),
    ]
    app = Bunch(dependency_manager=TestDependencyManager(dependency_resolvers=resolvers))
    out = _collect_dependency_resolvers(app)
    assert len(out) == 2
    assert out[0].type == "tool_shed_packages"
    assert out[0].disabled is False
    assert out[1].type == "conda"
    assert out[1].disabled is True
    assert out[1].auto_init is True
    assert out[1].auto_install is False
    assert out[1].prefix == "/p"
    assert out[1].versionless is True


def test_resolver_without_resolver_type_is_skipped():
    # Some resolver subclasses might not set resolver_type; we drop them
    # rather than emit a noisy unknown entry.
    resolvers = [_Resolver(None), _Resolver("conda", disabled=False)]
    app = Bunch(dependency_manager=TestDependencyManager(dependency_resolvers=resolvers))
    out = _collect_dependency_resolvers(app)
    assert [r.type for r in out] == ["conda"]


class _StubProxy:
    """Minimal proxy stub for the ``num_concurrent_jobs`` fallback branch.

    The fallback path in ``_collect_manager`` reads
    ``underlying.num_concurrent_jobs`` only when ``underlying.work_threads``
    is missing. **No in-tree manager has this shape** — every concrete
    Pulsar manager either inherits ``QueueManager`` (which always sets
    ``work_threads``) or is unqueued and exposes neither. The branch
    exists purely as a defensive hook for hypothetical third-party
    manager subclasses, so a real-object test cannot reach it; a 3-line
    stub here is the only way to cover that intentionally-third-party-only
    code path.
    """

    def __init__(self, num_concurrent_jobs=None):
        self.name = "m"
        underlying = type("Underlying", (object,), {"manager_type": "unqueued"})()
        if num_concurrent_jobs is not None:
            underlying.num_concurrent_jobs = num_concurrent_jobs
        self._proxied_manager = underlying


def test_num_concurrent_jobs_falls_back_to_attr():
    assert _collect_manager(_StubProxy(num_concurrent_jobs=7)).num_concurrent_jobs == 7


def test_num_concurrent_jobs_none_when_neither():
    assert _collect_manager(_StubProxy()).num_concurrent_jobs is None
