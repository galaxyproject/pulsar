#!/bin/bash

# Startup slurm
service munge start
python /usr/sbin/configure_slurm.py
service slurm-llnl start

# Startup rabbitmq
service rabbitmq-server start

## Condor doesn't allow submitting jobs as root - tests should run as different
## user anyway.
## # Startup condor
## service condor start

export PULSAR_LOCAL_ENV=/usr/share/pulsar/container_env.sh
export PULSAR_VIRTUALENV=/usr/share/pulsar/venv

. $PULSAR_LOCAL_ENV

# Run the tests...
cd /pulsar; pyflakes pulsar test && flake8 --exclude test_tool_deps.py --max-complexity 9 pulsar test && nosetests