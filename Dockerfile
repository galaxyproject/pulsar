FROM conda/miniconda2

ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive
ENV PULSAR_CONFIG_CONDA_PREFIX /usr/local

ADD ./requirements.txt /pulsar/

RUN apt-get update \
    # build dependencies
    && apt-get install -y --no-install-recommends gcc python-setuptools python-dev python-pip \
    \
    # Install pulsar python requirements
    && pip install --no-cache-dir -r /pulsar/requirements.txt \
    \
    # Remove build deps and cleanup
    && apt-get -y remove curl bzip2 python-dev gcc \
    && apt-get -y autoremove \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/* /var/log/dpkg.log

# Create pulsar user environment
RUN adduser --disabled-password --gecos '' pulsar \
    && mkdir -p /pulsar

# Set working directory to /pulsar/
WORKDIR /pulsar/

# Add files to /pulsar/
ADD . /pulsar

# Change ownership to pulsar
RUN python setup.py install \
    && pulsar-config --auto_conda --host 0.0.0.0 \
    && chown -R pulsar:pulsar /pulsar \
    && chmod +x /usr/local/bin/pulsar

# Switch to new, lower-privilege user
USER pulsar

# pulsar will listen on this port
EXPOSE 8913

CMD /usr/local/bin/pulsar
