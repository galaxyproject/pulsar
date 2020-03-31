import logging
import os

from six import string_types

from pulsar.managers.util.pykube_util import (
    ensure_pykube,
    find_job_object_by_name,
    galaxy_instance_id,
    Job,
    job_object_dict,
    produce_unique_k8s_job_name,
    pull_policy,
    pykube_client_from_dict,
    stop_job,
)
from .action_mapper import (
    actions,
    path_type,
)
from .decorators import parseJson
from .decorators import retry
from .destination import submit_params
from .job_directory import RemoteJobDirectory
from .setup_handler import build as build_setup_handler
from .util import copy
from .util import ensure_directory
from .util import json_dumps
from .util import json_loads
from .util import to_base64_json

log = logging.getLogger(__name__)

CACHE_WAIT_SECONDS = 3
TOOL_EXECUTION_CONTAINER_COMMAND_TEMPLATE = """
path='%s/command_line';
while [ ! -e $path ];
    do sleep 1; echo "waiting for job script $path";
done;
echo 'running script';
sh $path;
echo 'ran script'"""


class OutputNotFoundException(Exception):

    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "No remote output found for path %s" % self.path


class BaseJobClient(object):

    def __init__(self, destination_params, job_id):
        destination_params = destination_params or {}
        self.destination_params = destination_params
        self.assign_job_id(job_id)

        for attr in ["ssh_key", "ssh_user", "ssh_host", "ssh_port"]:
            setattr(self, attr, destination_params.get(attr, None))
        self.env = destination_params.get("env", [])
        self.files_endpoint = destination_params.get("files_endpoint", None)

        default_file_action = self.destination_params.get("default_file_action", "transfer")
        if default_file_action not in actions:
            raise Exception("Unknown Pulsar default file action type %s" % default_file_action)
        self.default_file_action = default_file_action
        self.action_config_path = self.destination_params.get("file_action_config", None)

        self.setup_handler = build_setup_handler(self, destination_params)

    def assign_job_id(self, job_id):
        self.job_id = job_id
        self._set_job_directory()

    def _set_job_directory(self):
        if "jobs_directory" in self.destination_params:
            staging_directory = self.destination_params["jobs_directory"]
            sep = self.destination_params.get("remote_sep", os.sep)
            job_directory = RemoteJobDirectory(
                remote_staging_directory=staging_directory,
                remote_id=self.job_id,
                remote_sep=sep,
            )
        else:
            job_directory = None
        self.job_directory = job_directory

    def setup(self, tool_id=None, tool_version=None, preserve_galaxy_python_environment=None):
        """
        Setup remote Pulsar server to run this job.
        """
        setup_args = {"job_id": self.job_id}
        if tool_id:
            setup_args["tool_id"] = tool_id
        if tool_version:
            setup_args["tool_version"] = tool_version
        if preserve_galaxy_python_environment:
            setup_args["preserve_galaxy_python_environment"] = preserve_galaxy_python_environment
        return self.setup_handler.setup(**setup_args)

    @property
    def prefer_local_staging(self):
        # If doing a job directory is defined, calculate paths here and stage
        # remotely.
        return self.job_directory is None


