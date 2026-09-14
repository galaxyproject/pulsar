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

COPY mock_galaxy/app.py /app/app.py
COPY mock_galaxy/recorder.py /app/recorder.py

ENV PYTHONUNBUFFERED=1
EXPOSE 8088

CMD ["python", "/app/app.py"]
