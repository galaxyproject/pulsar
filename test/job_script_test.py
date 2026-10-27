import subprocess

from pulsar.managers.util.job_script import (
    ExitHandlers,
    job_script,
)


def test_command_exit_trap_does_not_replace_exit_handlers(tmp_path):
    log = tmp_path / "exit.log"
    handlers = ExitHandlers()
    handlers.add(f"echo PULSAR >> {log}")
    # Mirrors Galaxy's DockerContainer.containerize_command trap.
    command = f"_on_exit() {{\n  echo GALAXY >> {log}\n}}\ntrap _on_exit EXIT\necho ran"
    script = job_script(
        working_directory=str(tmp_path),
        metadata_directory=str(tmp_path),
        command=command,
        exit_handler_setup=handlers.render(),
        prepare_dirs_statement="",
        integrity_injection="",
    )
    script_path = tmp_path / "job.sh"
    script_path.write_text(script)
    subprocess.run(["/bin/bash", str(script_path)], check=True, cwd=tmp_path)
    assert log.read_text().split() == ["GALAXY", "PULSAR"]
