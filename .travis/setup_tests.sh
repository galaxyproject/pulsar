#!/bin/bash

set -e
set -v

sudo apt-get update
sudo apt-get install libxml2-dev libxslt1-dev libcurl3 python-pycurl openssh-server
#pip install -r requirements$REQUIREMENTS_SUFFIX.txt --use-mirrors || true
#pip install -r dev-requirements.txt --use-mirrors || true
pip install coveralls  # Required fro coveralls reporting.
sudo apt-get install slurm-llnl slurm-llnl-torque # slurm-drmaa1 slurm-drmaa-dev
sudo apt-get install libswitch-perl  # A missing dependency of slurm-llnl-torque
wget https://depot.galaxyproject.org/deb/slurm-drmaa1_1.2.0-dev.57ebc0c_amd64.deb
sudo dpkg -i slurm-drmaa1_1.2.0-dev.57ebc0c_amd64.deb
wget https://depot.galaxyproject.org/deb/slurm-drmaa-dev_1.2.0-dev.57ebc0c_amd64.deb
sudo dpkg -i slurm-drmaa-dev_1.2.0-dev.57ebc0c_amd64.deb
sudo /usr/sbin/create-munge-key
sudo service munge start
sudo python scripts/configure_test_slurm.py
echo "export DRMAA_LIBRARY_PATH=/usr/lib/slurm-drmaa/lib/libdrmaa.so" >> local_env.sh
echo ". $VIRTUAL_ENV/bin/activate" >> local_env.sh
sudo useradd --home-dir /home/u1 --shell /bin/bash --create-home --comment TEST,,, --groups travis u1  ## Create user for run-as-user test.
mkdir -p ~/.ssh && cp test_data/testkey.pub ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
