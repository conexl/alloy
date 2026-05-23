# Multi-stage build for Python service
FROM python:3.11-slim AS base

# Install system dependencies (for lxml, etc.)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code (excluding .venv via .dockerignore)
COPY . .

# Expose health check port
EXPOSE 8000

# Run
CMD ["python", "main.py"]
