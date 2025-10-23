FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY olg_watcher.py .

RUN mkdir -p /data

CMD ["python", "-u", "olg_watcher.py"]
