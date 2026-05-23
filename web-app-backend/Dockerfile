FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.109.0 \
    uvicorn[standard]==0.27.0 \
    asyncpg==0.29.0 \
    pydantic==2.5.0 \
    redis==5.0.0 \
    openpyxl==3.1.2 \
    python-dateutil==2.8.2 \
    python-multipart==0.0.6

COPY . .

EXPOSE 8002

CMD ["python", "cmd/main.py"]
