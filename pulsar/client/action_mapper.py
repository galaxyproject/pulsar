import fnmatch
import tempfile
from contextlib import contextmanager
from os import (
    makedirs,
    unlink,
)
from os.path import (
    abspath,
    basename,
    dirname,
    exists,
    join,
    sep,
)
from re import (
    compile,
    escape,
)
from typing import (
    Any,
    Dict,
    List,
    Type,
)
from urllib.parse import urlencode

from galaxy.util.bunch import Bunch

from .config_util import read_file
from .transport import (
    get_file,
    post_file,
    rsync_get_file,
    rsync_post_file,
    scp_get_file,
    scp_post_file,
)
from .transport.tus import (
    tus_upload_file,
)
from .util import (
    copy_to_path,
    directory_files,
    unique_path_prefix,
)

DEFAULT_MAPPED_ACTION = 'transfer'  # Not really clear to me what this should be, exception?
DEFAULT_PATH_MAPPER_TYPE = 'prefix'

STAGING_ACTION_REMOTE = "remote"
STAGING_ACTION_LOCAL = "local"
STAGING_ACTION_NONE = None
STAGING_ACTION_DEFAULT = "default"

# Poor man's enum.
path_type = Bunch(
    # Galaxy input datasets and extra files.
    INPUT="input",
    # Galaxy config and param files.
    CONFIG="config",
    # Files from tool's tool_dir (for now just wrapper if available).
    TOOL="tool",
    # Input tool work dir files - e.g. task-split input file
    WORKDIR="workdir",
    # Job directory files (e.g. tool standard input/output and containerized command).
    JOBDIR="jobdir",
    # Input metadata dir files - e.g. metadata files, etc..
    METADATA="metadata",
    # Galaxy output datasets in their final home.
    OUTPUT="output",
    # Galaxy from_work_dir output paths and other files (e.g. galaxy.json)
    OUTPUT_WORKDIR="output_workdir",
    # Meta job and data files (e.g. Galaxy metadata generation files and
    # metric instrumentation files)
    OUTPUT_METADATA="output_metadata",
    # Job directory files output.
    OUTPUT_JOBDIR="output_jobdir",
    # Other fixed tool parameter paths (likely coming from tool data, but not
    # necessarily).
    UNSTRUCTURED="unstructured",
)


ACTION_DEFAULT_PATH_TYPES = [
    path_type.INPUT,
    path_type.CONFIG,
    path_type.TOOL,
    path_type.WORKDIR,
    path_type.JOBDIR,
    path_type.METADATA,
    path_type.OUTPUT,
    path_type.OUTPUT_WORKDIR,
    path_type.OUTPUT_METADATA,
    path_type.OUTPUT_JOBDIR,
]
ALL_PATH_TYPES = ACTION_DEFAULT_PATH_TYPES + [path_type.UNSTRUCTURED]

MISSING_FILES_ENDPOINT_ERROR = "Attempted to use remote_transfer action without defining a files_endpoint."
MISSING_SSH_KEY_ERROR = "Attempt to use file transfer action requiring an SSH key without specifying a ssh_key."


