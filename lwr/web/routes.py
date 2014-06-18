import os
from webob import exc
from json import loads

from galaxy.util import (
    copy_to_path,
    copy_to_temp,
)
from lwr.lwr_client.job_directory import verify_is_in_directory
from lwr.web.framework import Controller
from lwr.manager_factory import DEFAULT_MANAGER_NAME
from lwr.manager_endpoint_util import (
    submit_job,
    setup_job,
    full_status,
)

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
    return __setup(manager, job_id, tool_id=tool_id, tool_version=tool_version)


def __setup(manager, job_id, tool_id, tool_version):
    response = setup_job(manager, job_id, tool_id, tool_version)
    log.debug("Setup job with configuration: %s" % response)
    return response


@LwrController()
def clean(manager, job_id):
    manager.clean(job_id)


@LwrController()
def launch(manager, job_id, command_line, params='{}', dependencies_description='null', setup_params='{}', remote_staging='[]', env='[]'):
    submit_params = loads(params)
    setup_params = loads(setup_params)
    dependencies_description = loads(dependencies_description)
    env = loads(env)
    remote_staging = loads(remote_staging)
    submit_config = dict(
        job_id=job_id,
        command_line=command_line,
        setup_params=setup_params,
        submit_params=submit_params,
        dependencies_description=dependencies_description,
        env=env,
        remote_staging=remote_staging
    )
    submit_job(manager, submit_config)


@LwrController(response_type='json')
def check_complete(manager, job_id):
    status = manager.get_status(job_id)
    return full_status(manager, status, job_id)


@LwrController()
def kill(manager, job_id):
    manager.kill(job_id)


# Following routes allow older clients to talk to new LWR, should be considered
# deprecated in favor of generic upload_file route.
@LwrController(response_type='json')
def upload_tool_file(manager, file_cache, job_id, name, body, cache_token=None):
    path = manager.job_directory(job_id).calculate_path(name, 'tool')
    return _handle_upload(
        file_cache,
        path,
        body,
        cache_token=cache_token
    )


@LwrController(response_type='json')
def upload_input(manager, file_cache, job_id, name, body, cache_token=None):
    path = manager.job_directory(job_id).calculate_path(name, 'input')
    return _handle_upload(
        file_cache,
        path,
        body,
        cache_token=cache_token
    )


@LwrController(response_type='json')
def upload_extra_input(manager, file_cache, job_id, name, body, cache_token=None):
    path = manager.job_directory(job_id).calculate_path(name, 'input')
    return _handle_upload(
        file_cache,
        path,
        body,
        cache_token=cache_token
    )


@LwrController(response_type='json')
def upload_config_file(manager, file_cache, job_id, name, body, cache_token=None):
    path = manager.job_directory(job_id).calculate_path(name, 'config')
    return _handle_upload(
        file_cache,
        path,
        body,
        cache_token=cache_token,
    )


@LwrController(response_type='json')
def upload_working_directory_file(manager, file_cache, job_id, name, body, cache_token=None):
    path = manager.job_directory(job_id).calculate_path(name, 'workdir')
    return _handle_upload(
        file_cache,
        path,
        body,
        cache_token=cache_token,
    )


@LwrController(response_type='json')
def upload_unstructured_file(manager, file_cache, job_id, name, body, cache_token=None):
    path = manager.job_directory(job_id).calculate_path(name, 'unstructured')
    return _handle_upload(
        file_cache,
        path,
        body,
        cache_token=cache_token,
    )


@LwrController(response_type='json')
def upload_file(manager, input_type, file_cache, job_id, name, body, cache_token=None):
    # Input type should be one of input, config, workdir, tool, or unstructured.
    path = manager.job_directory(job_id).calculate_path(name, input_type)
    return _handle_upload(file_cache, path, body, cache_token=cache_token)


@LwrController(response_type='json')
def input_path(manager, input_type, job_id, name):
    path = manager.job_directory(job_id).calculate_path(name, input_type)
    return {'path': path}


@LwrController(response_type='file')
def download_output(manager, job_id, name, output_type="direct"):
    return _output_path(manager, job_id, name, output_type)


@LwrController(response_type='json')
def output_path(manager, job_id, name, output_type="direct"):
    # output_type should be one of...
    #   work_dir, direct
    # Added for non-transfer downloading.
    return {"path": _output_path(manager, job_id, name, output_type)}


def _output_path(manager, job_id, name, output_type):
    """
    """
    directory = manager.job_directory(job_id).outputs_directory()
    if output_type == "task" or output_type == "work_dir":
        directory = manager.job_directory(job_id).working_directory()
    path = os.path.join(directory, name)
    verify_is_in_directory(path, directory)
    return path


@LwrController(response_type='json')
def file_available(file_cache, ip, path):
    """ Returns {token: <token>, ready: <bool>}
    """
    return file_cache.file_available(ip, path)


@LwrController(response_type='json')
def cache_required(file_cache, ip, path):
    """ Returns bool indicating whether this client should
    execute cache_insert. Either way client should be follow up
    with file_available.
    """
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


def _handle_upload(file_cache, path, body, cache_token=None):
    source = body
    if cache_token:
        cached_file = file_cache.destination(cache_token)
        source = open(cached_file, 'rb')
        log.info("Copying cached file %s to %s" % (cached_file, path))
    copy_to_path(source, path)
    return {"path": path}