class JobClient(BaseJobClient):
    """
    Objects of this client class perform low-level communication with a remote Pulsar server.

    **Parameters**

    destination_params : dict or str
        connection parameters, either url with dict containing url (and optionally `private_token`).
    job_id : str
        Galaxy job/task id.
    """

    def __init__(self, destination_params, job_id, job_manager_interface):
        super(JobClient, self).__init__(destination_params, job_id)
        self.job_manager_interface = job_manager_interface

    def launch(self, command_line, dependencies_description=None, env=[], remote_staging=[], job_config=None):
        """
        Queue up the execution of the supplied `command_line` on the remote
        server. Called launch for historical reasons, should be renamed to
        enqueue or something like that.

        **Parameters**

        command_line : str
            Command to execute.
        """
        launch_params = dict(command_line=command_line, job_id=self.job_id)
        submit_params_dict = submit_params(self.destination_params)
        if submit_params_dict:
            launch_params['params'] = json_dumps(submit_params_dict)
        if dependencies_description:
            launch_params['dependencies_description'] = json_dumps(dependencies_description.to_dict())
        if env:
            launch_params['env'] = json_dumps(env)
        if remote_staging:
            launch_params['remote_staging'] = json_dumps(remote_staging)
        if job_config and 'touch_outputs' in job_config:
            # message clients pass the entire job config
            launch_params['submit_extras'] = json_dumps({'touch_outputs': job_config['touch_outputs']})

        if job_config and self.setup_handler.local:
            # Setup not yet called, job properties were inferred from
            # destination arguments. Hence, must have Pulsar setup job
            # before queueing.
            setup_params = _setup_params_from_job_config(job_config)
            launch_params['setup_params'] = json_dumps(setup_params)
        return self._raw_execute("submit", launch_params)

    def full_status(self):
        """ Return a dictionary summarizing final state of job.
        """
        return self.raw_check_complete()

    def kill(self):
        """
        Cancel remote job, either removing from the queue or killing it.
        """
        return self._raw_execute("cancel", {"job_id": self.job_id})

    @retry()
    @parseJson()
    def raw_check_complete(self):
        """
        Get check_complete response from the remote server.
        """
        check_complete_response = self._raw_execute("status", {"job_id": self.job_id})
        return check_complete_response

    def get_status(self):
        check_complete_response = self.raw_check_complete()
        # Older Pulsar instances won't set status so use 'complete', at some
        # point drop backward compatibility.
        status = check_complete_response.get("status", None)
        return status

    def clean(self):
        """
        Cleanup the remote job.
        """
        self._raw_execute("clean", {"job_id": self.job_id})

    @parseJson()
    def remote_setup(self, **setup_args):
        """
        Setup remote Pulsar server to run this job.
        """
        return self._raw_execute("setup", setup_args)

    def put_file(self, path, input_type, name=None, contents=None, action_type='transfer'):
        if not name:
            name = os.path.basename(path)
        args = {"job_id": self.job_id, "name": name, "type": input_type}
        input_path = path
        if contents:
            input_path = None
        # action type == 'message' should either copy or transfer
        # depending on default not just fallback to transfer.
        if action_type in ['transfer', 'message']:
            if isinstance(contents, string_types):
                contents = contents.encode("utf-8")
            message = "Uploading path [%s] (action_type: [%s])"
            log.debug(message, path, action_type)
            return self._upload_file(args, contents, input_path)
        elif action_type == 'copy':
            path_response = self._raw_execute('path', args)
            pulsar_path = json_loads(path_response)['path']
            _copy(path, pulsar_path)
            return {'path': pulsar_path}

    def fetch_output(self, path, name, working_directory, action_type, output_type):
        """
        Fetch (transfer, copy, etc...) an output from the remote Pulsar server.

        **Parameters**

        path : str
            Local path of the dataset.
        name : str
            Remote name of file (i.e. path relative to remote staging output
            or working directory).
        working_directory : str
            Local working_directory for the job.
        action_type : str
            Where to find file on Pulsar (output_workdir or output). legacy is also
            an option in this case Pulsar is asked for location - this will only be
            used if targetting an older Pulsar server that didn't return statuses
            allowing this to be inferred.
        """
        if output_type in ['output_workdir', 'output_metadata']:
            self._populate_output_path(name, path, action_type, output_type)
        elif output_type == 'output':
            self._fetch_output(path=path, name=name, action_type=action_type)
        else:
            raise Exception("Unknown output_type %s" % output_type)

    def _raw_execute(self, command, args={}, data=None, input_path=None, output_path=None):
        return self.job_manager_interface.execute(command, args, data, input_path, output_path)

    def _fetch_output(self, path, name=None, check_exists_remotely=False, action_type='transfer'):
        if not name:
            # Extra files will send in the path.
            name = os.path.basename(path)

        self._populate_output_path(name, path, action_type, path_type.OUTPUT)

    def _populate_output_path(self, name, output_path, action_type, path_type):
        ensure_directory(output_path)
        if action_type == 'transfer':
            self.__raw_download_output(name, self.job_id, path_type, output_path)
        elif action_type == 'copy':
            pulsar_path = self._output_path(name, self.job_id, path_type)['path']
            _copy(pulsar_path, output_path)

    @parseJson()
    def _upload_file(self, args, contents, input_path):
        return self._raw_execute("upload_file", args, contents, input_path)

    @parseJson()
    def _output_path(self, name, job_id, output_type):
        return self._raw_execute("path",
                                 {"name": name,
                                  "job_id": self.job_id,
                                  "type": output_type})

    @retry()
    def __raw_download_output(self, name, job_id, output_type, output_path):
        output_params = {
            "name": name,
            "job_id": self.job_id,
            "type": output_type
        }
        self._raw_execute("download_output", output_params, output_path=output_path)


