# Python service for report generation
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create reports directory
RUN mkdir -p /app/reports

# Run
CMD ["uvicorn", "cmd.main:app", "--host", "0.0.0.0", "--port", "8081"]