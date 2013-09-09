#!/bin/bash

PYTHON_SCRIPT="$1"
shift

# Ensure working directory is lwr project.  
SCRIPTS_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIRECTORY=$SCRIPTS_DIRECTORY/..
cd $PROJECT_DIRECTORY

if [ -d .venv ];
then
    . .venv/bin/activate
fi

python $PYTHON_SCRIPT "$@"