class BaseMessageJobClient(BaseJobClient):

    def __init__(self, destination_params, job_id, client_manager):
        super(BaseMessageJobClient, self).__init__(destination_params, job_id)
        if not self.job_directory:
            error_message = "Message-queue based Pulsar client requires destination define a remote job_directory to stage files into."
            raise Exception(error_message)
        self.client_manager = client_manager

    def clean(self):
        del self.client_manager.status_cache[self.job_id]

    def full_status(self):
        full_status = self.client_manager.status_cache.get(self.job_id, None)
        if full_status is None:
            raise Exception("full_status() called before a final status was properly cached with cilent manager.")
        return full_status

    def _build_setup_message(self, command_line, dependencies_description, env, remote_staging, job_config):
        """
        """
        launch_params = dict(command_line=command_line, job_id=self.job_id)
        submit_params_dict = submit_params(self.destination_params)
        if submit_params_dict:
            launch_params['submit_params'] = submit_params_dict
        if dependencies_description:
            launch_params['dependencies_description'] = dependencies_description.to_dict()
        if env:
            launch_params['env'] = env
        if remote_staging:
            launch_params['remote_staging'] = remote_staging
            launch_params['remote_staging']['ssh_key'] = self.ssh_key
        if job_config and self.setup_handler.local:
            # Setup not yet called, job properties were inferred from
            # destination arguments. Hence, must have Pulsar setup job
            # before queueing.
            setup_params = _setup_params_from_job_config(job_config)
            launch_params["setup_params"] = setup_params
        return launch_params


class MessageJobClient(BaseMessageJobClient):

    def launch(self, command_line, dependencies_description=None, env=[], remote_staging=[], job_config=None):
        """
        """
        launch_params = self._build_setup_message(
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            remote_staging=remote_staging,
            job_config=job_config,
        )
        response = self.client_manager.exchange.publish("setup", launch_params)
        log.info("Job published to setup message queue.")
        return response

    def kill(self):
        self.client_manager.exchange.publish("kill", dict(job_id=self.job_id))


class MessageCLIJobClient(BaseMessageJobClient):

    def __init__(self, destination_params, job_id, client_manager, shell):
        super(MessageCLIJobClient, self).__init__(destination_params, job_id, client_manager)
        self.remote_pulsar_path = destination_params["remote_pulsar_path"]
        self.shell = shell

    def launch(self, command_line, dependencies_description=None, env=[], remote_staging=[], job_config=None):
        """
        """
        launch_params = self._build_setup_message(
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            remote_staging=remote_staging,
            job_config=job_config,
        )
        base64_message = to_base64_json(launch_params)
        submit_command = os.path.join(self.remote_pulsar_path, "scripts", "submit.bash")
        # TODO: Allow configuration of manager, app, and ini path...
        self.shell.execute("nohup %s --base64 %s &" % (submit_command, base64_message))

    def kill(self):
        # TODO
        pass


