#!/bin/bash

PYTHON_SCRIPT="$1"
shift

# Ensure working directory is pulsar project.  
SCRIPTS_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIRECTORY=$SCRIPTS_DIRECTORY/..
cd $PROJECT_DIRECTORY

PULSAR_LOCAL_ENV=${PULSAR_LOCAL_ENV:-$PROJECT_DIRECTORY/local_env.sh}
export PULSAR_LOCAL_ENV

PULSAR_VIRTUALENV=${PULSAR_VIRTUALENV:-$PROJECT_DIRECTORY/.venv}
export PULSAR_VIRTUALENV

if [ -e $PULSAR_LOCAL_ENV ];
then
    # Setup Python, DRMAA_LIBRARY_PATH, etc...
    . $PULSAR_LOCAL_ENV
fi

if [ -d $PULSAR_VIRTUALENV ];
then
    . $PULSAR_VIRTUALENV/bin/activate
fi

export PYTHONPATH=.:$PYTHONPATH
python $PYTHON_SCRIPT "$@"