#!/bin/bash
## ./update_galaxy_client.sh /path/to/galaxy

if [ $# -lt 1 ]; then
    echo "Usage: $0 /path/to/galaxy"
    exit 1
fi
LWR_DIRECTORY="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
GALAXY_DIRECTORY=$1
GALAXY_RUNNERS_DIRECTORY=$GALAXY_DIRECTORY/lib/galaxy/jobs/runners

rm -rf $GALAXY_RUNNERS_DIRECTORY/util
cp -r $LWR_DIRECTORY/lwr/managers/util $GALAXY_RUNNERS_DIRECTORY
