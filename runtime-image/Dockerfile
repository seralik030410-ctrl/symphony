FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ripgrep curl poppler-utils ca-certificates fonts-dejavu-core libreoffice-writer libreoffice-impress libreoffice-calc \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /bin/sh sandbox

COPY requirements.txt /opt/symphony/requirements.txt
RUN pip install --no-cache-dir -r /opt/symphony/requirements.txt

# OCR is a separate layer so stage-5 users can reuse the large office layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*
LABEL com.symphony.runtime.version="6.0"

ENV HOME=/home/sandbox \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    npm_config_update_notifier=false

WORKDIR /workspace
USER sandbox

CMD ["/bin/sh"]
