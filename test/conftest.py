"""Pytest options shared between the unit/integration suite and the
docker-compose-backed resilience suite under ``test/resilience/``.

``pytest_addoption`` hooks declared in deeper conftest files are silently
ignored by pytest unless that file is the rootdir conftest. Putting the
options here ensures they are registered for every invocation that walks
into ``test/`` — including the standard ``tox -e test-unit`` runs that
collect the resilience tree only to skip it.
"""


def pytest_addoption(parser):
    parser.addoption(
        "--no-docker",
        action="store_true",
        default=False,
        help="Skip resilience tests that need a running docker-compose stack.",
    )
    parser.addoption(
        "--keep-stack",
        action="store_true",
        default=False,
        help="Don't tear down docker-compose at session end (faster local iteration).",
    )