class FileActionMapper:
    """
    Objects of this class define how paths are mapped to actions.

    >>> json_string = r'''{"paths": [ \
      {"path": "/opt/galaxy", "action": "none"}, \
      {"path": "/galaxy/data", "action": "transfer"}, \
      {"path": "/cool/bamfiles/**/*.bam", "action": "copy", "match_type": "glob"}, \
      {"path": ".*/dataset_\\\\d+.dat", "action": "copy", "match_type": "regex"} \
    ]}'''
    >>> from tempfile import NamedTemporaryFile
    >>> from os import unlink
    >>> def mapper_for(default_action, config_contents):
    ...     f = NamedTemporaryFile(delete=False)
    ...     f.write(config_contents.encode('UTF-8'))
    ...     f.close()
    ...     mock_client = Bunch(default_file_action=default_action, action_config_path=f.name, files_endpoint=None)
    ...     mapper = FileActionMapper(mock_client)
    ...     as_dict = config=mapper.to_dict()
    ...     mapper = FileActionMapper(config=as_dict) # Serialize and deserialize it to make sure still works
    ...     unlink(f.name)
    ...     return mapper
    >>> mapper = mapper_for(default_action='none', config_contents=json_string)
    >>> # Test first config line above, implicit path prefix mapper
    >>> action = mapper.action({'path': '/opt/galaxy/tools/filters/catWrapper.py'}, 'input')
    >>> action.action_type == u'none'
    True
    >>> action.staging_needed
    False
    >>> # Test another (2nd) mapper, this one with a different action
    >>> action = mapper.action({'path': '/galaxy/data/files/000/dataset_1.dat'}, 'input')
    >>> action.action_type == u'transfer'
    True
    >>> action.staging_needed
    True
    >>> # Always at least copy work_dir outputs.
    >>> action = mapper.action({'path': '/opt/galaxy/database/working_directory/45.sh'}, 'workdir')
    >>> action.action_type == u'copy'
    True
    >>> action.staging_needed
    True
    >>> # Test glob mapper (matching test)
    >>> mapper.action({'path': '/cool/bamfiles/projectABC/study1/patient3.bam'}, 'input').action_type == u'copy'
    True
    >>> # Test glob mapper (non-matching test)
    >>> mapper.action({'path': '/cool/bamfiles/projectABC/study1/patient3.bam.bai'}, 'input').action_type == u'none'
    True
    >>> # Regex mapper test.
    >>> mapper.action({'path': '/old/galaxy/data/dataset_10245.dat'}, 'input').action_type == u'copy'
    True
    >>> # Doesn't map unstructured paths by default
    >>> mapper.action({'path': '/old/galaxy/data/dataset_10245.dat'}, 'unstructured').action_type == u'none'
    True
    >>> input_only_mapper = mapper_for(default_action="none", config_contents=r'''{"paths": [ \
      {"path": "/", "action": "transfer", "path_types": "input"} \
    ] }''')
    >>> input_only_mapper.action({'path': '/dataset_1.dat'}, 'input').action_type == u'transfer'
    True
    >>> input_only_mapper.action({'path': '/dataset_1.dat'}, 'output').action_type == u'none'
    True
    >>> unstructured_mapper = mapper_for(default_action="none", config_contents=r'''{"paths": [ \
      {"path": "/", "action": "transfer", "path_types": "*any*"} \
    ] }''')
    >>> unstructured_mapper.action({'path': '/old/galaxy/data/dataset_10245.dat'}, 'unstructured').action_type == u'transfer'
    True
    >>> match_type_only_mapper = mapper_for(default_action="none", config_contents=r'''{"paths": [ \
      {"action": "transfer", "path_types": "input"}, \
      {"action": "remote_copy", "path_types": "output"} \
    ] }''')
    >>> input_action = match_type_only_mapper.action({}, 'input')
    >>> input_action.action_type
    'transfer'
    >>> output_action = match_type_only_mapper.action({}, 'output')
    >>> output_action.action_type
    'remote_copy'
    """

    def __init__(self, client=None, config=None):
        if config is None and client is None:
            message = "FileActionMapper must be constructed from either a client or a config dictionary."
            raise Exception(message)
        if config is None:
            config = self.__client_to_config(client)
        self.default_action = config.get("default_action", "transfer")
        self.ssh_key = config.get("ssh_key", None)
        self.ssh_user = config.get("ssh_user", None)
        self.ssh_host = config.get("ssh_host", None)
        self.ssh_port = config.get("ssh_port", None)
        self.mappers = mappers_from_dicts(config.get("paths", []))
        self.files_endpoint = config.get("files_endpoint", None)
        self.actions = []
        # Might want to make the working directory available here so that we know where to place archive
        # for archive action

    def action(self, source, type, mapper=None):
        path = source.get("path", None)
        mapper = self.__find_mapper(path, type, mapper)
        action_class = self.__action_class(path, type, mapper)
        file_lister = DEFAULT_FILE_LISTER
        action_kwds = {}
        if mapper:
            file_lister = mapper.file_lister
            action_kwds = mapper.action_kwds
        action = action_class(source, file_lister=file_lister, **action_kwds)
        self.__process_action(action, type)
        self.actions.append(action)
        return action

    def finalize(self):
        return [_ for _ in (action.finalize() for action in self.actions) if _]

    def unstructured_mappers(self):
        """ Return mappers that will map 'unstructured' files (i.e. go beyond
        mapping inputs, outputs, and config files).
        """
        return filter(lambda m: path_type.UNSTRUCTURED in m.path_types, self.mappers)

    def to_dict(self):
        return dict(
            default_action=self.default_action,
            files_endpoint=self.files_endpoint,
            ssh_key=self.ssh_key,
            ssh_user=self.ssh_user,
            ssh_port=self.ssh_port,
            ssh_host=self.ssh_host,
            paths=list(map(lambda m: m.to_dict(), self.mappers))
        )

    def __client_to_config(self, client):
        action_config_path = client.action_config_path
        if action_config_path:
            config = read_file(action_config_path)
        else:
            config = getattr(client, "file_actions", {})
        config["default_action"] = client.default_file_action
        config["files_endpoint"] = client.files_endpoint
        for attr in ['ssh_key', 'ssh_user', 'ssh_port', 'ssh_host']:
            if hasattr(client, attr):
                config[attr] = getattr(client, attr)
        return config

    def __find_mapper(self, path, type, mapper=None):
        if not mapper:
            if path is not None:
                normalized_path = abspath(path)
            else:
                normalized_path = None
            for query_mapper in self.mappers:
                if query_mapper.matches(normalized_path, type):
                    mapper = query_mapper
                    break
        return mapper

    def __action_class(self, path, type, mapper):
        action_type = self.default_action if type in ACTION_DEFAULT_PATH_TYPES else "none"
        if mapper:
            action_type = mapper.action_type
        if type in ["workdir", "jobdir", "output_workdir", "output_metadata", "output_jobdir"] and action_type == "none":
            # We are changing the working_directory/job_directory relative to what
            # Galaxy would use, these need to be copied over.
            action_type = "copy"
        action_class = actions.get(action_type, None)
        if action_class is None:
            message_template = "Unknown action_type encountered %s while trying to map path %s"
            message_args = (action_type, path)
            raise Exception(message_template % message_args)
        return action_class

    def __process_action(self, action, file_type):
        """ Extension point to populate extra action information after an
        action has been created.
        """
        if getattr(action, "inject_url", False):
            self.__inject_url(action, file_type)
        if getattr(action, "inject_ssh_properties", False):
            self.__inject_ssh_properties(action)

    def __inject_url(self, action, file_type):
        url_base = self.files_endpoint
        if not url_base:
            raise Exception(MISSING_FILES_ENDPOINT_ERROR)
        if "?" not in url_base:
            url_base = "%s?" % url_base
        else:
            url_base = "%s&" % url_base
        url_params = urlencode({"path": action.path, "file_type": file_type})
        action.url = f"{url_base}{url_params}"

    def __inject_ssh_properties(self, action):
        for attr in ["ssh_key", "ssh_host", "ssh_port", "ssh_user"]:
            action_attr = getattr(action, attr)
            if action_attr == UNSET_ACTION_KWD:
                client_default_attr = getattr(self, attr, None)
                setattr(action, attr, client_default_attr)

        if action.ssh_key is None:
            raise Exception(MISSING_SSH_KEY_ERROR)


