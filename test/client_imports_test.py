import pickle
import subprocess
import sys
import textwrap
from importlib import import_module

import pytest


def test_staging_constants_import_without_site_packages():
    code = textwrap.dedent("""\
        import sys
        from pulsar.client.staging import (
            COMMAND_VERSION_FILENAME,
            DEFAULT_DYNAMIC_COLLECTION_PATTERN,
            EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN,
        )

        assert COMMAND_VERSION_FILENAME == "COMMAND_VERSION"
        assert DEFAULT_DYNAMIC_COLLECTION_PATTERN
        assert EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN == [r"outputs_populated/.*"]
        assert {name for name in sys.modules if name.startswith("pulsar")} == {
            "pulsar", "pulsar.client", "pulsar.client.staging",
        }
    """)
    subprocess.run([sys.executable, '-S', '-c', code], check=True)


@pytest.mark.parametrize('module', [
    'pulsar.client.exceptions',
    'pulsar.client.client',
    'pulsar.client.manager',
    'pulsar.client.coexecution',
    'pulsar.client.container_job_config',
    'pulsar.client.staging.inputs',
    'pulsar.client.path_mapper',
])
def test_standard_modules_do_not_import_backend_sdks_or_tool_parser(module):
    code = textwrap.dedent("""\
        import sys
        from importlib import import_module

        forbidden = (
            "google.cloud.batch", "pydantic", "pydantictes", "pykube",
            "galaxy.tool_util.parser", "pulsar.client.gcp", "pulsar.client.tes",
            "pulsar.client.kubernetes", "pulsar.client.coexecution_manager",
        )

    """) + f'\nimport_module({module!r})\n' + textwrap.dedent("""\
        assert not [name for name in sys.modules if name.startswith(forbidden)]
    """)
    subprocess.run([sys.executable, '-c', code], check=True)


@pytest.mark.parametrize(('module', 'forbidden'), [
    ('pulsar.client.gcp', ('pydantictes', 'pykube')),
    ('pulsar.client.tes', ('google.cloud.batch', 'pykube')),
    ('pulsar.client.kubernetes', ('google.cloud.batch', 'pydantictes', 'pydantic')),
])
def test_backends_do_not_import_other_backend_sdks(module, forbidden):
    code = textwrap.dedent("""\
        import sys
        from importlib import import_module
    """) + f'forbidden = {forbidden!r}\nimport_module({module!r})\n' + textwrap.dedent("""\
        assert not [name for name in sys.modules if name.startswith(forbidden)]
    """)
    subprocess.run([sys.executable, '-c', code], check=True)


@pytest.mark.parametrize('package', ['pulsar.client', 'pulsar.client.staging'])
def test_compatibility_discovery_does_not_load_implementations(package):
    code = textwrap.dedent("""\
        import sys
        from importlib import import_module
    """) + f'package = import_module({package!r})\n' + textwrap.dedent("""\
        before = set(sys.modules)
        assert set(package.__all__) <= set(dir(package))
        assert not hasattr(package, "nonexistent_public_name")
        assert set(sys.modules) == before
    """)
    subprocess.run([sys.executable, '-S', '-c', code], check=True)


@pytest.mark.parametrize(('name', 'module'), [
    ('CLIENT_INPUT_PATH_TYPES', 'staging.inputs'),
    ('EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN', 'staging'),
    ('ClientInput', 'staging.inputs'),
    ('ClientInputs', 'staging.inputs'),
    ('ClientJobDescription', 'staging.models'),
    ('ClientOutputs', 'staging.models'),
    ('OutputNotFoundException', 'exceptions'),
    ('PathMapper', 'path_mapper'),
    ('PulsarClientTransportError', 'exceptions'),
    ('PulsarOutputs', 'staging.models'),
    ('build_client_manager', 'coexecution_manager'),
    ('finish_job', 'staging.down'),
    ('submit_job', 'staging.up'),
    ('url_to_destination_params', 'destination'),
])
def test_existing_client_exports_are_actual_implementation_objects(name, module):
    package = import_module('pulsar.client')
    exported = getattr(package, name)
    assert exported is getattr(import_module(f'pulsar.client.{module}'), name)
    assert vars(package)[name] is exported


@pytest.mark.parametrize(('name', 'module'), [
    ('CLIENT_INPUT_PATH_TYPES', 'inputs'),
    ('ClientInput', 'inputs'),
    ('ClientInputs', 'inputs'),
    ('ClientJobDescription', 'models'),
    ('ClientOutputs', 'models'),
    ('DynamicFileSourceType', 'models'),
    ('PulsarOutputs', 'models'),
])
def test_existing_staging_exports_are_actual_implementation_objects(name, module):
    package = import_module('pulsar.client.staging')
    exported = getattr(package, name)
    assert exported is getattr(import_module(f'pulsar.client.staging.{module}'), name)
    assert vars(package)[name] is exported
    if name != 'CLIENT_INPUT_PATH_TYPES':
        legacy_class_pickle = f'cpulsar.client.staging\n{name}\n.'.encode()
        assert pickle.loads(legacy_class_pickle) is exported


def test_staging_object_pickle_compatibility():
    staging = import_module('pulsar.client.staging')
    outputs = staging.ClientOutputs(output_files=['output.txt'])
    serialized = pickle.dumps(outputs, protocol=0)
    legacy_serialized = serialized.replace(b'pulsar.client.staging.models\n', b'pulsar.client.staging\n')
    assert legacy_serialized != serialized
    for payload in (serialized, legacy_serialized):
        restored = pickle.loads(payload)
        assert type(restored) is staging.ClientOutputs
        assert restored.output_files == ['output.txt']


def test_legacy_exception_path():
    exception = import_module('pulsar.client.exceptions').OutputNotFoundException
    assert import_module('pulsar.client.client').OutputNotFoundException is exception
    assert pickle.loads(b'cpulsar.client.client\nOutputNotFoundException\n.') is exception
