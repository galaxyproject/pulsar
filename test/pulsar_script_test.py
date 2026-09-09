import os
import subprocess
from pathlib import Path


def test_webless_mode_forwards_arguments_unchanged(tmp_path):
    captured_args = tmp_path / "args"
    pulsar_main = tmp_path / "pulsar-main"
    pulsar_main.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$PULSAR_ARG_CAPTURE\"\n")
    pulsar_main.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = "%s%s%s" % (tmp_path, os.pathsep, env["PATH"])
    env["PULSAR_ARG_CAPTURE"] = str(captured_args)
    pulsar_script = Path(__file__).parents[1] / "scripts" / "pulsar"
    forwarded_args = [
        "--daemon",
        "--pid", "custom pid",
        "--log-file", "custom log",
        "--custom-option", "custom value",
    ]

    subprocess.run(
        [str(pulsar_script), "--mode", "webless"] + forwarded_args,
        cwd=str(tmp_path),
        env=env,
        check=True,
    )

    assert captured_args.read_text().splitlines() == forwarded_args
