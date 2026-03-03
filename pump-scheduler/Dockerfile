FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pump-scheduler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY pump-scheduler /app

ENV PYTHONUNBUFFERED=1
ENV OPCUA_ENDPOINT=opc.tcp://opcua-server:4840/wastewater/
ENV OPC_POLL_SECONDS=0.2
ENV ROLLING_STEPS=192
ENV MIN_HISTORY_STEPS=32
ENV REOPTIMIZE_EVERY_SAMPLES=1
ENV COMMAND_MODE=db
ENV DB_PATH=/app/data/scheduler.db
ENV WEB_PORT=8090

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${WEB_PORT}"]
