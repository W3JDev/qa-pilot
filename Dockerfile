# QA Pilot — containerized, runnable anywhere.
#
# build: docker build -t qa-pilot .
# run:   docker run --rm -e OPENAI_API_KEY -v $PWD/qa-artifacts:/work/qa-artifacts \
#          -v $PWD/examples:/work/examples qa-pilot run /work/examples/cockpit.yaml

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Playwright Chromium runtime deps (minimal set)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
    libasound2 libatspi2.0-0 fonts-liberation libnss3 \
    ca-certificates wget curl xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# Install qa-pilot — copy the source tree and install into the image
COPY pyproject.toml README.md /work/
COPY src /work/src
RUN pip install --no-cache-dir .

# Install Playwright Chromium (skip Firefox + WebKit to keep the image small)
RUN python -m playwright install chromium

ENTRYPOINT ["qa-pilot"]
CMD ["--help"]
