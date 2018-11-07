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
        python-dev python-pip cvmfs cvmfs-config-default \
    # Install Pulsar Python requirements
    && pip install --no-cache-dir -r /pulsar/requirements.txt \
    # Remove build deps and cleanup
    && apt-get -y remove python-dev gcc wget lsb-release \
    && apt-get -y autoremove \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/* /var/log/dpkg.log

# Create pulsar user environment
RUN adduser --disabled-password --gecos '' pulsar \
    && mkdir -p /pulsar

# Set working directory to /pulsar/
WORKDIR /pulsar/

# Add files to the image
ADD . /pulsar
# Change ownership to pulsar & configure CVMFS
RUN python setup.py install \
    && pulsar-config --auto_conda --host 0.0.0.0 \
    && chown -R pulsar:pulsar /pulsar \
    && chmod +x /usr/local/bin/pulsar \
    && cp /pulsar/docker/cvmfs/default.local /etc/cvmfs/ \
    && cp /pulsar/docker/cvmfs/galaxyproject.org.conf /etc/cvmfs/domain.d/ \
    && cp /pulsar/docker/cvmfs/data.galaxyproject.org.pub /etc/cvmfs/keys/

# Pulsar will listen on this port
EXPOSE 8913

# Must run CVMFS setup otherwise autofs does not get configured nor automount
# starts. Then switch to less-priviledged user for running Pulsar.
CMD /usr/bin/cvmfs_config setup; su pulsar -c "/usr/local/bin/pulsar"
