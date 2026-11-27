FROM python:3.12-slim
WORKDIR /app
COPY gerenciador-estoque/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY gerenciador-estoque /app/service
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["uvicorn", "service.estoque:app", "--host", "0.0.0.0", "--port", "8001"]
