# Smart Waste Segregator — backend runtime image.
# Build context = repository root (the backend statically serves ../frontend).

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies first (better layer caching).
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt

# Copy application source: backend + the frontend it serves.
COPY backend /app/backend
COPY frontend /app/frontend

WORKDIR /app/backend

EXPOSE 5000

# Production command: gunicorn with a single eventlet worker.
# Socket.IO state is in-memory, so it must stay within one process.
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "--timeout", "120", "app:app"]