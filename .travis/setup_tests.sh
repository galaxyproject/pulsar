#!/bin/bash

set -e
set -v

sudo apt-get update
sudo apt-get install libxml2-dev libxslt1-dev libcurl3 python-pycurl openssh-server
#pip install -r requirements$REQUIREMENTS_SUFFIX.txt --use-mirrors || true
#pip install -r dev-requirements.txt --use-mirrors || true
pip install coveralls  # Required fro coveralls reporting.
sudo apt-get install slurm-llnl slurm-llnl-torque # slurm-drmaa1 slurm-drmaa-dev
sudo apt-get install libslurm23
wget http://launchpadlibrarian.net/104075475/slurm-drmaa1_1.0.4-3_amd64.deb
sudo dpkg -i slurm-drmaa1_1.0.4-3_amd64.deb
wget http://launchpadlibrarian.net/104075474/slurm-drmaa-dev_1.0.4-3_amd64.deb
sudo dpkg -i slurm-drmaa-dev_1.0.4-3_amd64.deb
sudo /usr/sbin/create-munge-key
sudo service munge start
sudo python scripts/configure_test_slurm.py
echo "export DRMAA_LIBRARY_PATH=/usr/lib/libdrmaa.so" >> local_env.sh
echo ". $VIRTUAL_ENV/bin/activate" >> local_env.sh
sudo adduser --quiet --disabled-password --gecos TEST u1  ## Create user for run-as-user test.  
mkdir -p ~/.ssh && cp test_data/testkey.pub ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
