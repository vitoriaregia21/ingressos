FROM python:3.12-slim
WORKDIR /app
COPY worker-processador/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY worker-processador /app/service
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["python", "service/worker.py"]
