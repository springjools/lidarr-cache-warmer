# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY entrypoint.py .
COPY main.py .
COPY storage.py .
COPY stats.py .
COPY process_artists.py .
COPY process_artist_textsearch.py .
COPY process_releasegroups.py .

# Work directory for mounted data (config.ini + CSV files/SQLite DB)
WORKDIR /data

# Optional: allow overriding the config path at runtime
ENV CONFIG_PATH=/data/config.ini

# Default entrypoint runs the scheduler for continuous operation
ENTRYPOINT ["python", "/app/entrypoint.py"]
