from lwr.manager import Manager
from lwr.routing import *

from ConfigParser import ConfigParser
import os

class LwrController(Controller):

    def __init__(self, **kwargs):
        super(LwrController, self).__init__(**kwargs)

    def _check_access(self, req, environ, start_response):
        if req.app.private_key:
            sent_private_key = req.GET.get("private_key", None)
            if not (req.app.private_key == sent_private_key):
                return exc.HTTPUnauthorized()(environ, start_response)

    def _prepare_controller_args(self, req, args):
        managers = req.app.managers
        manager_name = args.get('manager_name', '_default_')
        args['manager'] = managers[manager_name]

@LwrController(response_type='json')
def setup(manager, job_id):
    manager.setup_job_directory(job_id)
    working_directory = manager.working_directory(job_id)
    outputs_directory = manager.outputs_directory(job_id)
    return { "working_directory" : working_directory, 
             "outputs_directory" : outputs_directory,
             "path_separator" : os.sep }

@LwrController()
def clean(manager, job_id):
    manager.clean_job_directory(job_id)

@LwrController()
def launch(manager, job_id, command_line):
    manager.launch(job_id, command_line)

@LwrController(response_type='json')
def check_complete(manager, job_id):
    if manager.check_complete(job_id):
        return_code = manager.return_code(job_id)
        stdout_contents = manager.stdout_contents(job_id)
        stderr_contents = manager.stderr_contents(job_id)
        return {"complete" : "true", 
                "returncode" : return_code, 
                "stdout" : stdout_contents, 
                "stderr" : stderr_contents}
    else:
        return {"complete" : "false"}

@LwrController()
def kill(manager, job_id):
    manager.kill(job_id)

@LwrController(response_type='json')
def upload_tool_file(manager, job_id, name, body):
    return handle_upload_to_directory(manager.job_directory(job_id), name, body)

@LwrController(response_type='json')
def upload_input(manager, job_id, name, body):
    return handle_upload_to_directory(manager.inputs_directory(job_id), name, body)

@LwrController(response_type='json')
def upload_config_file(manager, job_id, name, body):
    return handle_upload_to_directory(manager.working_directory(job_id), name, body)

def handle_upload_to_directory(directory, name, body):
    name = os.path.basename(name)
    path = os.path.join(directory, name)
    output = open(path, 'wb')
    try:
        while True:
            buffer = body.read(1024)
            if buffer == "":
                break
            output.write(buffer)
    finally:
        output.close()
    return {"path" : path}

@LwrController(response_type='file')
def download_output(manager, job_id, name):
    outputs_directory = manager.outputs_directory(job_id)
    path = os.path.join(outputs_directory, name)
    return path



class App(RoutingApp):
    """
    """
    def add_route_for_function(self, function):
        route_base = '/%s' % function.__name__
        self.add_route(route_base, function)
        named_manager_route = '/managers/{manager_name}%s' % route_base
        self.add_route(named_manager_route, function)

    def __init__(self, **conf):
        RoutingApp.__init__(self)
        self.private_key = None
        self.staging_directory = os.path.abspath(conf['staging_directory'])
        if "private_key" in conf:
            self._setup_private_key(conf["private_key"])
        self._init_managers(conf.get("job_managers_config", None))
        for func in [setup, clean, launch, check_complete, kill, upload_input, 
                     upload_tool_file, upload_config_file, download_output]:
            self.add_route_for_function(func)

    def _init_managers(self, config_file):
        self.managers = {}
        if not config_file:
            self.managers['_default_'] = Manager(self.staging_directory)
        else:
            config = ConfigParser()
            config.readfp(open(config_file))
            for section in config.sections():
                if not section.startswith('manager:'):
                    continue
                self.managers[section[len('manager:'):]] = self._parse_manager(config, section)

    def _parse_manager(self, config, section):
        return Manager(self.staging_directory)

    def _setup_private_key(self, private_key):
        print "Securing LWR web app with private key, please verify you are using HTTPS so key cannot be obtained by monitoring traffic."
        self.private_key = private_key


def app_factory( global_conf, **local_conf ):
    """
    Returns the lwr wsgi application.
    """
    webapp = App(global_conf = global_conf, **local_conf)
    return webapp
