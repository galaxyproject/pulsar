#!/bin/bash

SCRIPTS_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
"$SCRIPTS_DIRECTORY/execute_script.bash" pulsar/scripts/chown_working_directory.py "$@"
