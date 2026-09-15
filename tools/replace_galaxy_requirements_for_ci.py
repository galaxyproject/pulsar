#!/usr/bin/env python
import glob
import os
import subprocess

PULSAR_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
GALAXY_DIR = os.path.normpath(os.path.join(PULSAR_ROOT, "..", "galaxy"))

subprocess.run(["python", "-m", "pip", "install",  "build"], check=True, stdout=subprocess.PIPE)
env = os.environ
env["PULSAR_GALAXY_LIB"] = "1"
subprocess.run(["python", "-m", "build", "--wheel"], env=env, check=True, stdout=subprocess.PIPE)

lib_wheel_path = glob.glob(f'{PULSAR_ROOT}/dist/pulsar_galaxy_lib-*-none-any.whl')[0]
print(f"Replacing Galaxy pulsar-galaxy-lib requirements in {GALAXY_DIR} with {lib_wheel_path}")

for req in ["lib/galaxy/dependencies/pinned-requirements.txt", "lib/galaxy/dependencies/dev-requirements.txt"]:
    req_abs_path = os.path.join(GALAXY_DIR, req)
    with open(req_abs_path) as f:
        lines = f.read()
    new_lines = []
    for line in lines.splitlines():
        if line.startswith("pulsar-galaxy-lib"):
            line = lib_wheel_path
        new_lines.append(line)
    with open(req_abs_path, "w") as f:
        f.write("\n".join(new_lines))
