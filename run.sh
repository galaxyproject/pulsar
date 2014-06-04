#!/bin/bash

show_help() {
cat <<EOF
Usage:

${0##*/} --daemon
    Start LWR server as daemon process (paster or circus):
${0##*/} --stop-daemon
    Stop LWR daemon process (paster/chaussette) with circus use
    'circusctl quit'
EOF
}

MODE=""
while :
do
    case "$1" in
      -h|--help|-\?) 
          show_help
          exit 0
          ;;
      -m|--mode)
          if [ $# -gt 1 ]; then
              MODE=$2
              shift 2
          else 
              echo "--mode requires explicit argument" 1>&2
              exit 1
          fi
          ;;

      --) 
          shift
          break
          ;;
      *)
          break;
          ;;
    esac
done

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

if [ -z "$MODE" ]; 
then
    if hash uwsgi 2>/dev/null; then
        MODE="uwsgi"
    elif hash circusd 2>/dev/null; then
        MODE="circusd"
    elif hash chaussette 2>/dev/null; then
        MODE="chaussette"
    else
        MODE="paster"
    fi
fi

if [ "$MODE" == "uwsgi" ]; then
    uwsgi --ini-paste server.ini "$@"
elif [ "$MODE" == "circusd" ]; then
    circusd server.ini "$@"
elif [ "$MODE" == "chaussette" ]; then
    echo "Attempting to use chaussette instead of paster, you must specify port on command-line (--port 8913)."
    chaussette paste:server.ini "$@"
elif [ "$MODE" == "paster" ]; then
    paster serve server.ini "$@"
else
    echo "Unknown mode passed to --mode argument." 1>&2
    exit 1
fi
