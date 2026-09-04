FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so the layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY data/ ./data/

# The corpus is baked into the image, so the container needs no network access.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
