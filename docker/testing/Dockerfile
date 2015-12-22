# Pulsar Testing Docker Image
#
# VERSION       0.1.0

# Build Docker image and then run tests with current pulsar clone! Tests
# include exercising rabbitmq, run as real user, DRMAA, etc....	
# docker build -t pulsar/testing .  
# docker run -v `pwd`/../..:/pulsar/ -t pulsar/testing 

FROM ubuntu:14.04

MAINTAINER John Chilton, jmchilton@gmail.com

RUN DEBIAN_FRONTEND=noninteractive apt-get -qq update

RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y build-essential
RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y python-dev
RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y python-virtualenv
RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y sudo

RUN DEBIAN_FRONTEND=noninteractive apt-get install -y slurm-llnl slurm-llnl-torque slurm-drmaa-dev
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y rabbitmq-server
# Needed for SLURM.
RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y libswitch-perl

RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y libcurl4-openssl-dev

## Condor Testing: See note in run_tests.sh
# RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y htcondor

RUN /usr/sbin/create-munge-key
ADD ./configure_slurm.py /usr/sbin/configure_slurm.py

RUN mkdir /usr/share/pulsar; chmod 755 /usr/share/pulsar
RUN virtualenv /usr/share/pulsar/venv

#RUN . /usr/share/pulsar/venv/bin/activate; pip install webob psutil PasteDeploy six paste PasteScript
#RUN . /usr/share/pulsar/venv/bin/activate; pip install drmaa
#RUN . /usr/share/pulsar/venv/bin/activate; pip install pycurl kombu pyyaml
#RUN . /usr/share/pulsar/venv/bin/activate; pip install nose coverage webtest unittest2 pyflakes flake8

RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y software-properties-common
RUN DEBIAN_FRONTEND=noninteractive add-apt-repository ppa:fkrull/deadsnakes
RUN DEBIAN_FRONTEND=noninteractive apt-get -qq update
RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y python2.6 python2.6-dev python3.4 python3.4-dev
RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y python2.6 python2.6-dev python3.4 python3.4-dev git

RUN . /usr/share/pulsar/venv/bin/activate; pip install tox

RUN echo 'OPTIONS="--force"' > /etc/default/munge

RUN adduser --quiet --disabled-password --gecos TEST u1

ADD container_env.sh /usr/share/pulsar/container_env.sh

ADD tox_wrapper.sh /usr/sbin/tox_wrapper.sh
RUN chmod +x /usr/sbin/tox_wrapper.sh

VOLUME ["/pulsar"]

ENTRYPOINT ["/usr/sbin/tox_wrapper.sh"]
