from os import environ
from pathlib import Path
import platform
from typing import (
    Dict,
    Optional,
)

from galaxy.util.bunch import Bunch
from pydantictes.api import TesClient
from pydantictes.funnelfixture import funnel_client
import pytest


from pulsar.client.test.check import run
from .test_utils import (
    files_server,
    integration_test,
    IntegrationTestConfiguration,
    mark,
    skip_unless_any_module,
    skip_unless_environ,
    skip_unless_executable,
    skip_unless_module,
    skip_without_drmaa,
    test_pulsar_app,
    test_pulsar_server,
)

TEST_TOOL_CONTAINER = "conda/miniconda3"


@integration_test
def test_integration_no_requirement(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None,
    )


@integration_test
def test_integration_maximum_stream_size(integration_test_configuration: IntegrationTestConfiguration):
    integration_test_configuration.set_app_conf_props(
        maximum_stream_size=4
    )
    run_job(
        integration_test_configuration,
        private_token=None,
        maximum_stream_size=4,
    )


@skip_without_drmaa
@integration_test
def test_integration_as_user(external_queue_test_configuration: IntegrationTestConfiguration):
    job_props = {'type': 'queued_external_drmaa', "production": "false"}
    run_job(
        external_queue_test_configuration,
        job_conf_props=job_props,
        private_token=None,
        default_file_action="copy",
        user='u1'
    )


@integration_test
def test_integration_local_setup(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None,
        default_file_action="remote_copy",
        local_setup=True
    )


@skip_unless_module("kombu")
@integration_test
def test_message_queue(external_queue_test_configuration: IntegrationTestConfiguration):
    mq = "memory://test_basicmq_%s" % external_queue_test_configuration.test_suffix
    external_queue_test_configuration.set_app_conf_props(message_queue_url=mq)
    run_job(
        external_queue_test_configuration,
        private_token=None,
        default_file_action="remote_copy",
        local_setup=True,
        manager_url=mq,
    )


@skip_unless_environ("PULSAR_TEST_KEY")
@skip_unless_module("kombu")
@integration_test
def test_integration_scp(external_queue_test_configuration: IntegrationTestConfiguration):
    mq = "memory://test_scp_%s" % external_queue_test_configuration.test_suffix
    external_queue_test_configuration.set_app_conf_props(message_queue_url=mq)
    run_job(
        external_queue_test_configuration,
        private_token=None,
        default_file_action="remote_scp_transfer",
        local_setup=True,
        manager_url=mq,
    )


@skip_unless_environ("PULSAR_TEST_KEY")
@skip_unless_module("kombu")
@integration_test
def test_integration_rsync(external_queue_test_configuration: IntegrationTestConfiguration):
    mq = "memory://test_rsync_%s" % external_queue_test_configuration.test_suffix
    external_queue_test_configuration.set_app_conf_props(message_queue_url=mq)
    run_job(
        external_queue_test_configuration,
        private_token=None,
        default_file_action="remote_rsync_transfer",
        local_setup=True,
        manager_url=mq,
    )


@integration_test
def test_integration_copy(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None,
        default_file_action="copy",
    )


@integration_test
def test_integration_no_transfer(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None,
        default_file_action="none"
    )


@integration_test
def test_integration_cached(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None,
        cache=True,
    )


@integration_test
def test_integration_legacy_galaxy_json(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None,
        legacy_galaxy_json=True,
    )


@integration_test
def test_integration_default(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None
    )


@skip_unless_module("pycurl")
@integration_test
def test_integration_curl(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None,
        transport="curl"
    )


@integration_test
def test_integration_explicit_tool_directory_includes(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        private_token=None,
        explicit_tool_declarations=True
    )


@integration_test
def test_integration_token(integration_test_configuration: IntegrationTestConfiguration):
    integration_test_configuration.set_app_conf_props(private_token="testtoken")
    run_job(
        integration_test_configuration,
        private_token="testtoken"
    )


@integration_test
def test_integration_errors(integration_test_configuration: IntegrationTestConfiguration):
    integration_test_configuration.set_app_conf_props(private_token="testtoken")
    run_job(
        integration_test_configuration,
        private_token="testtoken",
        test_errors=True
    )


@skip_without_drmaa
@integration_test
def test_integration_drmaa(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        job_conf_props={'type': 'queued_drmaa'},
        private_token=None
    )


