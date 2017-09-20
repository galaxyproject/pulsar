import logging
import os

from json import loads

from webob import exc

from pulsar.util import (
    copy_to_path,
    copy_to_temp,
)
from pulsar.client.job_directory import verify_is_in_directory
from pulsar.client.action_mapper import path_type
from pulsar.manager_endpoint_util import (
    setup_job,
    status_dict,
    submit_job,
)
from pulsar.manager_factory import DEFAULT_MANAGER_NAME
from pulsar.web.framework import Controller

log = logging.getLogger(__name__)


class PulsarController(Controller):

    def __init__(self, **kwargs):
        super(PulsarController, self).__init__(**kwargs)

    def _check_access(self, req, environ, start_response):
        if req.app.private_token:
            sent_private_token = req.GET.get("private_token", None)
            if not (req.app.private_token == sent_private_token):
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


@PulsarController(path="/jobs", method="POST", response_type='json')
def setup(manager, job_id, tool_id=None, tool_version=None, use_metadata='false'):
    return __setup(manager, job_id, tool_id=tool_id, tool_version=tool_version, use_metadata=use_metadata)


def __setup(manager, job_id, tool_id, tool_version, use_metadata):
    use_metadata = loads(use_metadata)
    response = setup_job(manager, job_id, tool_id, tool_version, use_metadata)
    log.debug("Setup job with configuration: %s" % response)
    return response


@PulsarController(path="/jobs/{job_id}", method="DELETE")
def clean(manager, job_id):
    manager.clean(job_id)


@PulsarController(path="/jobs/{job_id}/submit", method="POST")
def submit(manager, job_id, command_line, params='{}', dependencies_description='null', setup_params='{}',
           remote_staging='{}', env='[]', submit_extras='{}'):
    submit_params = loads(params)
    setup_params = loads(setup_params)
    dependencies_description = loads(dependencies_description)
    env = loads(env)
    remote_staging = loads(remote_staging)
    submit_extras = loads(submit_extras)
    submit_config = dict(
        job_id=job_id,
        command_line=command_line,
        setup_params=setup_params,
        submit_params=submit_params,
        dependencies_description=dependencies_description,
        env=env,
        remote_staging=remote_staging,
    )
    submit_config.update(submit_extras)
    submit_job(manager, submit_config)


@PulsarController(path="/jobs/{job_id}/status", response_type='json')
def status(manager, job_id):
    return status_dict(manager, job_id)


@PulsarController(path="/jobs/{job_id}/cancel", method="PUT")
def cancel(manager, job_id):
    manager.kill(job_id)


@PulsarController(path="/jobs/{job_id}/files", method="POST", response_type='json')
def upload_file(manager, type, file_cache, job_id, name, body, cache_token=None):
    # Input type should be one of input, config, workdir, metadata, tool, or unstructured (see action_mapper.path_type)
    path = manager.job_directory(job_id).calculate_path(name, type)
    return _handle_upload(file_cache, path, body, cache_token=cache_token)


@PulsarController(path="/jobs/{job_id}/files/path", method="GET", response_type='json')
def path(manager, type, job_id, name):
    if type in [path_type.OUTPUT, path_type.OUTPUT_WORKDIR, path_type.OUTPUT_METADATA]:
        path = _output_path(manager, job_id, name, type)
    else:
        path = manager.job_directory(job_id).calculate_path(name, type)
    return {'path': path}


@PulsarController(path="/jobs/{job_id}/files", method="GET", response_type='file')
def download_output(manager, job_id, name, type=path_type.OUTPUT):
    return _output_path(manager, job_id, name, type)


def output_path(manager, job_id, name, type=path_type.OUTPUT):
    # output_type should be one of...
    #   work_dir, direct
    # Added for non-transfer downloading.
    return {"path": _output_path(manager, job_id, name, type)}


def _output_path(manager, job_id, name, output_type):
    """
    """
    directory = manager.job_directory(job_id).outputs_directory()
    if output_type == path_type.OUTPUT_WORKDIR:  # action_mapper.path_type.OUTPUT_WORKDIR
        directory = manager.job_directory(job_id).working_directory()
    elif output_type == path_type.OUTPUT_METADATA:
        directory = manager.job_directory(job_id).metadata_directory()
    path = os.path.join(directory, name)
    verify_is_in_directory(path, directory)
    return path