REQUIRED_ACTION_KWD = object()
UNSET_ACTION_KWD = "__UNSET__"


class BaseAction:
    whole_directory_transfer_supported = False
    action_spec: Dict[str, Any] = {}
    action_type: str

    def __init__(self, source, file_lister=None):
        self.source = source
        self.file_lister = file_lister or DEFAULT_FILE_LISTER

    @property
    def path(self):
        return self.source.get("path")

    def unstructured_map(self, path_helper):
        unstructured_map = self.file_lister.unstructured_map(self.path)
        if self.staging_needed:
            # To ensure uniqueness, prepend unique prefix to each name
            prefix = unique_path_prefix(self.path)
            for path, name in unstructured_map.items():
                unstructured_map[path] = join(prefix, name)
        else:
            path_rewrites = {}
            for path in unstructured_map:
                rewrite = self.path_rewrite(path_helper, path)
                if rewrite:
                    path_rewrites[path] = rewrite
            unstructured_map = path_rewrites
        return unstructured_map

    @property
    def staging_needed(self):
        return self.staging != STAGING_ACTION_NONE

    @property
    def staging_action_local(self):
        return self.staging == STAGING_ACTION_LOCAL

    def _extend_base_dict(self, **kwds):
        base_dict = dict(
            path=self.path,  # For older Pulsar servers (pre-0.13.0?)
            source=self.source,
            action_type=self.action_type,
        )
        base_dict.update(**kwds)
        return base_dict

    def finalize(self):
        pass

    def to_dict(self):
        return self._extend_base_dict()

    def __str__(self):
        as_dict = self.to_dict()
        attribute_str = ""
        first = True
        for key, value in as_dict.items():
            if key == "source":
                continue
            if first:
                first = False
            else:
                attribute_str += ","
            attribute_str += "{}={}".format(key, value)
        return "FileAction[%s]" % attribute_str


