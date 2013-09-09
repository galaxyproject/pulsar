#!/bin/bash

PYTHON_SCRIPT="$1"
shift

# Ensure working directory is lwr project.  
SCRIPTS_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIRECTORY=$SCRIPTS_DIRECTORY/..
cd $PROJECT_DIRECTORY

if [ -e local_env.sh ];
then
    # Setup Python, DRMAA_LIBRARY_PATH, etc...
    . local_env.sh
elif [ -d .venv ];
then
    . .venv/bin/activate
fi

export PYTHONPATH=.:$PYTHONPATH
python $PYTHON_SCRIPT "$@"