@skip_unless_executable("condor_submit")
@integration_test
def test_integration_condor(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        job_conf_props={'type': 'queued_condor'},
        private_token=None
    )


@skip_unless_executable("qsub")
@integration_test
def test_integration_cli_torque(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        app_conf={}, job_conf_props={'type': 'queued_cli', 'job_plugin': 'Torque'}, private_token=None)


@skip_unless_executable("sbatch")
@integration_test
def test_integration_cli_slurm(integration_test_configuration: IntegrationTestConfiguration):
    run_job(
        integration_test_configuration,
        job_conf_props={'type': 'queued_cli', 'job_plugin': 'Slurm'},
        private_token=None
    )


# Test and Kubernetes tests without MQ


@integration_test
@mark.test_requires_tes
@skip_unless_environ("FUNNEL_SERVER_TARGET")
def test_tes_polling_integration(external_queue_test_configuration: IntegrationTestConfiguration, tes_funnel_client: TesClient):
    tes_url = tes_funnel_client._url
    # external_queue_test_configuration.set_test_conf_props(test_requirement=False)
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        inject_files_endpoint=True,
        tes_url=tes_url,
        expecting_full_metadata=False,
    )


@integration_test
@mark.test_requires_tes
@skip_unless_environ("FUNNEL_SERVER_TARGET")
def test_coexecution_tes_polling_integration(external_queue_test_configuration: IntegrationTestConfiguration, tes_funnel_client: TesClient):
    # test same as above but pass a container so coexecution occurs
    tes_url = tes_funnel_client._url
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        inject_files_endpoint=True,
        tes_url=tes_url,
        container=TEST_TOOL_CONTAINER,
        expecting_full_metadata=False,
    )


@integration_test
@mark.test_requires_kubernetes
def test_kubernetes_polling_integration(external_queue_test_configuration: IntegrationTestConfiguration):
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        inject_files_endpoint=True,
        k8s_enabled=True,
        expecting_full_metadata=False,
    )


@integration_test
@mark.test_requires_kubernetes
def test_coexecution_kubernetes_polling_integration(external_queue_test_configuration: IntegrationTestConfiguration):
    # test same as above but pass a container so coexecution occurs
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        inject_files_endpoint=True,
        k8s_enabled=True,
        container=TEST_TOOL_CONTAINER,
        expecting_full_metadata=False,
    )


# Test and Kubernetes tests with MQ


# PULSAR_RABBIT_MQ_CONNECTION="amqp://guest:guest@localhost:5672"
@integration_test
@skip_unless_environ("PULSAR_RABBIT_MQ_CONNECTION")
def test_integration_external_rabbit(external_queue_test_configuration: IntegrationTestConfiguration):
    message_queue_url = environ["PULSAR_RABBIT_MQ_CONNECTION"]
    external_queue_test_configuration.set_app_conf_props(message_queue_url=message_queue_url)
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        manager_url=message_queue_url,
        inject_files_endpoint=True,
    )


# PULSAR_RABBIT_MQ_CONNECTION="amqp://guest:guest@localhost:5672"
# PULSAR_TEST_INFRASTRUCTURE_HOST="docker.for.mac.localhost"
# Setup RabbitMQ and expose it on 0.0.0.0 by setting NODE_IP_ADDRESS= to empty string in server conf
@integration_test
@skip_unless_environ("PULSAR_RABBIT_MQ_CONNECTION")
@mark.test_requires_kubernetes
def test_coexecution_integration_kubernetes_mq(external_queue_test_configuration: IntegrationTestConfiguration):
    message_queue_url = environ["PULSAR_RABBIT_MQ_CONNECTION"]
    external_queue_test_configuration.set_app_conf_props(message_queue_url=message_queue_url)
    remote_pulsar_app_config = {
        "message_queue_url": to_infrastructure_uri(message_queue_url),
    }
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        manager_url=message_queue_url,
        inject_files_endpoint=True,
        k8s_enabled=True,
        container=TEST_TOOL_CONTAINER,
        remote_pulsar_app_config=remote_pulsar_app_config,
    )


