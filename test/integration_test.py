from os.path import join
from .test_utils import TempDirectoryTestCase

from lwr.util import Bunch
from .check import run
try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser


class IntegrationTest(TempDirectoryTestCase):

    def test_integration_as_user(self):
        self.__run(job_conf_props={'type': 'queued_external_drmaa', "production": "false"}, private_token=None, default_file_action="copy", user='u1')

    def test_integration_copy(self):
        self.__run(private_token=None, default_file_action="copy")

    def test_integration_no_transfer(self):
        self.__run(private_token=None, default_file_action="none")

    def test_integration_cached(self):
        self.__run(private_token=None, cache=True)

    def test_integration_default(self):
        self.__run(private_token=None)

    def test_integration_curl(self):
        self.__run(private_token=None, transport="curl")

    def test_integration_token(self):
        self.__run(app_conf={"private_key": "testtoken"}, private_token="testtoken", transport="curl")

    def test_integration_errors(self):
        self.__run(app_conf={"private_key": "testtoken"}, private_token="testtoken", transport="curl", test_errors=True)

    def test_integration_drmaa(self):
        self.__run(app_conf={}, job_conf_props={'type': 'queued_drmaa'}, private_token=None)

    def test_integration_condor(self):
        self.__run(app_conf={}, job_conf_props={'type': 'queued_condor'}, private_token=None)

    def test_integration_cli(self):
        self.__run(app_conf={}, job_conf_props={'type': 'queued_cli', 'job_plugin': 'Torque'}, private_token=None)

    def __run(self, app_conf={}, job_conf_props={}, **kwds):
        kwds["suppress_output"] = True
        if job_conf_props:
            job_conf = join(self.temp_directory, "job_managers.ini")
            config = ConfigParser()
            section_name = "manager:_default_"
            config.add_section(section_name)
            for key, value in job_conf_props.iteritems():
                config.set(section_name, key, value)
            with open(job_conf, "wb") as configf:
                config.write(configf)

            app_conf["job_managers_config"] = job_conf

        from .test_utils import test_server
        with test_server(app_conf=app_conf) as server:
            options = Bunch(url=server.application_url, **kwds)
            run(options)
