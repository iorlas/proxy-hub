FROM python:3.13-slim

RUN useradd -r -s /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY proxy_api/ ./proxy_api/

RUN mkdir -p /data && chown app:app /data

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENV PYTHONPATH=/app
USER app
CMD ["python", "-u", "-m", "proxy_api.main"]
