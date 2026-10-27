import subprocess

from pulsar.managers.util.job_script import (
    ExitHandlers,
    job_script,
)


def _run_job_script(tmp_path, command, exit_handler_commands, **kwds):
    handlers = ExitHandlers()
    for exit_handler_command in exit_handler_commands:
        handlers.add(exit_handler_command)
    script = job_script(
        working_directory=str(tmp_path),
        metadata_directory=str(tmp_path),
        command=command,
        exit_handler_setup=handlers.render(),
        prepare_dirs_statement="",
        integrity_injection="",
        **kwds,
    )
    script_path = tmp_path / "job.sh"
    script_path.write_text(script)
    return subprocess.run(["/bin/bash", str(script_path)], cwd=tmp_path)


def test_command_exit_trap_does_not_replace_exit_handlers(tmp_path):
    log = tmp_path / "exit.log"
    # Mirrors Galaxy's DockerContainer.containerize_command trap.
    command = f"_on_exit() {{\n  echo GALAXY >> {log}\n}}\ntrap _on_exit EXIT\necho ran"
    result = _run_job_script(tmp_path, command, [f"echo PULSAR >> {log}"])
    assert result.returncode == 0
    assert log.read_text().split() == ["GALAXY", "PULSAR"]


def test_command_exit_status_kept_with_exit_handlers(tmp_path):
    post_log = tmp_path / "post.log"
    result = _run_job_script(
        tmp_path, "exit 7", ["true"], instrument_post_commands=f"echo POST >> {post_log}"
    )
    assert result.returncode == 7
    assert not post_log.exists()
