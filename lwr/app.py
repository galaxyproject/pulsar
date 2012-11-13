from lwr.manager import Manager
from lwr.routing import *

import os

@Controller(response_type='json')
def setup(manager, job_id):
    manager.setup_job_directory(job_id)
    working_directory = manager.working_directory(job_id)
    outputs_directory = manager.outputs_directory(job_id)
    return {"working_directory" : working_directory, 
            "outputs_directory" : outputs_directory,
            "path_separator" : os.sep}

@Controller()
def clean(manager, job_id):
    manager.clean_job_directory(job_id)

@Controller()
def launch(manager, job_id, command_line):
    manager.launch(job_id, command_line)

@Controller(response_type='json')
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

@Controller()
def kill(manager, job_id):
    manager.kill(job_id)

@Controller(response_type='json')
def upload_tool_file(manager, job_id, name, body):
    return handle_upload_to_directory(manager.job_directory(job_id), name, body)

@Controller(response_type='json')
def upload_input(manager, job_id, name, body):
    return handle_upload_to_directory(manager.inputs_directory(job_id), name, body)

@Controller(response_type='json')
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

@Controller(response_type='file')
def download_output(manager, job_id, name):
    outputs_directory = manager.outputs_directory(job_id)
    path = os.path.join(outputs_directory, name)
    return path

class App(RoutingApp):
    """
    """
    def add_route_for_function(self, function):
        route_base = '/%s' % function.__name__
        self.add_route(route_base, function, manager=self.manager)
        #queued_route = '/queue/{queue}%s' % route_base
        #self.add_route(queued_route, function, manager=self.manager)

    def __init__(self, **conf):
        RoutingApp.__init__(self)
        self.private_key = None
        if "private_key" in conf:
            self._setup_private_key(conf["private_key"])
	self.manager = Manager(os.path.abspath(conf['staging_directory']))
        self.add_route_for_function(setup)
        self.add_route_for_function(clean)
        self.add_route_for_function(launch)
        self.add_route_for_function(check_complete)
        self.add_route_for_function(kill)
        self.add_route_for_function(upload_input)
        self.add_route_for_function(upload_tool_file)
        self.add_route_for_function(upload_config_file)
        self.add_route_for_function(download_output)

    def _setup_private_key(self, private_key):
        print "Securing LWR web app with private key, please verify you are using HTTPS so key cannot be obtained by monitoring traffic."
        self.private_key = private_key



def app_factory( global_conf, **local_conf ):
    """
    Returns the lwr wsgi application.
    """
    webapp = App(global_conf = global_conf, **local_conf)
    return webapp