@PulsarController(path="/cache/status", method="GET", response_type='json')
def file_available(file_cache, ip, path):
    """ Returns {token: <token>, ready: <bool>}
    """
    return file_cache.file_available(ip, path)


@PulsarController(path="/cache", method="PUT", response_type='json')
def cache_required(file_cache, ip, path):
    """ Returns bool indicating whether this client should
    execute cache_insert. Either way client should be follow up
    with file_available.
    """
    return file_cache.cache_required(ip, path)


@PulsarController(path="/cache", method="POST", response_type='json')
def cache_insert(file_cache, ip, path, body):
    temp_path = copy_to_temp(body)
    file_cache.cache_file(temp_path, ip, path)


# TODO: coerce booleans and None values into correct types - simplejson may
# do this already but need to check.
@PulsarController(path="/objects/{object_id}/exists", response_type='json')
def object_store_exists(object_store, object_id, base_dir=None, dir_only=False, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = PulsarDataset(object_id)
    return object_store.exists(obj, base_dir=base_dir, dir_only=dir_only, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@PulsarController(path="/objects/{object_id}/file_ready", response_type='json')
def object_store_file_ready(object_store, object_id, base_dir=None, dir_only=False, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = PulsarDataset(object_id)
    return object_store.file_ready(obj, base_dir=base_dir, dir_only=dir_only,
                                   extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root,
                                   alt_name=alt_name)


@PulsarController(path="/objects/{object_id}", method="POST", response_type='json')
def object_store_create(object_store, object_id, base_dir=None, dir_only=False, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = PulsarDataset(object_id)
    return object_store.create(obj, base_dir=base_dir, dir_only=dir_only, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@PulsarController(path="/objects/{object_id}/empty", response_type='json')
def object_store_empty(object_store, object_id, base_dir=None, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = PulsarDataset(object_id)
    return object_store.empty(obj, base_dir=base_dir, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@PulsarController(path="/objects/{object_id}/size", response_type='json')
def object_store_size(object_store, object_id, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = PulsarDataset(object_id)
    return object_store.size(obj, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@PulsarController(path="/objects/{object_id}", method="DELETE", response_type='json')
def object_store_delete(object_store, object_id, entire_dir=False, base_dir=None, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = PulsarDataset(object_id)
    return object_store.delete(obj, entire_dir=False, base_dir=None, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@PulsarController(path="/objects/{object_id}", method="GET", response_type='json')
def object_store_get_data(object_store, object_id, start=0, count=-1, base_dir=None, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = PulsarDataset(object_id)
    return object_store.get_data(obj, start=int(start), count=int(count), entire_dir=False,
                                 base_dir=None, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root,
                                 alt_name=alt_name)


@PulsarController(path="/objects/{object_id}/filename", response_type='json')
def object_store_get_filename(object_store, object_id, base_dir=None, dir_only=False, extra_dir=None, extra_dir_at_root=False, alt_name=None):
    obj = PulsarDataset(object_id)
    return object_store.get_filename(obj, base_dir=base_dir, dir_only=dir_only, extra_dir=extra_dir,
                                     extra_dir_at_root=extra_dir_at_root, alt_name=alt_name)


@PulsarController(path="/objects/{object_id}", method="PUT", response_type='json')
def object_store_update_from_file(object_store, object_id, base_dir=None, extra_dir=None, extra_dir_at_root=False,
                                  alt_name=None, file_name=None, create=False):
    obj = PulsarDataset(object_id)
    return object_store.update_from_file(obj, base_dir=base_dir, extra_dir=extra_dir, extra_dir_at_root=extra_dir_at_root,
                                         alt_name=alt_name, file_name=file_name, create=create)


@PulsarController(path="/object_store_usage_percent", response_type='json')
def object_store_get_store_usage_percent(object_store):
    return object_store.get_store_usage_percent()


class PulsarDataset(object):
    """Intermediary between Pulsar and objectstore."""

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
