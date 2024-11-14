# use the root of the repository as context, i.e. `docker build . -f ./docker/coexecutor/Dockerfile`

FROM python:3.12-bookworm as build_wheel

ENV PIP_ROOT_USER_ACTION=ignore

WORKDIR /build

# install requirements
COPY requirements.txt .
COPY dev-requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir setuptools -r requirements.txt -r dev-requirements.txt

# build Pulsar wheel
COPY . .
RUN python setup.py sdist bdist_wheel


FROM python:3.12-bookworm

ENV PYTHONUNBUFFERED 1
ENV PIP_ROOT_USER_ACTION=ignore
ENV DEBIAN_FRONTEND noninteractive
ENV PULSAR_CONFIG_CONDA_PREFIX /usr/local

# set up Galaxy Depot repository (provides SLURM DRMAA packages for Debian Buster and newer releases)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "http://keyserver.ubuntu.com/pks/lookup?op=get&search=0x18381AC8832160AF" | gpg --dearmor -o /etc/apt/trusted.gpg.d/galaxy-depot.gpg \
    && echo "deb https://depot.galaxyproject.org/apt/ $(bash -c '. /etc/os-release; echo ${VERSION_CODENAME:-bookworm}') main" | tee /etc/apt/sources.list.d/galaxy-depot.list

# set up Debian Bullseye repository (and use it only for libslurm36, needed by slurm-drmaa1, and slurm)
RUN echo "deb http://deb.debian.org/debian/ bullseye main" > /etc/apt/sources.list.d/bullseye.list && \
cat <<EOF > /etc/apt/preferences.d/bullseye.pref
Package: *
Pin: release n=bullseye
Pin-Priority: -1

Package: libslurm36, slurm
Pin: release n=bullseye
Pin-Priority: 100
EOF

# set up CVMFS repository
RUN apt-get update \
    && apt-get install -y --no-install-recommends lsb-release wget \
    && wget https://ecsft.cern.ch/dist/cvmfs/cvmfs-release/cvmfs-release-latest_all.deb \
    && dpkg -i cvmfs-release-latest_all.deb && rm -f cvmfs-release-latest_all.deb

# wget, gcc, pip - to build and install Pulsar.
# bzip2 for Miniconda.
# TODO: pycurl stuff...
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Install CVMFS client
    cvmfs cvmfs-config-default \
    # Install packages
    gcc libcurl4-openssl-dev \
    munge libmunge-dev slurm slurm-drmaa-dev \
    bzip2 \
    # Install Pulsar Python requirements
    && pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir drmaa wheel kombu pykube pycurl \
            webob psutil PasteDeploy pyyaml paramiko \
    # Remove build deps and cleanup
    && apt-get -y remove gcc wget lsb-release \
    && apt-get -y autoremove \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/log/dpkg.log

COPY --from=build_wheel /build/dist/pulsar_app-*-py2.py3-none-any.whl /

SHELL ["/bin/bash", "-c"]

RUN pip install --no-cache-dir --upgrade setuptools pyOpenSSL cryptography
RUN pip install --no-cache-dir "$(echo /pulsar_app-*-py2.py3-none-any.whl)"[galaxy_extended_metadata] && rm /pulsar_app-*-py2.py3-none-any.whl
RUN pip install --upgrade 'importlib-metadata<5.0'
RUN _pulsar-configure-galaxy-cvmfs
RUN _pulsar-conda-init --conda_prefix=/pulsar_dependencies/conda
