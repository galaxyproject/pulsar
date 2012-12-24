import os
from webob import exc
from lwr.util import get_mapped_file, copy_to_path
from lwr.framework import Controller
from lwr.manager_factory import DEFAULT_MANAGER_NAME


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
def upload_extra_input(manager, job_id, name, body):
    return _handle_upload_to_directory(manager.inputs_directory(job_id), name, body, allow_nested_files=True)


@LwrController(response_type='json')
def upload_config_file(manager, job_id, name, body):
    return _handle_upload_to_directory(manager.working_directory(job_id), name, body)


@LwrController(response_type='json')
def upload_working_directory_file(manager, job_id, name, body):
    return _handle_upload_to_directory(manager.working_directory(job_id), name, body)


@LwrController(response_type='file')
def download_output(manager, job_id, name, output_type="direct"):
    directory = manager.outputs_directory(job_id)
    if output_type == "task" or output_type == "work_dir":
        directory = manager.working_directory(job_id)
    path = os.path.join(directory, name)
    return path


@LwrController(response_type='json')
def get_output_type(manager, job_id, name):
    outputs_directory = manager.outputs_directory(job_id)
    working_directory = manager.working_directory(job_id)
    if os.path.exists(os.path.join(outputs_directory, name)):
        return "direct"
    elif os.path.exists(os.path.join(working_directory, name)):
        return "task"
    else:
        return "none"


def _handle_upload_to_directory(directory, remote_path, body, allow_nested_files=False):
    path = get_mapped_file(directory, remote_path, allow_nested_files=allow_nested_files)
    copy_to_path(body, path)
    return {"path": path}
