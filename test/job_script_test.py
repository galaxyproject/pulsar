import os
import subprocess

from pulsar.managers.util.job_script import (
    ExitHandlers,
    job_script,
)

# Shape of Galaxy's DockerContainer.containerize_command output.
GALAXY_DOCKER_COMMAND = """_on_exit() {
  docker kill job_container &> /dev/null
}
trap _on_exit EXIT
docker inspect busybox > /dev/null 2>&1
[ $? -ne 0 ] && docker pull busybox > /dev/null 2>&1

docker run --name job_container --rm busybox echo tool-ran"""


def _render(tmp_path, command, exit_handler_commands, **kwds):
    handlers = ExitHandlers()
    for exit_handler_command in exit_handler_commands:
        handlers.add(exit_handler_command)
    return job_script(
        working_directory=str(tmp_path),
        metadata_directory=str(tmp_path),
        command=command,
        exit_handler_setup=handlers.render(),
        prepare_dirs_statement="",
        integrity_injection="",
        **kwds,
    )


def _run(tmp_path, script, env=None):
    script_path = tmp_path / "job.sh"
    script_path.write_text(script)
    return subprocess.run(["/bin/bash", str(script_path)], cwd=tmp_path, env=env)


def test_galaxy_docker_trap_does_not_replace_exit_handlers(tmp_path):
    log = tmp_path / "exit.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(f'#!/bin/sh\necho "DOCKER $1" >> "{log}"\n')
    docker.chmod(0o755)
    script = _render(tmp_path, GALAXY_DOCKER_COMMAND, [f'echo UMOUNT >> "{log}"'])
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    result = _run(tmp_path, script, env=env)
    assert result.returncode == 0
    assert log.read_text().splitlines() == ["DOCKER inspect", "DOCKER run", "DOCKER kill", "UMOUNT"]


def test_command_exit_status_kept_with_exit_handlers(tmp_path):
    post_log = tmp_path / "post.log"
    script = _render(tmp_path, "exit 7", ["true"], instrument_post_commands=f'echo POST >> "{post_log}"')
    assert _run(tmp_path, script).returncode == 7
    assert not post_log.exists()


def test_manager_return_code_written_with_exit_handlers(tmp_path):
    rc_path = tmp_path / "return_code"
    # Suffix appended by DirectoryBaseManager._expand_command_line.
    command = f"false; return_code=$?; echo $return_code > {rc_path};"
    script = _render(tmp_path, command, ["true"])
    assert _run(tmp_path, script).returncode == 0
    assert rc_path.read_text().strip() == "1"


def test_command_not_wrapped_without_exit_handlers(tmp_path):
    script = _render(tmp_path, "trap _on_exit EXIT\nuptime", [])
    assert "\n\ntrap _on_exit EXIT\nuptime\n" in script
