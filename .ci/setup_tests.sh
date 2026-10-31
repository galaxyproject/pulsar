#!/bin/bash

set -e
set -v

sudo add-apt-repository ppa:natefoo/slurm-drmaa -y
sudo apt update
sudo apt install -y libxml2-dev libxslt1-dev libcurl4-openssl-dev openssh-server
#pip install -r requirements$REQUIREMENTS_SUFFIX.txt --use-mirrors || true
#pip install -r dev-requirements.txt --use-mirrors || true
#pip install coveralls  # Required fro coveralls reporting.
sudo apt install -y slurm-wlm slurm-wlm-torque munge slurm-drmaa1 slurm-drmaa-dev
sudo apt install -y libswitch-perl libgnutls28-dev # A missing dependency of slurm-llnl-torque

# DEBIAN_FRONTEND=noninteractive sudo apt install htcondor ## htcondor installation

sudo service munge start
sudo python scripts/configure_test_slurm.py
echo "export DRMAA_LIBRARY_PATH=/usr/lib/slurm-drmaa/lib/libdrmaa.so" >> local_env.sh
#echo ". $VIRTUAL_ENV/bin/activate" >> local_env.sh
echo "umask 002" >> local_env.sh
# tox 4.67.5+ refuses to stage packages under a group-writable .tox, so create
# its staging path before the umask above applies to the test run.
install -d -m 755 .tox .tox/.tmp .tox/.tmp/package
sudo useradd --home-dir /home/u1 --shell /bin/bash --create-home --comment TEST,,, --groups $(id -gn) u1  ## Create user for run-as-user test.
mkdir -p ~/.ssh && cp test_data/testkey.pub ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
