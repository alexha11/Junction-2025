FROM python:3.13-slim AS prod

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV MCP_SERVER_PORT=8080

# Ignored in docker-compose.yml
CMD ["python", "mcp_server.py"]
