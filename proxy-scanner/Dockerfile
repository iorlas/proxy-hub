FROM python:3.13-slim

RUN useradd -r -s /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY proxy_scanner/ ./proxy_scanner/

RUN mkdir -p /data && chown app:app /data

HEALTHCHECK CMD python -c "import os; os.kill(1, 0)" || exit 1

ENV PYTHONPATH=/app
USER app
CMD ["python", "-u", "/app/proxy_scanner/main.py"]
