# Use an official Python runtime as a parent image
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["python", "app/main.py"]
