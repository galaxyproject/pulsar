#!/bin/bash

usage() {
cat << EOF
Usage: ${0##*/} [-i] /path/to/galaxy...
Sync LWR shared modules to those same modules in Galaxy directory (or vice versa if -i).

EOF
}

if [ $# -lt 1 ]; then
    usage
    exit 1
fi

invert=0
OPTIND=1
while getopts ":i" opt; do
    case "$opt" in
        h)
            usage
            exit 0
            ;;
        i)
            invert=1
            ;;
        '?')
            usage >&2
            exit 1
            ;;
    esac
done
shift "$((OPTIND-1))" # Shift off the options and optional --.

LWR_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
GALAXY_DIRECTORY=$1
GALAXY_RUNNERS_DIRECTORY=$GALAXY_DIRECTORY/lib/galaxy/jobs/runners

if [ "$invert" -ne "1" ];
then
    rm -rf $GALAXY_RUNNERS_DIRECTORY/util
    cp -r $LWR_DIRECTORY/lwr/managers/util $GALAXY_RUNNERS_DIRECTORY
else
    rm -rf $LWR_DIRECTORY/lwr/managers/util
    cp -r $GALAXY_RUNNERS_DIRECTORY/util $LWR_DIRECTORY/lwr/managers
fi
