import os
from uuid import uuid4

from packaging.version import (
    InvalidVersion,
    Version,
)

from pulsar import __version__ as pulsar_version
from .util import filter_destination_params

REMOTE_SYSTEM_PROPERTY_PREFIX = "remote_property_"
REMOTE_PULSAR_VERSION_PARAM = "remote_pulsar_version"
# Published staging images and the Pulsar they were built from - tags don't
# follow releases (0.15.0.2 predates 0.15.0). Add new images here.
KNOWN_PULSAR_CONTAINER_VERSIONS = {
    "galaxy/pulsar-pod-staging:0.10.0": "0.10.0.dev0",
    "galaxy/pulsar-pod-staging:0.12.0": "0.12.0.dev0",
    "galaxy/pulsar-pod-staging:0.13.0": "0.13.0.dev0",
    "galaxy/pulsar-pod-staging:0.14.0": "0.14.0.dev3",
    "galaxy/pulsar-pod-staging:0.14.15.0": "0.14.15",
    "galaxy/pulsar-pod-staging:0.15.0.1": "0.15.0.dev0",
    "galaxy/pulsar-pod-staging:0.15.0.2": "0.15.0.dev1",
}


def build(client, destination_args):
    """ Build a SetupHandler object for client from destination parameters.
    """
    # Have defined a remote job directory, lets do the setup locally.
    if client.job_directory:
        handler = LocalSetupHandler(client, destination_args)
    else:
        handler = RemoteSetupHandler(client)
    return handler


class LocalSetupHandler:
    """ Parse destination params to infer job setup parameters (input/output
    directories, etc...). Default is to get this configuration data from the
    remote Pulsar server.

    Downside of this approach is that it requires more and more dependent
    configuraiton of Galaxy. Upside is that it is asynchronous and thus makes
    message queue driven configurations possible.

    Remote system properties (such as galaxy_home) can be specified in
    destination args by prefixing property with remote_property_ (e.g.
    remote_property_galaxy_home).

    The remote Pulsar is never contacted, so its version is unknown unless
    declared with remote_pulsar_version or implied by a known
    pulsar_container_image. ``pulsar_version_source`` in the job config tells
    Galaxy which it got - ``client`` means ``pulsar_version`` is just this
    client library's version.
    """

    def __init__(self, client, destination_args):
        self.client = client
        system_properties = self.__build_system_properties(destination_args)
        system_properties["separator"] = client.job_directory.separator
        self.system_properties = system_properties
        self.jobs_directory = destination_args["jobs_directory"]
        self.assign_ids = destination_args.get("assign_ids", "galaxy")
        remote_pulsar_version = _remote_pulsar_version(destination_args)
        image_pulsar_version = KNOWN_PULSAR_CONTAINER_VERSIONS.get(destination_args.get("pulsar_container_image"))
        # pulsar_version stays populated so Galaxy releases that predate
        # pulsar_version_source keep passing their minimum version check.
        if remote_pulsar_version:
            self.pulsar_version, self.pulsar_version_source = remote_pulsar_version, "destination"
        elif image_pulsar_version:
            self.pulsar_version, self.pulsar_version_source = image_pulsar_version, "container_image"
        else:
            self.pulsar_version, self.pulsar_version_source = pulsar_version, "client"

    def setup(self, job_id, tool_id=None, tool_version=None, preserve_galaxy_python_environment=None):
        if self.assign_ids == "uuid":
            job_id = uuid4().hex

        # Following is a gross hack but same gross hack in pulsar.client.staging.up
        if self.client.job_id != job_id:
            self.client.assign_job_id(job_id)

        return build_job_config(
            job_id=job_id,
            job_directory=self.client.job_directory,
            system_properties=self.system_properties,
            tool_id=tool_id,
            tool_version=tool_version,
            preserve_galaxy_python_environment=preserve_galaxy_python_environment,
            pulsar_version=self.pulsar_version,
            pulsar_version_source=self.pulsar_version_source,
        )

    @property
    def local(self):
        """
        """
        return True

    def __build_system_properties(self, destination_params):
        return filter_destination_params(destination_params, REMOTE_SYSTEM_PROPERTY_PREFIX)


class RemoteSetupHandler:
    """ Default behavior. Fetch setup information from remote Pulsar server.
    """
    def __init__(self, client):
        self.client = client

    def setup(self, **setup_args):
        setup_args["use_metadata"] = "true"
        job_config = self.client.remote_setup(**setup_args)
        # Always say so, so Galaxy can treat a missing key as coming from a
        # client that predates pulsar_version_source rather than trusting it.
        job_config.setdefault("pulsar_version_source", "remote")
        return job_config

    @property
    def local(self):
        """
        """
        return False


def _remote_pulsar_version(destination_args):
    remote_pulsar_version = destination_args.get(REMOTE_PULSAR_VERSION_PARAM)
    if remote_pulsar_version is None:
        return None
    if not isinstance(remote_pulsar_version, str):
        # YAML reads an unquoted 0.20 as the float 0.2, losing digits we can't recover.
        raise ValueError(
            f"{REMOTE_PULSAR_VERSION_PARAM} must be a string, got {remote_pulsar_version!r} - "
            f"quote it in the job configuration (e.g. {REMOTE_PULSAR_VERSION_PARAM}: \"0.15.16\")"
        )
    try:
        Version(remote_pulsar_version)
    except InvalidVersion:
        raise ValueError(
            f"{REMOTE_PULSAR_VERSION_PARAM} must be a version such as \"0.15.16\", got {remote_pulsar_version!r}"
        ) from None
    return remote_pulsar_version


def build_job_config(
    job_id,
    job_directory,
    system_properties={},
    tool_id=None,
    tool_version=None,
    preserve_galaxy_python_environment=None,
    pulsar_version=pulsar_version,
    pulsar_version_source=None,
):
    """
    """
    inputs_directory = job_directory.inputs_directory()
    working_directory = job_directory.working_directory()
    metadata_directory = job_directory.metadata_directory()
    outputs_directory = job_directory.outputs_directory()
    configs_directory = job_directory.configs_directory()
    tools_directory = job_directory.tool_files_directory()
    unstructured_files_directory = job_directory.unstructured_files_directory()
    sep = system_properties.get("sep", os.sep)
    job_config = {
        "job_directory": job_directory.path,
        "working_directory": working_directory,
        "metadata_directory": metadata_directory,
        "outputs_directory": outputs_directory,
        "configs_directory": configs_directory,
        "tools_directory": tools_directory,
        "inputs_directory": inputs_directory,
        "unstructured_files_directory": unstructured_files_directory,
        # Poorly named legacy attribute. Drop at some point.
        "path_separator": sep,
        "job_id": job_id,
        "system_properties": system_properties,
        "pulsar_version": pulsar_version,
        "preserve_galaxy_python_environment": preserve_galaxy_python_environment,
    }
    if pulsar_version_source:
        job_config["pulsar_version_source"] = pulsar_version_source
    if tool_id:
        job_config["tool_id"] = tool_id
    if tool_version:
        job_config["tool_version"] = tool_version
    return job_config


__all__ = ['build', 'build_job_config']
