FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app/secure_api

EXPOSE 8080

CMD ["uvicorn", "secure_api.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
