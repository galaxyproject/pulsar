FROM conda/miniconda3

ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive
ENV PULSAR_CONFIG_CONDA_PREFIX /usr/local

# wget, gcc, pip - to build and install Pulsar.
# bzip2 for Miniconda.
# TODO: pycurl stuff...
RUN apt-get update \
    && apt-get install -y --no-install-recommends apt-transport-https \
    # Install CVMFS client
    && apt-get install -y --no-install-recommends lsb-release wget \
    && wget https://ecsft.cern.ch/dist/cvmfs/cvmfs-release/cvmfs-release-latest_all.deb \
    && dpkg -i cvmfs-release-latest_all.deb \
    && rm -f cvmfs-release-latest_all.deb \
    # Install packages
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc \
        libcurl4-openssl-dev \
        cvmfs cvmfs-config-default \
        slurm-llnl slurm-drmaa-dev \
        bzip2 \
    # Install Pulsar Python requirements
    && pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir drmaa wheel kombu pykube pycurl \
            webob psutil PasteDeploy pyyaml paramiko \
    # Remove build deps and cleanup
    && apt-get -y remove gcc wget lsb-release \
    && apt-get -y autoremove \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/* /var/log/dpkg.log \
    && /usr/sbin/create-munge-key

ADD pulsar_app-*-py2.py3-none-any.whl /pulsar_app-*-py2.py3-none-any.whl

RUN pip install --upgrade setuptools && pip install pyOpenSSL --upgrade && pip install cryptography --upgrade
RUN pip install --no-cache-dir /pulsar_app-*-py2.py3-none-any.whl[galaxy_extended_metadata] && rm /pulsar_app-*-py2.py3-none-any.whl
RUN pip install --upgrade 'importlib-metadata<5.0'
RUN _pulsar-configure-galaxy-cvmfs
RUN _pulsar-conda-init --conda_prefix=/pulsar_dependencies/conda
