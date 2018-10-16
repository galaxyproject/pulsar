FROM frolvlad/alpine-miniconda2

ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive
ENV PULSAR_CONFIG_CONDA_PREFIX /opt/conda

ADD ./requirements.txt /pulsar/

RUN apk update \
    # psycopg2 dependencies
    && apk add --no-cache --virtual build-deps gcc python-dev musl-dev \
    # CFFI dependencies
    && apk --no-cache add libffi-dev py-cffi \
    && apk --no-cache add make linux-headers \
    \
    # Install python requirements
    && pip install --no-cache-dir -r /pulsar/requirements.txt \
    \
    # Remove build deps
    && apk del build-deps \
    && rm /var/cache/apk/*

# Create pulsar user environment
RUN adduser -D -g '' pulsar \
    && mkdir -p /pulsar

# Set working directory to /pulsar/
WORKDIR /pulsar/

# Add files to /pulsar/
ADD . /pulsar

# Change ownership to pulsar
RUN python setup.py install \
    && pulsar-config --auto_conda --host 0.0.0.0 \
    && chown -R pulsar:pulsar /pulsar

# Switch to new, lower-privilege user
USER pulsar

# gunicorn will listen on this port
EXPOSE 8913

CMD sh $PULSAR_CONFIG_CONDA_PREFIX/bin/pulsar