class MessageCoexecutionPodJobClient(BaseMessageJobClient):

    def __init__(self, destination_params, job_id, client_manager):
        ensure_pykube()
        super(MessageCoexecutionPodJobClient, self).__init__(destination_params, job_id, client_manager)
        self.instance_id = galaxy_instance_id(destination_params)
        self.pulsar_container_image = destination_params.get("pulsar_container_image", "galaxy/pulsar-pod-staging:0.13.0")
        self._default_pull_policy = pull_policy(destination_params)

    def launch(self, command_line, dependencies_description=None, env=[], remote_staging=[], job_config=None, container=None, pulsar_app_config=None):
        """
        """
        launch_params = self._build_setup_message(
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            remote_staging=remote_staging,
            job_config=job_config,
        )

        manager_type = "coexecution" if container is not None else "unqueued"
        if "manager" not in pulsar_app_config and "managers" not in pulsar_app_config:
            pulsar_app_config["manager"] = {"type": manager_type}

        using_dependencies = container is None and dependencies_description is not None
        if using_dependencies and "dependency_resolution" not in pulsar_app_config:
            # Setup default dependency resolution for container above...
            dependency_resolution = {
                "cache": False,
                "use": True,
                "default_base_path": "/pulsar_dependencies",
                "cache_dir": "/pulsar_dependencies/_cache",
                "resolvers": [{  # TODO: add CVMFS resolution...
                    "type": "conda",
                    "auto_init": True,
                    "auto_install": True,
                    "prefix": '/pulsar_dependencies/conda',
                }, {
                    "type": "conda",
                    "auto_init": True,
                    "auto_install": True,
                    "prefix": '/pulsar_dependencies/conda',
                    "versionless": True,
                }]
            }
            pulsar_app_config["dependency_resolution"] = dependency_resolution
        base64_message = to_base64_json(launch_params)
        base64_app_conf = to_base64_json(pulsar_app_config)

        job_name = self._k8s_job_name
        params = self.destination_params

        pulsar_container_image = self.pulsar_container_image

        job_directory = self.job_directory

        volumes = [
            {"name": "staging-directory", "emptyDir": {}},
        ]
        volume_mounts = [
            {"mountPath": "/pulsar_staging", "name": "staging-directory"},
        ]
        pulsar_container_dict = {
            "name": "pulsar-container",
            "image": pulsar_container_image,
            "command": ["pulsar-submit"],
            "args": ["--base64", base64_message, "--app_conf_base64", base64_app_conf],
            "workingDir": "/",
            "volumeMounts": volume_mounts,
        }
        tool_container_image = container
        container_dicts = [pulsar_container_dict]
        if container:
            command = TOOL_EXECUTION_CONTAINER_COMMAND_TEMPLATE % job_directory.job_directory
            tool_container_spec = {
                "name": "tool-container",
                "image": tool_container_image,
                "command": ["sh"],
                "args": ["-c", command],
                "workingDir": "/",
                "volumeMounts": volume_mounts,
            }
            container_dicts.append(tool_container_spec)
        for container_dict in container_dicts:
            if self._default_pull_policy:
                container_dict["imagePullPolicy"] = self._default_pull_policy

        template = {
            "metadata": {
                "labels": {"app": job_name},
            },
            "spec": {
                "volumes": volumes,
                "restartPolicy": "Never",
                "containers": container_dicts,
            }
        }
        spec = {"template": template}
        k8s_job_obj = job_object_dict(params, job_name, spec)
        pykube_client = self._pykube_client
        job = Job(pykube_client, k8s_job_obj)
        job.create()

    def kill(self):
        job_name = self._k8s_job_name
        pykube_client = self._pykube_client
        job = find_job_object_by_name(pykube_client, job_name)
        if job:
            log.info("Kill k8s job with name %s" % job_name)
            stop_job(job)
        else:
            log.info("Attempted to kill k8s job but it is unavailable.")

    @property
    def _pykube_client(self):
        return pykube_client_from_dict(self.destination_params)

    @property
    def _k8s_job_name(self):
        job_id = self.job_id
        job_name = produce_unique_k8s_job_name(app_prefix="pulsar", job_id=job_id, instance_id=self.instance_id)
        return job_name


class InputCachingJobClient(JobClient):
    """
    Beta client that cache's staged files to prevent duplication.
    """

    def __init__(self, destination_params, job_id, job_manager_interface, client_cacher):
        super(InputCachingJobClient, self).__init__(destination_params, job_id, job_manager_interface)
        self.client_cacher = client_cacher

    @parseJson()
    def _upload_file(self, args, contents, input_path):
        action = "upload_file"
        if contents:
            input_path = None
            return self._raw_execute(action, args, contents, input_path)
        else:
            event_holder = self.client_cacher.acquire_event(input_path)
            cache_required = self.cache_required(input_path)
            if cache_required:
                self.client_cacher.queue_transfer(self, input_path)
            while not event_holder.failed:
                available = self.file_available(input_path)
                if available['ready']:
                    token = available['token']
                    args["cache_token"] = token
                    return self._raw_execute(action, args)
                event_holder.event.wait(30)
            if event_holder.failed:
                raise Exception("Failed to transfer file %s" % input_path)

    @parseJson()
    def cache_required(self, path):
        return self._raw_execute("cache_required", {"path": path})

    @parseJson()
    def cache_insert(self, path):
        return self._raw_execute("cache_insert", {"path": path}, None, path)

    @parseJson()
    def file_available(self, path):
        return self._raw_execute("file_available", {"path": path})


def _copy(from_path, to_path):
    message = "Copying path [%s] to [%s]"
    log.debug(message, from_path, to_path)
    copy(from_path, to_path)


def _setup_params_from_job_config(job_config):
    job_id = job_config.get("job_id", None)
    tool_id = job_config.get("tool_id", None)
    tool_version = job_config.get("tool_version", None)
    preserve_galaxy_python_environment = job_config.get("preserve_galaxy_python_environment", None)
    return dict(
        job_id=job_id,
        tool_id=tool_id,
        tool_version=tool_version,
        use_metadata=True,
        preserve_galaxy_python_environment=preserve_galaxy_python_environment,
    )
