FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
        fastapi==0.111.0 \
        uvicorn[standard]==0.30.0 \
        kombu==5.3.7 \
        amqp==5.2.0 \
        requests==2.32.3 \
        simple-job-files==0.2.1 \
        a2wsgi==1.10.10

# The recorder now lives in the Pulsar distribution as pulsar.testing.recorder,
# so copy the package rather than a loose module. Only pulsar/__init__.py and
# pulsar.testing.recorder are imported here and both are pure stdlib, so none
# of Pulsar's own runtime dependencies are needed in this image.
COPY pulsar /app/pulsar
COPY test/resilience/mock_galaxy/app.py /app/app.py

ENV PYTHONUNBUFFERED=1
EXPOSE 8088

CMD ["python", "/app/app.py"]
