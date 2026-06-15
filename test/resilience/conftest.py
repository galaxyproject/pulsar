"""Pytest fixtures for the docker-compose-backed resilience suite.

The session-scoped ``compose_up`` fixture brings the stack up once. Per-test
fixtures wipe state (mock-galaxy recorder, RabbitMQ queues, Pulsar staging
volumes) and parametrize over messaging modes.

Tests opt into this framework with the ``resilience`` marker; the suite is
skipped automatically if ``docker compose`` or toxiproxy is not available,
or if the user passed ``--no-docker`` to pytest. Pytest options
(``--no-docker``, ``--keep-stack``) are registered in ``test/conftest.py``
at the rootdir so they apply to both this suite and the unit suite that
collects it only to skip it.
"""
import os
import shutil
import subprocess

import pytest
import requests

from harness.broker_control import ToxiproxyControl
from harness.pulsar_control import PulsarControl

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
GALAXY_BASE = "http://localhost:8088"
TOXIPROXY_ADMIN = "http://localhost:8474"


def pytest_addoption(parser):
    # Also registered in ``test/conftest.py`` for the full unit suite. When
    # this suite is invoked directly (``pytest test/resilience``), the
    # rootdir is this directory and the parent conftest is not loaded, so
    # we have to register again. Both ``argparse`` and pytest tolerate the
    # second call as long as the option exists; we still guard with a
    # try/except in case pytest tightens that in a future version.
    try:
        parser.addoption(
            "--no-docker",
            action="store_true",
            default=False,
            help="Skip resilience tests that need a running docker-compose stack.",
        )
    except ValueError:
        pass
    try:
        parser.addoption(
            "--keep-stack",
            action="store_true",
            default=False,
            help="Don't tear down docker-compose at session end.",
        )
    except ValueError:
        pass


def _docker_available():
    return shutil.which("docker") is not None


def _stack_reachable():
    try:
        r = requests.get(f"{TOXIPROXY_ADMIN}/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def compose_up(request):
    """Require the docker-compose stack to already be up.

    We deliberately don't auto-launch the stack here: the unit-test tox env
    runs in environments (CI, contributor laptops) that have docker
    available but no resilience stack running, and a 60+ second compose-up
    on every unit run would be wrong. The user is expected to bring the
    stack up explicitly before exercising the resilience suite, e.g.::

        docker compose -f test/resilience/docker-compose.yml up -d --build
        pytest test/resilience -v
    """
    if request.config.getoption("--no-docker") or not _docker_available():
        pytest.skip("docker not available; skipping resilience suite")

    if not _stack_reachable():
        pytest.skip(
            "resilience docker-compose stack is not running; "
            "start it with `docker compose -f test/resilience/docker-compose.yml up -d --build` "
            "before running test/resilience scenarios."
        )

    yield

    if not request.config.getoption("--keep-stack"):
        subprocess.run(
            ["docker", "compose", "-f", f"{PROJECT_DIR}/docker-compose.yml", "down", "-v"],
            check=False,
        )


MQ_MODES = ["amqp", "amqp_ack", "relay"]


def pytest_generate_tests(metafunc):
    """Parametrize ``mq_mode`` over all messaging modes by default.

    Previously ``mq_mode`` was a parametrized fixture (``params=MQ_MODES``).
    Tests that only make sense for a single mode narrowed it with their own
    ``@pytest.mark.parametrize("mq_mode", [...], indirect=True)``. Under
    pytest < 9.1 the per-test parametrize overrode the fixture's params; pytest
    9.1 instead rejects the two sources as a "duplicate parametrization of
    'mq_mode'" collection error, which aborts the whole session.

    Applying the default here only when the test hasn't already parametrized
    ``mq_mode`` keeps the single source of truth pytest 9.1 requires while
    preserving the existing behavior (full matrix by default, override allowed).
    """
    if "mq_mode" not in metafunc.fixturenames:
        return
    already_parametrized = any(
        marker.args and "mq_mode" in [name.strip() for name in str(marker.args[0]).split(",")]
        for marker in metafunc.definition.iter_markers("parametrize")
    )
    if not already_parametrized:
        metafunc.parametrize("mq_mode", MQ_MODES, indirect=True, ids=lambda m: f"mode={m}")


@pytest.fixture
def mq_mode(request):
    return request.param


@pytest.fixture
def pulsar(compose_up, mq_mode):
    ctrl = PulsarControl(PROJECT_DIR, mode=mq_mode)
    # Wipe state at fixture entry only; tests that kill/restart reuse persisted
    # state to validate recovery semantics.
    ctrl.start(wait_ready=True, fresh=True)
    yield ctrl
    ctrl.stop()


@pytest.fixture
def rabbitmq_proxy(compose_up):
    p = ToxiproxyControl("rabbitmq", admin=TOXIPROXY_ADMIN)
    p.enable()
    p.remove_all_toxics()
    yield p
    p.enable()
    p.remove_all_toxics()


@pytest.fixture
def relay_proxy(compose_up):
    p = ToxiproxyControl("relay", admin=TOXIPROXY_ADMIN)
    p.enable()
    p.remove_all_toxics()
    yield p
    p.enable()
    p.remove_all_toxics()


@pytest.fixture
def galaxy_proxy(compose_up):
    p = ToxiproxyControl("galaxy_http", admin=TOXIPROXY_ADMIN)
    p.enable()
    p.remove_all_toxics()
    yield p
    p.enable()
    p.remove_all_toxics()


@pytest.fixture(autouse=True)
def _clear_recorder_each_test():
    """Best-effort recorder reset between tests. Does not depend on
    ``compose_up`` so the pure-python recorder unit tests under
    ``mock_galaxy/`` still run when docker is not available."""
    try:
        requests.post(f"{GALAXY_BASE}/_recorder/clear", timeout=2)
    except Exception:
        pass
    yield
