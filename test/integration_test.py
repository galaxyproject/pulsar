from __future__ import print_function
from os.path import join
from os import environ, makedirs, system
from six import next, itervalues
from six.moves import configparser
from .test_utils import (
    TempDirectoryTestCase,
    skip_unless_executable,
    skip_unless_module,
    skip_unless_any_module,
    skip_unless_environ,
    skip_without_drmaa,
)

from .test_utils import integration_test
from .test_utils import test_pulsar_app
from .test_utils import test_pulsar_server
from .test_utils import files_server

from galaxy.util.bunch import Bunch
from pulsar.client.test.check import run


class BaseIntegrationTest(TempDirectoryTestCase):

    def _run(self, app_conf={}, job_conf_props={}, **kwds):
        app_conf = app_conf.copy()
        job_conf_props = job_conf_props.copy()

        if "suppress_output" not in kwds:
            kwds["suppress_output"] = False

        self.__setup_job_properties(app_conf, job_conf_props)
        self.__setup_dependencies(app_conf)
        self._run_in_app(app_conf, **kwds)

    def _run_in_app(self, app_conf, **kwds):
        direct_interface = kwds.get("direct_interface", None)
        inject_files_endpoint = direct_interface or kwds.get("inject_files_endpoint", False)
        if inject_files_endpoint:
            # Client directory hasn't bee created yet, don't restrict where
            # test files written.
            # Can only run tests using files_server if not constructing a test
            # server for Pulsar - webtest doesn't seem to like having two test
            # servers alive at same time.
            with files_server("/") as test_files_server:
                files_endpoint = to_infrastructure_uri(test_files_server.application_url)
                if direct_interface:
                    self._run_direct(app_conf, files_endpoint=files_endpoint, **kwds)
                else:
                    self._run_in_test_server(app_conf, files_endpoint=files_endpoint, **kwds)
        else:
            self._run_in_test_server(app_conf, **kwds)

    def _run_in_test_server(self, app_conf, **kwds):
        with test_pulsar_server(app_conf=app_conf) as server:
            options = Bunch(url=server.application_url, **kwds)
            # TODO: sync Py 2 v 3 approach so following hack is unneeded.
            app = server.test_app
            if hasattr(app, "application"):
                app = app.application
            self._update_options_for_app(options, app, **kwds)
            run(options)

    def _run_direct(self, app_conf, **kwds):
        with test_pulsar_app({}, app_conf, {}) as app:
            options = Bunch(job_manager=next(itervalues(app.app.managers)), file_cache=app.app.file_cache, **kwds)
            self._update_options_for_app(options, app.app, **kwds)
            run(options)

    def _update_options_for_app(self, options, app, **kwds):
        if kwds.get("local_setup", False):
            staging_directory = app.staging_directory
            if kwds.get("k8s_enabled"):
                options["jobs_directory"] = "/pulsar_staging"
            else:
                options["jobs_directory"] = staging_directory

    def __setup_job_properties(self, app_conf, job_conf_props):
        if job_conf_props:
            job_conf = join(self.temp_directory, "job_managers.ini")
            config = configparser.ConfigParser()
            section_name = "manager:_default_"
            config.add_section(section_name)
            for key, value in job_conf_props.items():
                config.set(section_name, key, value)
            with open(job_conf, "w") as configf:
                config.write(configf)

            app_conf["job_managers_config"] = job_conf

    def __setup_dependencies(self, app_conf):
        dependencies_dir = join(self.temp_directory, "dependencies")
        dep1_directory = join(dependencies_dir, "dep1", "1.1")
        makedirs(dep1_directory)
        try:
            # Let external users read/execute this directory for run as user
            # test.
            system("chmod 755 %s" % self.temp_directory)
            system("chmod -R 755 %s" % dependencies_dir)
        except Exception as e:
            print(e)
        env_file = join(dep1_directory, "env.sh")
        with open(env_file, "w") as env:
            env.write("MOO=moo_override; export MOO")
        app_conf["tool_dependency_dir"] = dependencies_dir


