FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY listener.py .

RUN mkdir -p /data

CMD ["python", "-u", "listener.py"]
