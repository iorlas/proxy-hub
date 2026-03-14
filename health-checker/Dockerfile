FROM python:3.13-alpine

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY health_check.py /usr/local/bin/health_check.py

CMD ["python", "-u", "/usr/local/bin/health_check.py"]
