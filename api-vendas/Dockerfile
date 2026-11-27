FROM python:3.12-slim
WORKDIR /app
COPY api-vendas/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY api-vendas /app/service
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
