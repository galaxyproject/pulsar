#!/bin/bash

# Ensure working directory is lwr project. 
PROJECT_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $PROJECT_DIRECTORY

. .venv/bin/activate
paster serve server.ini "$@"
