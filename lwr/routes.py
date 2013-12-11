import os
from webob import exc
from simplejson import loads

from lwr.util import get_mapped_file, copy_to_path, copy_to_temp, verify_is_in_directory
from lwr.framework import Controller
from lwr.manager_factory import DEFAULT_MANAGER_NAME

import logging
log = logging.getLogger(__name__)


class LwrController(Controller):

    def __init__(self, **kwargs):
        super(LwrController, self).__init__(**kwargs)

    def _check_access(self, req, environ, start_response):
        if req.app.private_key:
            sent_private_key = req.GET.get("private_key", None)
            if not (req.app.private_key == sent_private_key):
                return exc.HTTPUnauthorized()(environ, start_response)

    def _app_args(self, args, req):
        app = req.app
        managers = app.managers
        manager_name = args.get('manager_name', DEFAULT_MANAGER_NAME)
        app_args = {}
        app_args['manager'] = managers[manager_name]
        app_args['file_cache'] = getattr(app, 'file_cache', None)
        app_args['object_store'] = getattr(app, 'object_store', None)
        return app_args


@LwrController(response_type='json')
def setup(manager, job_id, tool_id=None, tool_version=None):
    job_id = manager.setup_job(job_id, tool_id, tool_version)
    working_directory = manager.working_directory(job_id)
    outputs_directory = manager.outputs_directory(job_id)
    configs_directory = manager.configs_directory(job_id)
    response = {
        "working_directory": working_directory,
        "outputs_directory": outputs_directory,
        "configs_directory": configs_directory,
        "path_separator": os.sep,
        "job_id": job_id,
        "system_properties": manager.system_properties,
    }
    log.debug("Setup job with configuration: %s" % response)
    return response


@LwrController()
def clean(manager, job_id):
    manager.clean(job_id)


@LwrController()
def launch(manager, job_id, command_line, params='{}'):
    submit_params = loads(params)
    manager.launch(job_id, command_line, submit_params)


@LwrController(response_type='json')
def check_complete(manager, job_id):
    status = manager.get_status(job_id)
    if status in ['complete', 'cancelled']:
        return_code = manager.return_code(job_id)
        stdout_contents = manager.stdout_contents(job_id)
        stderr_contents = manager.stderr_contents(job_id)
        response = {
            "complete": "true",
            "status": status,
            "returncode": return_code,
            "stdout": stdout_contents,
            "stderr": stderr_contents,
            "working_directory_contents": manager.working_directory_contents(job_id),
        }
        log.debug("Returning job complete response: %s" % response)
        return response
    else:
        return {"complete": "false", "status": status}


@LwrController()
def kill(manager, job_id):
    manager.kill(job_id)


## Following routes allow older clients to talk to new LWR, should be considered
## deprecated in favor of generic upload_file route.
@LwrController(response_type='json')
def upload_tool_file(manager, file_cache, job_id, name, body, cache_token=None):
    return _handle_upload_to_directory(file_cache, manager.tool_files_directory(job_id), name, body, cache_token=cache_token)


@LwrController(response_type='json')
def upload_input(manager, file_cache, job_id, name, body, cache_token=None):
    return _handle_upload_to_directory(file_cache, manager.inputs_directory(job_id), name, body, cache_token=cache_token)


@LwrController(response_type='json')
def upload_extra_input(manager, file_cache, job_id, name, body, cache_token=None):
    return _handle_upload_to_directory(file_cache, manager.inputs_directory(job_id), name, body, cache_token=cache_token, allow_nested_files=True)


@LwrController(response_type='json')
def upload_config_file(manager, file_cache, job_id, name, body, cache_token=None):
    return _handle_upload_to_directory(file_cache, manager.configs_directory(job_id), name, body, cache_token=cache_token)


@LwrController(response_type='json')
def upload_working_directory_file(manager, file_cache, job_id, name, body, cache_token=None):
    return _handle_upload_to_directory(file_cache, manager.working_directory(job_id), name, body, cache_token=cache_token)


@LwrController(response_type='json')
def upload_file(manager, input_type, file_cache, job_id, name, body, cache_token=None):
    ## Input type should be one of input, input_extra, config, work_dir, or tool.
    directory, allow_nested_files = _input_path_params(manager, input_type, job_id)
    return _handle_upload_to_directory(file_cache, directory, name, body, cache_token=cache_token, allow_nested_files=allow_nested_files)


@LwrController(response_type='json')
def input_path(manager, input_type, job_id, name):
    directory, allow_nested_files = _input_path_params(manager, input_type, job_id)
    return {'path': get_mapped_file(directory, name, allow_nested_files=allow_nested_files)}


