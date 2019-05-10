"""
pulsar client
=================

This module contains logic for interfacing with an external Pulsar server.

------------------
Configuring Galaxy
------------------

Galaxy job runners are configured in Galaxy's ``job_conf.xml`` file. See ``job_conf.xml.sample_advanced``
in your Galaxy code base or on
`Github <https://github.com/galaxyproject/galaxy/blob/dev/config/job_conf.xml.sample_advanced>`_
for information on how to configure Galaxy to interact with the Pulsar.

Galaxy also supports an older, less rich configuration of job runners directly
in its main ``galaxy.ini`` file. The following section describes how to
configure Galaxy to communicate with the Pulsar in this legacy mode.

Legacy
------

A Galaxy tool can be configured to be executed remotely via Pulsar by
adding a line to the ``galaxy.ini`` file under the ``galaxy:tool_runners``
section with the format::

    <tool_id> = pulsar://http://<pulsar_host>:<pulsar_port>

As an example, if a host named remotehost is running the Pulsar server
application on port ``8913``, then the tool with id ``test_tool`` can
be configured to run remotely on remotehost by adding the following
line to ``galaxy.ini``::

    test_tool = pulsar://http://remotehost:8913

Remember this must be added after the ``[galaxy:tool_runners]`` header
in the ``galaxy.ini`` file.


"""

from .client import OutputNotFoundException
from .destination import url_to_destination_params
from .exceptions import PulsarClientTransportError
from .manager import build_client_manager
from .path_mapper import PathMapper
from .staging import (
    ClientJobDescription,
    ClientInputs,
    ClientInput,
    ClientOutputs,
    CLIENT_INPUT_PATH_TYPES,
    PulsarOutputs,
)
from .staging.down import finish_job
from .staging.up import submit_job

__all__ = [
    'build_client_manager',
    'OutputNotFoundException',
    'url_to_destination_params',
    'finish_job',
    'submit_job',
    'ClientJobDescription',
    'PulsarOutputs',
    'ClientInput',
    'ClientInputs',
    'ClientOutputs',
    'CLIENT_INPUT_PATH_TYPES',
    'ClientOutputs',
    'PathMapper',
    'PulsarClientTransportError',
]
