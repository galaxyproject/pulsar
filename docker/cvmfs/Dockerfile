FROM conda/miniconda2

ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive
ENV PULSAR_CONFIG_CONDA_PREFIX /usr/local

ADD ./requirements.txt /pulsar/

RUN apt-get update \
    # Install CVMFS client
    && apt-get install -y --no-install-recommends lsb-release wget \
    && wget https://ecsft.cern.ch/dist/cvmfs/cvmfs-release/cvmfs-release-latest_all.deb \
    && dpkg -i cvmfs-release-latest_all.deb \
    && rm -f cvmfs-release-latest_all.deb \
    # Install packages
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc python-setuptools \
        python-dev python-pip \
        cvmfs cvmfs-config-default \
        slurm-llnl slurm-drmaa-dev \
    # Install Pulsar Python requirements
    && pip install --no-cache-dir -r /pulsar/requirements.txt drmaa \
    # Remove build deps and cleanup
    && apt-get -y remove python-dev gcc wget lsb-release \
    && apt-get -y autoremove \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/* /var/log/dpkg.log \
    && /usr/sbin/create-munge-key

# Create pulsar user environment
RUN adduser --disabled-password --gecos '' pulsar \
    && mkdir -p /pulsar

# Set working directory to /pulsar/
WORKDIR /pulsar/

# Add files to the image
ADD . /pulsar/
# Change ownership to pulsar & configure CVMFS
RUN python setup.py install \
    && pulsar-config --auto_conda --host 0.0.0.0 \
    && echo "export DRMAA_LIBRARY_PATH=/usr/lib/slurm-drmaa/lib/libdrmaa.so" >> local_env.sh \
    && cp docker/cvmfs/app.yml . \
    && chown -R pulsar:pulsar /pulsar \
    && chmod +x /usr/local/bin/pulsar \
    && _pulsar-configure-galaxy-cvmfs \
    && chown pulsar -R /usr/local

# Pulsar will listen on this port
EXPOSE 8913

# Must run CVMFS setup otherwise autofs does not get configured nor automount
# starts. Then start Slurm and switch to a less-priviledged user for Pulsar.
CMD /usr/bin/cvmfs_config setup; service munge start; \
    _pulsar-configure-slurm; service slurmd start; \
    service slurmctld start; su pulsar -c "/usr/local/bin/pulsar"