class NoneAction(BaseAction):
    """ This action indicates the corresponding path does not require any
    additional action. This should indicate paths that are available both on
    the Pulsar client (i.e. Galaxy server) and remote Pulsar server with the same
    paths. """
    action_type = "none"
    staging = STAGING_ACTION_NONE

    def to_dict(self):
        return self._extend_base_dict()

    @classmethod
    def from_dict(cls, action_dict):
        return NoneAction(source=action_dict["source"])

    def path_rewrite(self, path_helper, path=None):
        return None


class RewriteAction(BaseAction):
    """ This actin indicates the Pulsar server should simply rewrite the path
    to the specified file.
    """
    action_spec = dict(
        source_directory=REQUIRED_ACTION_KWD,
        destination_directory=REQUIRED_ACTION_KWD
    )
    action_type = "rewrite"
    staging = STAGING_ACTION_NONE

    def __init__(self, source, file_lister=None, source_directory=None, destination_directory=None):
        super().__init__(source, file_lister=file_lister)
        self.source_directory = source_directory
        self.destination_directory = destination_directory

    def to_dict(self):
        return self._extend_base_dict(
            source_directory=self.source_directory,
            destination_directory=self.destination_directory,
        )

    @classmethod
    def from_dict(cls, action_dict):
        return RewriteAction(
            source=action_dict["source"],
            source_directory=action_dict["source_directory"],
            destination_directory=action_dict["destination_directory"],
        )

    def path_rewrite(self, path_helper, path=None):
        if not path:
            path = self.path
        new_path = path_helper.from_posix_with_new_base(self.path, self.source_directory, self.destination_directory)
        return None if new_path == self.path else new_path


class TransferAction(BaseAction):
    """ This actions indicates that the Pulsar client should initiate an HTTP
    transfer of the corresponding path to the remote Pulsar server before
    launching the job. """
    action_type = "transfer"
    staging = STAGING_ACTION_LOCAL


class CopyAction(BaseAction):
    """ This action indicates that the Pulsar client should execute a file system
    copy of the corresponding path to the Pulsar staging directory prior to
    launching the corresponding job. """
    action_type = "copy"
    staging = STAGING_ACTION_LOCAL


class RemoteCopyAction(BaseAction):
    """ This action indicates the Pulsar server should copy the file before
    execution via direct file system copy. This is like a CopyAction, but
    it indicates the action should occur on the Pulsar server instead of on
    the client.
    """
    action_type = "remote_copy"
    staging = STAGING_ACTION_REMOTE

    @classmethod
    def from_dict(cls, action_dict):
        return RemoteCopyAction(source=action_dict["source"])

    def write_to_path(self, path):
        copy_to_path(open(self.path, "rb"), path)

    def write_from_path(self, pulsar_path):
        destination = self.path
        parent_directory = dirname(destination)
        if not exists(parent_directory):
            makedirs(parent_directory)
        with open(pulsar_path, "rb") as f:
            copy_to_path(f, destination)


class RemoteTransferAction(BaseAction):
    """ This action indicates the Pulsar server should transfer the file before
    execution via one of the remote transfer implementations. This is like a TransferAction, but
    it indicates the action requires network access to the staging server, and
    should be executed via ssh/rsync/etc
    """
    inject_url = True
    action_type = "remote_transfer"
    staging = STAGING_ACTION_REMOTE

    def __init__(self, source, file_lister=None, url=None):
        super().__init__(source, file_lister=file_lister)
        self.url = url

    def to_dict(self):
        return self._extend_base_dict(url=self.url)

    @classmethod
    def from_dict(cls, action_dict):
        return RemoteTransferAction(source=action_dict["source"], url=action_dict["url"])

    def write_to_path(self, path):
        get_file(self.url, path)

    def write_from_path(self, pulsar_path):
        post_file(self.url, pulsar_path)