@LwrController(response_type='file')
def download_output(manager, job_id, name, output_type="direct"):
    return _output_path(manager, job_id, name, output_type)


@LwrController(response_type='json')
def output_path(manager, job_id, name, output_type="directory"):
    ## Added for non-transfer downloading.
    return {"path": _output_path(manager, job_id, name, output_type)}


def _output_path(manager, job_id, name, output_type):
    """
    """
    directory = manager.outputs_directory(job_id)
    if output_type == "task" or output_type == "work_dir":
        directory = manager.working_directory(job_id)
    path = os.path.join(directory, name)
    verify_is_in_directory(path, directory)
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


@LwrController(response_type='json')
def file_available(file_cache, ip, path):
    return file_cache.file_available(ip, path)


@LwrController(response_type='json')
def cache_required(file_cache, ip, path):
    return file_cache.cache_required(ip, path)


@LwrController(response_type='json')
def cache_insert(file_cache, ip, path, body):
    temp_path = copy_to_temp(body)
    file_cache.cache_file(temp_path, ip, path)


# TODO: coerce booleans and None values into correct types - simplejson may
# do this already but need to check.
@LwrController(response_type='json')
def object_store_exists(object_store, object_id, base_dir=None, dir_only=False, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = LwrDataset(object_id)
    return object_store.exists(obj, base_dir=base_dir, dir_only=dir_only, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@LwrController(response_type='json')
def object_store_file_ready(object_store, object_id, base_dir=None, dir_only=False, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = LwrDataset(object_id)
    return object_store.file_ready(obj, base_dir=base_dir, dir_only=dir_only,
                                   extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root,
                                   alt_name=alt_name)


@LwrController(response_type='json')
def object_store_create(object_store, object_id, base_dir=None, dir_only=False, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = LwrDataset(object_id)
    return object_store.create(obj, base_dir=base_dir, dir_only=dir_only, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@LwrController(response_type='json')
def object_store_empty(object_store, object_id, base_dir=None, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = LwrDataset(object_id)
    return object_store.empty(obj, base_dir=base_dir, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@LwrController(response_type='json')
def object_store_size(object_store, object_id, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = LwrDataset(object_id)
    return object_store.size(obj, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@LwrController(response_type='json')
def object_store_delete(object_store, object_id, entire_dir=False, base_dir=None, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = LwrDataset(object_id)
    return object_store.delete(obj, entire_dir=False, base_dir=None, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@LwrController(response_type='json')
def object_store_get_data(object_store, object_id, start=0, count=-1, base_dir=None, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = LwrDataset(object_id)
    return object_store.get_data(obj, start=int(start), count=int(count), entire_dir=False,
                                 base_dir=None, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root,
                                 alt_name=alt_name)


@LwrController(response_type='json')
def object_store_get_filename(object_store, object_id, base_dir=None, dir_only=False, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = LwrDataset(object_id)
    return object_store.get_filename(obj, base_dir=base_dir, dir_only=dir_only, extra_dir=extra_dir,
                                     extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@LwrController(response_type='json')
def object_store_update_from_file(object_store, object_id, base_dir=None, extra_dir=None, extra_dir_at_root=False,
                                  alt_name=None, file_name=None, create=False):
    obj = LwrDataset(object_id)
    return object_store.update_from_file(obj, base_dir=base_dir, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root,
                                         alt_name=alt_name, file_name=file_name, create=create)


@LwrController(response_type='json')
def object_store_get_store_usage_percent(object_store):
    return object_store.get_store_usage_percent()


class LwrDataset(object):
    """Intermediary between lwr and objectstore."""

    def __init__(self, id):
        self.id = id
        self.object_store_id = None


def _handle_upload_to_directory(file_cache, directory, remote_path, body, cache_token=None, allow_nested_files=False):
    path = get_mapped_file(directory, remote_path, allow_nested_files=allow_nested_files)
    source = body
    if cache_token:
        cached_file = file_cache.destination(cache_token)
        source = open(cached_file, 'rb')
        log.info("Copying cached file %s to %s" % (cached_file, path))
    copy_to_path(source, path)
    return {"path": path}


def _input_path_params(manager, input_type, job_id):
    allow_nested_files = input_type in ['input_extra']
    if input_type in ['input', 'input_extra']:
        directory = manager.inputs_directory(job_id)
    elif input_type == 'config':
        directory = manager.configs_directory(job_id)
    elif input_type == 'tool':
        directory = manager.tool_files_directory(job_id)
    elif input_type == 'work_dir':
        directory = manager.working_directory(job_id)
    else:
        raise Exception("Unknown input_type specified %s" % input_type)
    return directory, allow_nested_files
