FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY driver_gps/ driver_gps/
COPY manifest.json driver_gps/manifest.json
COPY config.default.ini .

# Git release tag, passed by the release workflow; the Driver reports "dev" when unset.
ARG DRIVER_VERSION
ENV DRIVER_VERSION=${DRIVER_VERSION}

ENTRYPOINT ["python", "-m", "driver_gps.main"]
CMD ["--config", "/app/config.ini"]
