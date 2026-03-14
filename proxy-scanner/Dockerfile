FROM python:3.13-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY proxy_scanner/ ./proxy_scanner/

ENV PYTHONPATH=/app
CMD ["python", "-u", "/app/proxy_scanner/main.py"]