@integration_test
@skip_unless_environ("PULSAR_RABBIT_MQ_CONNECTION")
@mark.test_requires_kubernetes
def test_integration_kubernetes_mq(external_queue_test_configuration: IntegrationTestConfiguration):
    message_queue_url = environ["PULSAR_RABBIT_MQ_CONNECTION"]
    external_queue_test_configuration.set_app_conf_props(message_queue_url=message_queue_url)
    remote_pulsar_app_config = {
        "message_queue_url": to_infrastructure_uri(message_queue_url),
    }
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        manager_url=message_queue_url,
        inject_files_endpoint=True,
        k8s_enabled=True,
        remote_pulsar_app_config=remote_pulsar_app_config,
    )


# PULSAR_RABBIT_MQ_CONNECTION="amqp://guest:guest@localhost:5672"
# PULSAR_TEST_INFRASTRUCTURE_HOST="docker.for.mac.localhost"
# Setup MQ and expose it on 0.0.0.0 by setting NODE_IP_ADDRESS= to empty string
@integration_test
@skip_unless_environ("PULSAR_RABBIT_MQ_CONNECTION")
@skip_unless_environ("FUNNEL_SERVER_TARGET")
@mark.test_requires_tes
def test_coexecution_integration_tes_mq(external_queue_test_configuration: IntegrationTestConfiguration, tes_funnel_client: TesClient):
    message_queue_url = environ["PULSAR_RABBIT_MQ_CONNECTION"]
    external_queue_test_configuration.set_app_conf_props(message_queue_url=message_queue_url)
    remote_pulsar_app_config = {
        "message_queue_url": to_infrastructure_uri(message_queue_url),
    }
    tes_url = tes_funnel_client._url
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        manager_url=message_queue_url,
        inject_files_endpoint=True,
        tes_url=tes_url,
        container=TEST_TOOL_CONTAINER,
        remote_pulsar_app_config=remote_pulsar_app_config,
    )


@integration_test
@skip_unless_environ("PULSAR_RABBIT_MQ_CONNECTION")
@skip_unless_environ("PULSAR_TES_SERVER_TARGET")
@mark.test_requires_tes
def test_integration_tes_mq(external_queue_test_configuration: IntegrationTestConfiguration, tes_funnel_client: TesClient):
    message_queue_url = environ["PULSAR_RABBIT_MQ_CONNECTION"]
    external_queue_test_configuration.set_app_conf_props(message_queue_url=message_queue_url)
    remote_pulsar_app_config = {
        "message_queue_url": to_infrastructure_uri(message_queue_url),
    }
    tes_url = tes_funnel_client._url
    run_job(
        external_queue_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
        manager_url=message_queue_url,
        inject_files_endpoint=True,
        tes_url=tes_url,
        remote_pulsar_app_config=remote_pulsar_app_config,
    )


@skip_unless_any_module(["pycurl", "poster", "requests_toolbelt"])
@integration_test
def test_integration_remote_transfer(direct_test_configuration: IntegrationTestConfiguration):
    run_job(
        direct_test_configuration,
        private_token=None,
        local_setup=True,
        default_file_action="remote_transfer",
    )


def run_job(test_configuration: IntegrationTestConfiguration, job_conf_props: Optional[Dict[str, str]] = None, **kwds):
    if "suppress_output" not in kwds:
        kwds["suppress_output"] = False

    test_configuration.write_job_conf_props(job_conf_props)
    test_kwds = kwds
    test_kwds.update(test_configuration._test_conf_dict)
    _run_in_app(test_configuration, **test_kwds)


def _run_in_app(test_configuration: IntegrationTestConfiguration, direct_interface: bool = False, inject_files_endpoint: bool = False, **kwds):
    inject_files_endpoint = direct_interface or inject_files_endpoint
    if inject_files_endpoint:
        # Client directory hasn't bee created yet, don't restrict where
        # test files written.
        # Can only run tests using files_server if not constructing a test
        # server for Pulsar - webtest doesn't seem to like having two test
        # servers alive at same time.
        with files_server("/") as test_files_server:
            files_endpoint = to_infrastructure_uri(test_files_server.application_url)
            if direct_interface:
                _run_direct(test_configuration, files_endpoint=files_endpoint, **kwds)
            else:
                _run_in_test_server(test_configuration, files_endpoint=files_endpoint, **kwds)
    else:
        _run_in_test_server(test_configuration, **kwds)


