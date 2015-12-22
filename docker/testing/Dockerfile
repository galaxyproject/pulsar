# Pulsar Testing Docker Image
#
# VERSION       0.1.0

# Build Docker image and then run tests with current pulsar clone! Tests
# include exercising rabbitmq, run as real user, DRMAA, etc....	
# docker build -t pulsar/testing .  
# docker run -v `pwd`/../..:/pulsar/ -t pulsar/testing 

FROM ubuntu:14.04

MAINTAINER John Chilton, jmchilton@gmail.com

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get -qq update && \
    apt-get install --no-install-recommends -y software-properties-common && \
    add-apt-repository ppa:fkrull/deadsnakes && \
    apt-get -qq update && \
    apt-get install --no-install-recommends -y build-essential \
    python-dev python-virtualenv sudo slurm-llnl slurm-llnl-torque slurm-drmaa-dev \
    rabbitmq-server libswitch-perl libcurl4-openssl-dev \
    python2.6 python2.6-dev python3.4 python3.4-dev git && \
    apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

## Condor Testing: See note in run_tests.sh
# RUN apt-get install --no-install-recommends -y htcondor


RUN /usr/sbin/create-munge-key
ADD ./configure_slurm.py /usr/sbin/configure_slurm.py

RUN mkdir /usr/share/pulsar; chmod 755 /usr/share/pulsar
RUN virtualenv /usr/share/pulsar/venv

RUN . /usr/share/pulsar/venv/bin/activate; pip install tox

RUN echo 'OPTIONS="--force"' > /etc/default/munge

RUN adduser --quiet --disabled-password --gecos TEST u1

ADD container_env.sh /usr/share/pulsar/container_env.sh

ADD tox_wrapper.sh /usr/sbin/tox_wrapper.sh
RUN chmod +x /usr/sbin/tox_wrapper.sh

VOLUME ["/pulsar"]

ENTRYPOINT ["/usr/sbin/tox_wrapper.sh"]
