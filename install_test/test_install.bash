#!/bin/bash

set -e

shopt -s nullglob
PULSAR_INSTALL_TARGET="${PULSAR_INSTALL_TARGET:-pulsar-app}"
PLANEMO_INSTALL_TARGET="${PLANEMO_INSTALL_TARGET:-planemo==0.29.1}"

echo "Begin Pulsar checks"

SCRIPT_DIR="$( cd "$(dirname "$0")" ; pwd )"
PROJECT_DIR="$SCRIPT_DIR/.."

TEMP_DIR=`mktemp -d`
echo "Setting up test directory $TEMP_DIR"
cd "$TEMP_DIR"

mkdir pulsar
cd pulsar
echo "Setting up virtualenv for Pulsar"
virtualenv venv
. venv/bin/activate # .venv\Scripts\activate if Windows
echo "Installing Pulsar using 'pip install $PULSAR_INSTALL_TARGET'"
pip install $PULSAR_INSTALL_TARGET
echo "Running pulsar-config with default arguments"
pulsar-config
echo "Starting Pulsar in daemon mode."
pulsar --daemon
echo "Waiting for Pulsar to start."
sleep 2
echo "Running a standalone Pulsar job."
pulsar-check # runs a test job
echo "Stopping Pulsar daemon."
pulsar --stop-daemon
echo "End Pulsar Checks"

echo "Testing Pulsar-Galaxy Interaction"
echo "Starting Pulsar in daemon mode."
pulsar --daemon
echo "Waiting for Pulsar to start."
sleep 2

cd ..

echo "Creating a virtual environment for Planemo to drive a test job."
virtualenv planemo-venv
. planemo-venv/bin/activate
echo "Installing Pulsar using 'pip install $PLANEMO_INSTALL_TARGET'"
pip install "$PLANEMO_INSTALL_TARGET"
echo "Setting up Planemo test tools."
planemo project_init --template=demo test_tools
echo "Running tool tests with Planemo through Pulsar"
: ${GALAXY_ROOT:=""}
galaxy_root_args=""
if [ -d "$GALAXY_ROOT" ];
then
    galaxy_root_args="--galaxy_root $GALAXY_ROOT"
fi
planemo --verbose test $galaxy_root_args --job_config_file "$SCRIPT_DIR/galaxy_job_conf.xml" test_tools/cat.xml
echo "Tests complete."

cd pulsar
. venv/bin/activate
echo "Stopping Pulsar daemon."
pulsar --stop-daemon
echo "Ending tests."