class IntegrationTests(BaseIntegrationTest):
    default_kwargs = dict(direct_interface=False, test_requirement=True, test_unicode=True, test_env=True, test_rewrite_action=True)

    @integration_test
    def test_integration_no_requirement(self):
        self._run(private_token=None, **self.default_kwargs)

    @integration_test
    def test_integration_maximum_stream_size(self):
        app_conf = dict(maximum_stream_size=4)
        self._run(app_conf=app_conf, private_token=None, maximum_stream_size=4, **self.default_kwargs)

    @skip_without_drmaa
    @integration_test
    def test_integration_as_user(self):
        job_props = {'type': 'queued_external_drmaa', "production": "false"}
        self._run(job_conf_props=job_props, private_token=None, default_file_action="copy", user='u1', **self.default_kwargs)

    @integration_test
    def test_integration_local_setup(self):
        self._run(private_token=None, default_file_action="remote_copy", local_setup=True, **self.default_kwargs)

    @skip_unless_module("pycurl")
    @skip_unless_module("kombu")
    @integration_test
    def test_message_queue(self):
        self._run(
            app_conf=dict(message_queue_url="memory://test1"),
            private_token=None,
            default_file_action="remote_copy",
            local_setup=True,
            manager_url="memory://test1",
            **self.default_kwargs
        )

    @skip_unless_environ("PULSAR_TEST_KEY")
    @skip_unless_module("kombu")
    @integration_test
    def test_integration_scp(self):
        self._run(
            app_conf=dict(message_queue_url="memory://test2"),
            private_token=None,
            default_file_action="remote_scp_transfer",
            local_setup=True,
            manager_url="memory://test2",
            **self.default_kwargs
        )

    @skip_unless_environ("PULSAR_TEST_KEY")
    @skip_unless_module("kombu")
    @integration_test
    def test_integration_rsync(self):
        self._run(
            app_conf=dict(message_queue_url="memory://test3"),
            private_token=None,
            default_file_action="remote_rsync_transfer",
            local_setup=True,
            manager_url="memory://test3",
            **self.default_kwargs
        )

    @integration_test
    def test_integration_copy(self):
        self._run(private_token=None, default_file_action="copy", **self.default_kwargs)

    @integration_test
    def test_integration_no_transfer(self):
        self._run(private_token=None, default_file_action="none", **self.default_kwargs)

    @integration_test
    def test_integration_cached(self):
        self._run(private_token=None, cache=True, **self.default_kwargs)

    @integration_test
    def test_integration_default(self):
        self._run(private_token=None, **self.default_kwargs)

    @skip_unless_module("pycurl")
    @integration_test
    def test_integration_curl(self):
        self._run(private_token=None, transport="curl", **self.default_kwargs)

    @integration_test
    def test_integration_token(self):
        self._run(app_conf={"private_token": "testtoken"}, private_token="testtoken", **self.default_kwargs)

    @integration_test
    def test_integration_errors(self):
        self._run(app_conf={"private_token": "testtoken"}, private_token="testtoken", test_errors=True, **self.default_kwargs)

    @skip_without_drmaa
    @integration_test
    def test_integration_drmaa(self):
        self._run(app_conf={}, job_conf_props={'type': 'queued_drmaa'}, private_token=None, **self.default_kwargs)

    @skip_unless_executable("condor_submit")
    @integration_test
    def test_integration_condor(self):
        self._run(app_conf={}, job_conf_props={'type': 'queued_condor'}, private_token=None, **self.default_kwargs)

    @skip_unless_executable("qsub")
    @integration_test
    def test_integration_cli_torque(self):
        self._run(app_conf={}, job_conf_props={'type': 'queued_cli', 'job_plugin': 'Torque'}, private_token=None, **self.default_kwargs)

    @skip_unless_executable("sbatch")
    @integration_test
    def test_integration_cli_slurm(self):
        self._run(app_conf={}, job_conf_props={'type': 'queued_cli', 'job_plugin': 'Slurm'}, private_token=None, **self.default_kwargs)


class ExternalQueueIntegrationTests(IntegrationTests):
    default_kwargs = dict(direct_interface=False, test_requirement=False, test_unicode=True, test_env=True, test_rewrite_action=True)

    @integration_test
    @skip_unless_environ("PULSAR_RABBIT_MQ_CONNECTION")
    def test_integration_external_rabbit(self):
        # e.g. amqp://guest:guest@localhost:5672//
        # TODO: nc docker.for.mac.localhost 5679
        message_queue_url = environ.get("PULSAR_RABBIT_MQ_CONNECTION")
        self._run(
            app_conf=dict(message_queue_url=message_queue_url),
            private_token=None,
            local_setup=True,
            default_file_action="remote_transfer",
            manager_url=message_queue_url,
            inject_files_endpoint=True,
            **self.default_kwargs
        )

    @integration_test
    @skip_unless_environ("PULSAR_RABBIT_MQ_CONNECTION")
    def test_integration_kubernetes(self):
        message_queue_url = environ.get("PULSAR_RABBIT_MQ_CONNECTION")
        remote_pulsar_app_config = {
            "staging_directory": "/pulsar_staging/",
            "message_queue_url": to_infrastructure_uri(message_queue_url),
            "manager": {
                "type": "coexecution",
            }
        }
        self._run(
            app_conf=dict(message_queue_url=message_queue_url),
            private_token=None,
            local_setup=True,
            default_file_action="remote_transfer",
            manager_url=message_queue_url,
            inject_files_endpoint=True,
            k8s_enabled=True,
            container="conda/miniconda2",
            remote_pulsar_app_config=remote_pulsar_app_config,
            **self.default_kwargs
        )


class DirectIntegrationTests(IntegrationTests):
    default_kwargs = dict(direct_interface=True, test_requirement=False)

    @skip_unless_any_module(["pycurl", "poster", "requests_toolbelt"])
    @integration_test
    def test_integration_remote_transfer(self):
        self._run(
            private_token=None,
            local_setup=True,
            default_file_action="remote_transfer",
            **self.default_kwargs
        )


def to_infrastructure_uri(uri):
    # remap MQ or file server URI hostnames for in-container versions, this is sloppy
    # should actually parse the URI and rebuild with correct host
    infrastructure_host = environ.get("PULSAR_TEST_INFRASTRUCTURE_HOST")
    infrastructure_uri = uri
    if infrastructure_host:
        if "0.0.0.0" in infrastructure_uri:
            infrastructure_uri = infrastructure_uri.replace("0.0.0.0", infrastructure_host)
        elif "localhost" in infrastructure_uri:
            infrastructure_uri = infrastructure_uri.replace("localhost", infrastructure_host)
        elif "127.0.0.1" in infrastructure_uri:
            infrastructure_uri = infrastructure_uri.replace("127.0.0.1", infrastructure_host)
    return infrastructure_uri
