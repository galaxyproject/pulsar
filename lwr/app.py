import atexit
import os

from webob import exc

from lwr.manager_factory import build_managers, DEFAULT_MANAGER_NAME
from lwr.persistence import PersistedJobStore
from lwr.framework import Controller, RoutingApp


def app_factory(global_conf, **local_conf):
    """
    Returns the LWR WSGI application.
    """
    webapp = LwrApp(global_conf=global_conf, **local_conf)
    atexit.register(webapp.shutdown)
    return webapp


class LwrApp(RoutingApp):
    """
    Central application logic for LWR server.
    """
    def add_route_for_function(self, function):
        route_suffix = '/%s' % function.__name__
        # Default or old-style route without explicit manager specified,
        # will be routed to manager '_default_'.
        default_manager_route = route_suffix
        self.add_route(default_manager_route, function)
        # Add route for named manager as well.
        named_manager_route = '/managers/{manager_name}%s' % route_suffix
        self.add_route(named_manager_route, function)

    def __init__(self, **conf):
        RoutingApp.__init__(self)
        self.private_key = None
        self.staging_directory = os.path.abspath(conf['staging_directory'])
        self._setup_private_key(conf.get("private_key", None))
        self.persisted_job_store = PersistedJobStore(**conf)
        self.managers = build_managers(self, conf.get("job_managers_config", None))
        self._setup_routes()

    def shutdown(self):
        for manager in self.managers.values():
            try:
                manager.shutdown()
            except:
                pass

    def _setup_routes(self):
        for func in [setup, clean, launch, check_complete, kill, upload_input,
                     upload_tool_file, upload_config_file, download_output]:
            self.add_route_for_function(func)

    def _setup_private_key(self, private_key):
        if not private_key:
            return
        print "Securing LWR web app with private key, please verify you are using HTTPS so key cannot be obtained by monitoring traffic."
        self.private_key = private_key


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
        manager_name = args.get('manager_name', DEFAULT_MANAGER_NAME)
        args['manager'] = managers[manager_name]


@LwrController(response_type='json')
def setup(manager, job_id):
    manager.setup_job_directory(job_id)
    working_directory = manager.working_directory(job_id)
    outputs_directory = manager.outputs_directory(job_id)
    return {"working_directory": working_directory,
            "outputs_directory": outputs_directory,
            "path_separator": os.sep}


@LwrController()
def clean(manager, job_id):
    manager.clean_job_directory(job_id)


@LwrController()
def launch(manager, job_id, command_line):
    manager.launch(job_id, command_line)


@LwrController(response_type='json')
def check_complete(manager, job_id):
    status = manager.get_status(job_id)
    if status == 'complete':
        return_code = manager.return_code(job_id)
        stdout_contents = manager.stdout_contents(job_id)
        stderr_contents = manager.stderr_contents(job_id)
        return {"complete": "true",
                "status": "status",
                "returncode": return_code,
                "stdout": stdout_contents,
                "stderr": stderr_contents}
    elif status == 'cancelled':
        return {"complete": "true",
                "status": status}
    else:
        return {"complete": "false", "status": status}


@LwrController()
def kill(manager, job_id):
    manager.kill(job_id)


@LwrController(response_type='json')
def upload_tool_file(manager, job_id, name, body):
    return _handle_upload_to_directory(manager.job_directory(job_id), name, body)


@LwrController(response_type='json')
def upload_input(manager, job_id, name, body):
    return _handle_upload_to_directory(manager.inputs_directory(job_id), name, body)


@LwrController(response_type='json')
def upload_config_file(manager, job_id, name, body):
    return _handle_upload_to_directory(manager.working_directory(job_id), name, body)


@LwrController(response_type='file')
def download_output(manager, job_id, name):
    outputs_directory = manager.outputs_directory(job_id)
    path = os.path.join(outputs_directory, name)
    return path


def _handle_upload_to_directory(directory, name, body):
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
    return {"path": path}
