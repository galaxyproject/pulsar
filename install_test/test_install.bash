#!/bin/bash

set -e

echo "Start Pulsar Checks"

SCRIPT_DIR="$( cd "$(dirname "$0")" ; pwd )"
PROJECT_DIR="$SCRIPT_DIR/.."

TEMP_DIR=`mktemp -d`
cd "$TEMP_DIR"

mkdir pulsar
cd pulsar
virtualenv venv
. venv/bin/activate # .venv\Scripts\activate if Windows
pip install pulsar-app
pulsar-config
pulsar --daemon # just pulsar if Windows
sleep 2
pulsar-check # runs a test job
pulsar --stop-daemon

echo "End Pulsar Checks"
echo "Testing Galaxy Interactions"

pulsar --daemon # just pulsar if Windows
sleep 2

cd ..

virtualenv planemo-venv
. planemo-venv/bin/activate
pip install planemo
planemo project_init --template=demo test_tools
planemo --verbose test --job_config_file "$SCRIPT_DIR/galaxy_job_conf.xml" test_tools
pulsar --stop-daemon

echo "Ending tests.

