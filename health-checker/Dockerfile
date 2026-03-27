FROM python:3.13-slim

RUN useradd -r -s /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY health_check.py .

HEALTHCHECK CMD python -c "import os; os.kill(1, 0)" || exit 1

USER app
CMD ["python", "-u", "health_check.py"]
