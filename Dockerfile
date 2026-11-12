FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
RUN mkdir -p /data
ENV DATABASE_PATH=/data/broward.db
EXPOSE 8080
CMD ["sh", "-c", "gunicorn --chdir backend --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 app:app"]
