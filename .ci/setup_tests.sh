#!/bin/bash

set -e
set -v

sudo apt update
sudo apt install -y libxml2-dev libxslt1-dev libcurl4-openssl-dev openssh-server
#pip install -r requirements$REQUIREMENTS_SUFFIX.txt --use-mirrors || true
#pip install -r dev-requirements.txt --use-mirrors || true
#pip install coveralls  # Required fro coveralls reporting.
sudo apt install -y slurm-wlm slurm-wlm-torque munge
sudo apt install -y libswitch-perl libgnutls28-dev # A missing dependency of slurm-llnl-torque

# slurm-drmaa is not in Ubuntu; it comes from ppa:natefoo/slurm-drmaa. Fetch the
# published debs straight from the Launchpad librarian instead of adding the
# PPA: add-apt-repository depends on the Launchpad API and the PPA archive
# (ppa.launchpadcontent.net) intermittently answers 503. apt resolves their
# dependencies from the Ubuntu archive.
slurm_drmaa_debs=$(mktemp -d)
chmod 755 "$slurm_drmaa_debs"  # readable by apt's _apt sandbox user
while read -r sha256 url; do
    curl -fsSL -o "$slurm_drmaa_debs/$(basename "$url")" "$url"
    echo "$sha256  $slurm_drmaa_debs/$(basename "$url")" | sha256sum -c -
done <<'DEBS'
bb72e0db2fc3eb2b31020512e608a4598f9785bf664fccfe5a4dd2484e1dcb52 https://launchpadlibrarian.net/866291890/slurm-drmaa1_1.1.6-1ubuntu1~24.04_amd64.deb
3090bb8d39f6cff3a4bfd0e5e1e7dbbf715fbbfbc9f7397ef4f0b431f380485a https://launchpadlibrarian.net/866291888/slurm-drmaa-dev_1.1.6-1ubuntu1~24.04_amd64.deb
DEBS
sudo apt install -y "$slurm_drmaa_debs"/*.deb

# DEBIAN_FRONTEND=noninteractive sudo apt install htcondor ## htcondor installation

sudo service munge start
sudo python scripts/configure_test_slurm.py
echo "export DRMAA_LIBRARY_PATH=/usr/lib/slurm-drmaa/lib/libdrmaa.so" >> local_env.sh
#echo ". $VIRTUAL_ENV/bin/activate" >> local_env.sh
echo "umask 002" >> local_env.sh
sudo useradd --home-dir /home/u1 --shell /bin/bash --create-home --comment TEST,,, --groups $(id -gn) u1  ## Create user for run-as-user test.
mkdir -p ~/.ssh && cp test_data/testkey.pub ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