class RemoteTransferTusAction(BaseAction):
    """ This action indicates the Pulsar server should transfer the file before
    execution via one of the remote transfer implementations. This is like a TransferAction, but
    it indicates the action requires network access to the staging server and TUS
    will be used for the transfer
    """
    inject_url = True
    action_type = "remote_transfer_tus"
    staging = STAGING_ACTION_REMOTE

    def __init__(self, source, file_lister=None, url=None):
        super().__init__(source, file_lister=file_lister)
        self.url = url

    def to_dict(self):
        return self._extend_base_dict(url=self.url)

    @classmethod
    def from_dict(cls, action_dict):
        return RemoteTransferAction(source=action_dict["source"], url=action_dict["url"])

    def write_to_path(self, path):
        get_file(self.url, path)

    def write_from_path(self, pulsar_path):
        tus_upload_file(self.url, pulsar_path)


class JsonTransferAction(BaseAction):
    """
    This action indicates that the pulsar server should create a JSON manifest that can be used to stage files by an
    external system that can stage files in and out of the compute environment.
    """
    inject_url = True
    whole_directory_transfer_supported = True
    action_type = "json_transfer"
    staging = STAGING_ACTION_REMOTE

    def __init__(self, source, file_lister=None, url=None):
        super().__init__(source, file_lister)
        self.url = url
        self._path = None

    @classmethod
    def from_dict(cls, action_dict):
        return JsonTransferAction(source=action_dict["source"], url=action_dict["url"])

    def write_to_path(self, path):
        self._path = path

    def write_from_path(self, pulsar_path: str):
        self._path = pulsar_path

    def finalize(self):
        return {"url": self.url, "path": self.path}


class RemoteObjectStoreCopyAction(BaseAction):
    """
    """
    action_type = "remote_object_store_copy"
    staging = STAGING_ACTION_REMOTE
    inject_object_store = True

    @classmethod
    def from_dict(cls, action_dict):
        return RemoteObjectStoreCopyAction(source=action_dict["source"])

    def write_to_path(self, path):
        assert self.object_store  # Make sure object_store attribute injected
        assert "object_store_ref" in self.source
        object_store_ref = self.source["object_store_ref"]
        dataset_object = Bunch(
            id=object_store_ref["dataset_id"],
            uuid=object_store_ref["dataset_uuid"],
            object_store_id=object_store_ref["object_store_id"],
        )
        filename = self.object_store.get_filename(dataset_object)
        copy_to_path(open(filename, 'rb'), path)

    def write_from_path(self, pulsar_path):
        raise NotImplementedError("Writing raw files to object store not supported at this time.")


class PubkeyAuthenticatedTransferAction(BaseAction):
    """Base class for file transfers requiring an SSH public/private key
    """
    inject_ssh_properties = True
    action_spec = dict(
        ssh_key=UNSET_ACTION_KWD,
        ssh_user=UNSET_ACTION_KWD,
        ssh_host=UNSET_ACTION_KWD,
        ssh_port=UNSET_ACTION_KWD,
    )
    staging = STAGING_ACTION_REMOTE

    def __init__(self, source, file_lister=None, ssh_user=UNSET_ACTION_KWD,
                 ssh_host=UNSET_ACTION_KWD, ssh_port=UNSET_ACTION_KWD, ssh_key=UNSET_ACTION_KWD):
        super().__init__(source, file_lister=file_lister)
        self.ssh_user = ssh_user
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_key = ssh_key

    def to_dict(self):
        return self._extend_base_dict(
            ssh_user=self.ssh_user,
            ssh_host=self.ssh_host,
            ssh_port=self.ssh_port
        )

    @contextmanager
    def _serialized_key(self):
        key_file = self.__serialize_ssh_key()
        yield key_file
        self.__cleanup_ssh_key(key_file)

    def __serialize_ssh_key(self):
        f = tempfile.NamedTemporaryFile(delete=False)
        if self.ssh_key is not None:
            f.write(self.ssh_key.encode("utf-8"))
        else:
            raise Exception("SSH_KEY not available")
        return f.name

    def __cleanup_ssh_key(self, keyfile):
        if exists(keyfile):
            unlink(keyfile)


