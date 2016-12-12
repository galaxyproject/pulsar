#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$(dirname "$0")" ; pwd )"
. "$SCRIPT_DIR/common_functions.bash"

init_temp_dir

init_pulsar

cd pulsar
echo "Running pulsar-config with --auto_conda"
pulsar-config --auto_conda

cd ..

check_pulsar

init_planemo "conda_testing"

run_planemo --job_config_file "$SCRIPT_DIR/galaxy_job_conf.xml" test_tools/bwa.xml

stop_pulsar