def _run_in_test_server(test_configuration, **kwds):
    with test_pulsar_server(app_conf=test_configuration._app_conf_dict) as server:
        options = Bunch(url=server.application_url, **kwds)
        # TODO: sync Py 2 v 3 approach so following hack is unneeded.
        app = server.test_app
        if hasattr(app, "application"):
            app = app.application
        _update_options_for_app(options, app, **kwds)
        run(options)


def _run_direct(test_configuration, **kwds):
    with test_pulsar_app({}, test_configuration._app_conf_dict, {}) as app:
        options = Bunch(job_manager=next(iter(app.app.managers.values())), file_cache=app.app.file_cache, **kwds)
        _update_options_for_app(options, app.app, **kwds)
        run(options)


def _update_options_for_app(options, app, **kwds):
    if kwds.get("local_setup", False):
        staging_directory = app.staging_directory
        is_coexecution = kwds.get("k8s_enabled") or kwds.get("tes_url")
        if is_coexecution:
            # Update client to not require this - seems silly.
            options["jobs_directory"] = "/pulsar_staging"
        else:
            options["jobs_directory"] = staging_directory


@pytest.fixture(scope="function")
def integration_test_configuration(request, test_configuration: IntegrationTestConfiguration) -> IntegrationTestConfiguration:
    if request.param == "simple":
        return _simple_test_configuration(test_configuration)
    elif request.param == "mq":
        return _external_queue_test_configuration(test_configuration)
    elif request.param == "direct":
        return _direct_test_configuration(test_configuration)
    else:
        raise Exception("Unknown test configuration parameter, should not happen!")


def _direct_test_configuration(test_configuration: IntegrationTestConfiguration) -> IntegrationTestConfiguration:
    test_configuration.set_test_conf_props(
        direct_interface=True,
        test_requirement=False,
    )
    test_configuration._test_suffix = "direct"
    return test_configuration


def _simple_test_configuration(test_configuration: IntegrationTestConfiguration) -> IntegrationTestConfiguration:
    test_configuration.set_test_conf_props(
        direct_interface=False,
        test_requirement=True,
        test_unicode=True,
        test_env=True,
        test_rewrite_action=True,
    )
    test_configuration._test_suffix = "simple"
    return test_configuration


def _external_queue_test_configuration(test_configuration: IntegrationTestConfiguration) -> IntegrationTestConfiguration:
    test_configuration.set_test_conf_props(
        direct_interface=False,
        test_requirement=False,
        test_unicode=True,
        test_env=True,
        test_rewrite_action=True,
    )
    test_configuration._test_suffix = "mq"
    return test_configuration


simple_test_configuration = pytest.fixture(scope="function")(_simple_test_configuration)
external_queue_test_configuration = pytest.fixture(scope="function")(_external_queue_test_configuration)
direct_test_configuration = pytest.fixture(scope="function")(_direct_test_configuration)


@pytest.fixture(scope="function")
def test_configuration(tmp_path: Path) -> IntegrationTestConfiguration:
    return IntegrationTestConfiguration(tmp_path)


tes_funnel_client = pytest.fixture(scope="module")(funnel_client)


def pytest_generate_tests(metafunc):
    if "integration_test_configuration" in metafunc.fixturenames:
        metafunc.parametrize("integration_test_configuration", ["simple", "mq", "direct"], indirect=True)


def to_infrastructure_uri(uri: str) -> str:
    # remap MQ or file server URI hostnames for in-container versions, this is sloppy
    # should actually parse the URI and rebuild with correct host
    infrastructure_host = environ.get("PULSAR_TEST_INFRASTRUCTURE_HOST")
    if infrastructure_host == "_PLATFORM_AUTO_":
        system = platform.system()
        if system in ["Darwin", "Windows"]:
            # assume Docker Desktop is installed and use its domain
            infrastructure_host = "host.docker.internal"
        else:
            # native linux Docker sometimes sets up
            infrastructure_host = "172.17.0.1"

    infrastructure_uri = uri
    if infrastructure_host:
        if "0.0.0.0" in infrastructure_uri:
            infrastructure_uri = infrastructure_uri.replace("0.0.0.0", infrastructure_host)
        elif "localhost" in infrastructure_uri:
            infrastructure_uri = infrastructure_uri.replace("localhost", infrastructure_host)
        elif "127.0.0.1" in infrastructure_uri:
            infrastructure_uri = infrastructure_uri.replace("127.0.0.1", infrastructure_host)
    return infrastructure_uri
