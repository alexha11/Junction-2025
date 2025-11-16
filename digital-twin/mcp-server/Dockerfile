FROM python:3.13-slim AS prod

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
	--trusted-host pypi.org \
	--trusted-host files.pythonhosted.org
RUN pip install --no-cache-dir -r requirements.txt \
	--trusted-host pypi.org \
	--trusted-host files.pythonhosted.org

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV MCP_SERVER_PORT=8080

# Ignored in docker-compose.yml
CMD ["python", "mcp_server.py"]
