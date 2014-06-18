#!/bin/bash

usage() {
cat << EOF
Usage: ${0##*/} [-i] /path/to/galaxy...
Sync Pulsar shared modules to those same modules in Galaxy directory (or vice versa if -i).

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

PULSAR_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
GALAXY_DIRECTORY=$1
GALAXY_LIB_DIR=$GALAXY_DIRECTORY/lib/galaxy
GALAXY_RUNNERS_DIRECTORY=$GALAXY_LIB_DIR/jobs/runners

if [ "$invert" -ne "1" ];
then
    rm -rf $GALAXY_RUNNERS_DIRECTORY/util
    cp -r $PULSAR_DIRECTORY/pulsar/managers/util $GALAXY_RUNNERS_DIRECTORY

    rm -rf $GALAXY_LIB_DIR/objectstore 
    cp -r $PULSAR_DIRECTORY/galaxy/objectstore $GALAXY_LIB_DIR

    rm -rf $GALAXY_LIB_DIR/tools/deps
    cp -r $PULSAR_DIRECTORY/galaxy/tools/deps $GALAXY_LIB_DIR/tools

    rm -rf $GALAXY_LIB_DIR/jobs/metrics
    cp -r $PULSAR_DIRECTORY/galaxy/jobs/metrics $GALAXY_LIB_DIR/jobs

else
    rm -rf $PULSAR_DIRECTORY/pulsar/managers/util
    cp -r $GALAXY_RUNNERS_DIRECTORY/util $PULSAR_DIRECTORY/pulsar/managers

    rm -rf $PULSAR_DIRECTORY/galaxy/objectstore
    cp -r $GALAXY_LIB_DIR/objectstore $PULSAR_DIRECTORY/galaxy

    rm -rf $PULSAR_DIRECTORY/galaxy/tools/deps
    cp -r $GALAXY_LIB_DIR/tools/deps $PULSAR_DIRECTORY/galaxy/tools

    rm -rf $PULSAR_DIRECTORY/galaxy/jobs/metrics
    cp -r $GALAXY_LIB_DIR/jobs/metrics $PULSAR_DIRECTORY/galaxy/jobs

fi
