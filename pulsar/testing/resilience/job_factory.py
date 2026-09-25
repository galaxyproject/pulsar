"""Build setup-message payloads for resilience scenarios.

The scenarios don't run real Galaxy tools — they just need a job that runs
a deterministic shell command and surfaces input/output staging through
mock-galaxy's HTTP endpoints. This factory keeps the wire format consistent
across scenarios.

File-staging URLs target the mock_galaxy mount of simple-job-files at
``/api/jobs/_resilience/files`` (Galaxy job-files API shape: ``?path=``
query param, multipart POST). The path query value is the absolute path
inside the mock-galaxy container's shared volume (``GALAXY_FILES_ROOT``).
"""
import uuid
from urllib.parse import urlencode

GALAXY_URL = "http://toxiproxy:8088"
# Trailing slash matters: Starlette's mount issues a 307 trailing-slash
# redirect for the bare prefix, which `requests` follows correctly but
# costs an extra round-trip per staging op. Use the canonical form.
FILES_API = "/api/jobs/_resilience/files/"
GALAXY_FILES_ROOT = "/galaxy/files"


def files_url(galaxy_filename: str, file_type: str = "input") -> str:
    """URL Pulsar's client should use to GET/POST a staged file in the mock.

    ``galaxy_filename`` is the basename inside ``GALAXY_FILES_ROOT``. This is
    the in-network address; the host reaches the same mount through
    ``localhost``, which is also toxiproxy - mock-galaxy has no bypass.
    """
    qs = urlencode({"path": f"{GALAXY_FILES_ROOT}/{galaxy_filename}", "file_type": file_type})
    return f"{GALAXY_URL}{FILES_API}?{qs}"


def make_setup_message(
    job_id=None,
    command_line="echo hello",
    input_files=None,
    output_files=None,
):
    """Build a ``setup`` message body matching pulsar.client.setup_handler.

    Args:
        job_id: deterministic id (default: random uuid)
        command_line: shell command to run
        input_files: list of ``(local_name, galaxy_filename)`` pairs.
            ``local_name`` is the path Pulsar stages the input under;
            ``galaxy_filename`` is the basename inside ``GALAXY_FILES_ROOT``
            on the mock-galaxy side. The factory builds the simple-job-files
            URL.
        output_files: names of files the job writes into its outputs
            directory, to be staged back. One name, not a pair -
            ``PulsarOutputs.has_output_file`` matches by basename, so both
            sides necessarily share it.

    Returns:
        Dict ready to POST to mock-galaxy's ``/_publish_setup`` endpoint.
    """
    job_id = job_id or uuid.uuid4().hex[:12]
    setup_actions = []
    if input_files:
        for local_name, galaxy_filename in input_files:
            setup_actions.append({
                "name": local_name,
                "type": "input",
                "action": {
                    "action_type": "remote_transfer",
                    "url": files_url(galaxy_filename, file_type="input"),
                    "source": {"path": local_name},
                    "path": local_name,
                },
            })
    # Outputs are not staged by explicit actions the way inputs are - Pulsar's
    # postprocess builds them from ``client_outputs`` plus the action mapper's
    # files endpoint, so naming them here is what makes stage-out happen.
    client_outputs = {
        "output_files": [
            f"{GALAXY_FILES_ROOT}/{name}" for name in output_files or []
        ],
    }

    return {
        "job_id": job_id,
        "command_line": command_line,
        "setup": True,
        "remote_staging": {
            "setup": setup_actions,
            "action_mapper": {
                "default_action": "remote_transfer",
                "files_endpoint": f"{GALAXY_URL}{FILES_API}",
            },
            "client_outputs": client_outputs,
        },
    }