class RsyncTransferAction(PubkeyAuthenticatedTransferAction):
    action_type = "remote_rsync_transfer"

    @classmethod
    def from_dict(cls, action_dict):
        return RsyncTransferAction(source=action_dict["source"],
                                   ssh_user=action_dict["ssh_user"],
                                   ssh_host=action_dict["ssh_host"],
                                   ssh_port=action_dict["ssh_port"],
                                   ssh_key=action_dict["ssh_key"])

    def write_to_path(self, path):
        with self._serialized_key() as key_file:
            rsync_get_file(self.path, path, self.ssh_user, self.ssh_host,
                           self.ssh_port, key_file)

    def write_from_path(self, pulsar_path):
        with self._serialized_key() as key_file:
            rsync_post_file(pulsar_path, self.path, self.ssh_user,
                            self.ssh_host, self.ssh_port, key_file)


class ScpTransferAction(PubkeyAuthenticatedTransferAction):
    action_type = "remote_scp_transfer"

    @classmethod
    def from_dict(cls, action_dict):
        return ScpTransferAction(source=action_dict["source"],
                                 ssh_user=action_dict["ssh_user"],
                                 ssh_host=action_dict["ssh_host"],
                                 ssh_port=action_dict["ssh_port"],
                                 ssh_key=action_dict["ssh_key"])

    def write_to_path(self, path):
        with self._serialized_key() as key_file:
            scp_get_file(self.path, path, self.ssh_user, self.ssh_host,
                         self.ssh_port, key_file)

    def write_from_path(self, pulsar_path):
        with self._serialized_key() as key_file:
            scp_post_file(pulsar_path, self.path, self.ssh_user, self.ssh_host,
                          self.ssh_port, key_file)


class MessageAction:
    """ Sort of pseudo action describing "files" store in memory and
    transferred via message (HTTP, Python-call, MQ, etc...)
    """
    action_type = "message"
    staging = STAGING_ACTION_DEFAULT

    def __init__(self, contents, client=None):
        self.contents = contents
        self.client = client

    @property
    def staging_needed(self):
        return True

    @property
    def staging_action_local(self):
        # Ekkk, cannot be called if created through from_dict.
        # Shouldn't be a problem the way it is used - but is an
        # object design problem.
        return self.client.prefer_local_staging

    def to_dict(self):
        return dict(contents=self.contents, action_type=MessageAction.action_type)

    @classmethod
    def from_dict(cls, action_dict):
        return MessageAction(contents=action_dict["contents"])

    def write_to_path(self, path):
        open(path, "w").write(self.contents)


DICTIFIABLE_ACTION_CLASSES = [
    JsonTransferAction,
    RemoteCopyAction,
    RemoteTransferAction,
    RemoteTransferTusAction,
    MessageAction,
    RsyncTransferAction,
    ScpTransferAction,
    RemoteObjectStoreCopyAction
]


def from_dict(action_dict):
    action_type = action_dict.get("action_type", None)
    target_class = None
    for action_class in DICTIFIABLE_ACTION_CLASSES:
        if action_type == action_class.action_type:
            target_class = action_class
    if not target_class:
        message = "Failed to recover action from dictionary - invalid action type specified %s." % action_type
        raise Exception(message)
    if "source" in action_dict:
        action_dict.pop("path")  # remove redundant information stored for backward compatibility.
    elif "path" in action_dict:
        # legacy message received from older Pulsar client, pop the path from the dict
        # and convert it to a source.
        source = {"path": action_dict.pop("path")}
        action_dict["source"] = source
    return target_class.from_dict(action_dict)


