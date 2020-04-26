#!/bin/bash

set -e
set -v

sudo apt update
sudo apt install -y libxml2-dev libxslt1-dev libcurl3 python-pycurl openssh-server
#pip install -r requirements$REQUIREMENTS_SUFFIX.txt --use-mirrors || true
#pip install -r dev-requirements.txt --use-mirrors || true
pip install coveralls  # Required fro coveralls reporting.
sudo apt install -y slurm-wlm slurm-wlm-torque # slurm-drmaa1 slurm-drmaa-dev
sudo apt install -y libswitch-perl  # A missing dependency of slurm-llnl-torque

wget http://ftp.us.debian.org/debian/pool/main/s/slurm-llnl/libslurm33_18.08.5.2-1+deb10u1_amd64.deb
wget http://ftp.us.debian.org/debian/pool/main/s/slurm-llnl/libslurmdb33_18.08.5.2-1+deb10u1_amd64.deb
wget https://depot.galaxyproject.org/apt/pool/main/s/slurm-drmaa/slurm-drmaa1_1.1.1-1+deb10u1_amd64.deb
wget https://depot.galaxyproject.org/apt/pool/main/s/slurm-drmaa/slurm-drmaa-dev_1.1.1-1+deb10u1_amd64.deb

sudo dpkg -i libslurm33_18.08.5.2-1+deb10u1_amd64.deb
sudo dpkg -i libslurmdb33_18.08.5.2-1+deb10u1_amd64.deb
sudo dpkg -i slurm-drmaa1_1.1.1-1+deb10u1_amd64.deb
sudo dpkg -i slurm-drmaa-dev_1.1.1-1+deb10u1_amd64.deb

yes | sudo /usr/sbin/create-munge-key
sudo service munge start
sudo python scripts/configure_test_slurm.py
echo "export DRMAA_LIBRARY_PATH=/usr/lib/slurm-drmaa/lib/libdrmaa.so" >> local_env.sh
echo ". $VIRTUAL_ENV/bin/activate" >> local_env.sh
sudo useradd --home-dir /home/u1 --shell /bin/bash --create-home --comment TEST,,, --groups travis u1  ## Create user for run-as-user test.
mkdir -p ~/.ssh && cp test_data/testkey.pub ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
