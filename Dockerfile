FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY node_gps/ node_gps/
COPY manifest.json node_gps/manifest.json
COPY config.default.ini .

# Git release tag, passed by the release workflow; the Node reports "dev" when unset.
ARG NODE_VERSION
ENV NODE_VERSION=${NODE_VERSION}

ENTRYPOINT ["python", "-m", "node_gps.main"]
CMD ["--config", "/app/config.ini"]
