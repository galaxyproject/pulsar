FROM conda/miniconda2

ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive
ENV PULSAR_CONFIG_CONDA_PREFIX /usr/local

# TODO: pycurl stuff...

RUN apt-get update \
    # Install CVMFS client
    && apt-get install -y --no-install-recommends lsb-release wget \
        gcc python-setuptools \
        python-dev python-pip \
    && apt-get -y autoremove \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/* /var/log/dpkg.log

RUN pip install -U pip && pip install wheel kombu pykube poster

ENV PULSAR_VERSION 0.11.0.dev0

ADD pulsar_app-$PULSAR_VERSION-py2.py3-none-any.whl /pulsar_app-$PULSAR_VERSION-py2.py3-none-any.whl

RUN pip install /pulsar_app-$PULSAR_VERSION-py2.py3-none-any.whl
