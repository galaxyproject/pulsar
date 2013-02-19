#!/bin/bash

## Usage:
## Start LWR server as daemon process:
##   run.sh --daemon   
## Stop LWR daemon process:
##   run.sh --stop-daemon

# Ensure working directory is lwr project. 
PROJECT_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $PROJECT_DIRECTORY

if [ -d .venv ]; 
then
    . .venv/bin/activate
fi

paster serve server.ini "$@"
