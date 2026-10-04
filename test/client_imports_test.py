import pickle
import subprocess
import sys
import textwrap
from importlib import import_module

import pytest

from pulsar.client.staging.models import ClientOutputs


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
def test_packages_have_no_lazy_exports_or_client_dependencies(package):
    code = textwrap.dedent("""\
        import sys
        from importlib import import_module
    """) + f'package = import_module({package!r})\n' + textwrap.dedent("""\
        assert not hasattr(package, "__getattr__")
        assert not hasattr(package, "ClientJobDescription")
        assert not hasattr(package, "build_client_manager")
        assert {name for name in sys.modules if name.startswith("pulsar")} <= {
            "pulsar", "pulsar.client", "pulsar.client.staging",
        }
    """)
    subprocess.run([sys.executable, '-S', '-c', code], check=True)


def test_staging_object_pickle_roundtrip():
    outputs = ClientOutputs(output_files=['output.txt'])
    restored = pickle.loads(pickle.dumps(outputs))
    assert type(restored) is ClientOutputs
    assert restored.output_files == ['output.txt']


def test_legacy_exception_path():
    exception = import_module('pulsar.client.exceptions').OutputNotFoundException
    assert import_module('pulsar.client.client').OutputNotFoundException is exception
    assert pickle.loads(b'cpulsar.client.client\nOutputNotFoundException\n.') is exception
