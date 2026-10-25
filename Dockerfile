FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONFIG_FILE=/app/config.json \
    DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 cesoir \
    && useradd --uid 10001 --gid cesoir --no-create-home cesoir \
    && mkdir -p /app /data \
    && chown cesoir:cesoir /data

WORKDIR /app
COPY cesoir /app/cesoir
COPY config.json /app/config.json
USER 10001:10001
ENTRYPOINT ["python", "-m", "cesoir"]
