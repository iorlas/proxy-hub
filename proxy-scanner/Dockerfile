FROM python:3.13-slim

RUN useradd -r -s /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY proxy_scanner/ ./proxy_scanner/

HEALTHCHECK CMD pgrep -f main.py || exit 1

ENV PYTHONPATH=/app
USER app
CMD ["python", "-u", "/app/proxy_scanner/main.py"]
