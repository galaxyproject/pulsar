#!/bin/bash

## Usage:
## Start LWR server as daemon process (paster or circus):
##   run.sh --daemon   
## Stop LWR daemon process (paster):
##   run.sh --stop-daemon
## Stop LWR daemon process (circusd):
##   circusctl quit


# Ensure working directory is lwr project. 
PROJECT_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $PROJECT_DIRECTORY

if [ -e $PROJECT_DIRECTORY/local_env.sh ];
then 
    . $PROJECT_DIRECTORY/local_env.sh
fi

if [ -d .venv ]; 
then
    . .venv/bin/activate
fi

# If TEST_GALAXY_LIBS is set, this script will attempt to verify
# Galaxy is properly placed on the LWR's PYTHONPATH before starting
# the server.
if [ -n "$TEST_GALAXY_LIBS" ];
then
    python -c 'import sys; sys.path.pop(0); from galaxy import eggs'
    result=$?
    if [ "$result" == "0" ];
    then
        echo "Galaxy loaded properly."
    else
        echo "Failed to setup Galaxy environment properly, is GALAXY_HOME ($GALAXY_HOME) a valid Galaxy instance."
        exit $result
    fi
fi

# Setup default configuration files (if needed).
for file in 'server.ini'; do
    if [ ! -f "$file" -a -f "$file.sample" ]; then
        echo "Initializing $file from `basename $file.sample`"
        cp "$file.sample" "$file"
    fi
done

if hash circusd 2>/dev/null; then
    circusd server.ini "$@"
elif hash chaussette 2>/dev/null; then
    chaussette paste:server.ini "$@"
else
    paster serve server.ini "$@"
fi