class BasePathMapper:
    match_type: str

    def __init__(self, config):
        action_type = config.get('action', DEFAULT_MAPPED_ACTION)
        action_class = actions.get(action_type, None)
        action_kwds = action_class.action_spec.copy()
        for key, value in action_kwds.items():
            if key in config:
                action_kwds[key] = config[key]
            elif value is REQUIRED_ACTION_KWD:
                message_template = "action_type %s requires key word argument %s"
                message = message_template % (action_type, key)
                raise Exception(message)
            else:
                action_kwds[key] = value
        self.action_type = action_type
        self.action_kwds = action_kwds
        path_types_str = config.get('path_types', "*defaults*")
        path_types_str = path_types_str.replace("*defaults*", ",".join(ACTION_DEFAULT_PATH_TYPES))
        path_types_str = path_types_str.replace("*any*", ",".join(ALL_PATH_TYPES))
        self.path_types = path_types_str.split(",")
        self.file_lister = FileLister(config)

    def matches(self, path, path_type):
        path_type_matches = path_type in self.path_types
        rval = path_type_matches and self._path_matches(path)
        return rval

    def _extend_base_dict(self, **kwds):
        base_dict = dict(
            action=self.action_type,
            path_types=",".join(self.path_types),
            match_type=self.match_type
        )
        base_dict.update(self.file_lister.to_dict())
        base_dict.update(self.action_kwds)
        base_dict.update(**kwds)
        return base_dict

    def to_pattern(self):
        raise NotImplementedError()


class PathTypeOnlyMapper(BasePathMapper):
    match_type = 'path_type_only'

    def __init__(self, config):
        super().__init__(config)

    def _path_matches(self, path):
        return True

    def to_dict(self):
        return self._extend_base_dict()


class PrefixPathMapper(BasePathMapper):
    match_type = 'prefix'

    def __init__(self, config):
        super().__init__(config)
        self.prefix_path = abspath(config['path'])

    def _path_matches(self, path):
        return path is not None and path.startswith(self.prefix_path)

    def to_pattern(self):
        pattern_str = r"({}{}[^\s,\"\']+)".format(escape(self.prefix_path), escape(sep))
        return compile(pattern_str)

    def to_dict(self):
        return self._extend_base_dict(path=self.prefix_path)


class GlobPathMapper(BasePathMapper):
    match_type = 'glob'

    def __init__(self, config):
        super().__init__(config)
        self.glob_path = config['path']

    def _path_matches(self, path):
        return path is not None and fnmatch.fnmatch(path, self.glob_path)

    def to_pattern(self):
        return compile(fnmatch.translate(self.glob_path))

    def to_dict(self):
        return self._extend_base_dict(path=self.glob_path)


class RegexPathMapper(BasePathMapper):
    match_type = 'regex'

    def __init__(self, config):
        super().__init__(config)
        self.pattern_raw = config['path']
        self.pattern = compile(self.pattern_raw)

    def _path_matches(self, path):
        return path is not None and self.pattern.match(path) is not None

    def to_pattern(self):
        return self.pattern

    def to_dict(self):
        return self._extend_base_dict(path=self.pattern_raw)


MAPPER_CLASSES = [PathTypeOnlyMapper, PrefixPathMapper, GlobPathMapper, RegexPathMapper]
MAPPER_CLASS_DICT = dict(map(lambda c: (c.match_type, c), MAPPER_CLASSES))


def mappers_from_dicts(mapper_def_list):
    return list(map(lambda m: _mappper_from_dict(m), mapper_def_list))


def _mappper_from_dict(mapper_dict):
    if "path" in mapper_dict:
        map_type = mapper_dict.get('match_type', DEFAULT_PATH_MAPPER_TYPE)
    else:
        map_type = 'path_type_only'
    return MAPPER_CLASS_DICT[map_type](mapper_dict)


class FileLister:

    def __init__(self, config):
        self.depth = int(config.get("depth", "0"))

    def to_dict(self):
        return dict(
            depth=self.depth
        )

    def unstructured_map(self, path):
        depth = self.depth
        if self.depth == 0:
            return {path: basename(path)}
        else:
            while depth > 0:
                path = dirname(path)
                depth -= 1
            return {join(path, f): f for f in directory_files(path)}


DEFAULT_FILE_LISTER = FileLister(dict(depth=0))

ACTION_CLASSES: List[Type[BaseAction]] = [
    NoneAction,
    JsonTransferAction,
    RewriteAction,
    TransferAction,
    CopyAction,
    RemoteCopyAction,
    RemoteTransferAction,
    RemoteTransferTusAction,
    RemoteObjectStoreCopyAction,
    RsyncTransferAction,
    ScpTransferAction,
]
actions = {clazz.action_type: clazz for clazz in ACTION_CLASSES}


__all__ = (
    'FileActionMapper',
    'path_type',
    'from_dict',
    'MessageAction',
    'RemoteTransferAction',  # For testing
)
