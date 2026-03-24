FROM python:3.13-slim

RUN useradd -r -s /usr/sbin/nologin app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY health_check.py /usr/local/bin/health_check.py

HEALTHCHECK CMD pgrep -f health_check.py || exit 1

USER app
CMD ["python", "-u", "/usr/local/bin/health_check.py"]
