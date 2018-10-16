FROM debian:latest

ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive

ADD ./requirements.txt /pulsar/ 

RUN apt-get update \
    # build dependencies
    && apt-get install -y --no-install-recommends apt-utils build-essential python-setuptools python-dev python-pip \
    \
    # preinstall conda for faster startup
    && apt-get -y install curl bzip2 \
    && curl -sSL https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -bfp /pulsar/dependencies/_conda \
    && rm -rf /tmp/miniconda.sh \
    \
    # Install pulsar python requirements
    && pip install --no-cache-dir -r /pulsar/requirements.txt \
    \
    # Remove build deps and cleanup
    && apt-get -y remove curl bzip2 \
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

# gunicorn will listen on this port
EXPOSE 8913

CMD /usr/local/bin/pulsar
