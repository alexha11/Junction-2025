FROM python:3.13-slim AS prep-data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

RUN python parse_historical_data.py

FROM python:3.13-slim AS prod

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

COPY --from=prep-data /app/data /app/data

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV SPEEDUP=1

# Ignored in docker-compose.yml
CMD ["python", "opcua_server.py"]
