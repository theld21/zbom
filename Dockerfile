FROM python:3.11-slim

# Performance optimizations
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PIP_NO_CACHE_DIR=1 \
  USE_UVLOOP=1 \
  USE_NUMBA=0

# Install system dependencies for numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r bomber && useradd -r -g bomber bomber

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code and entry point
COPY app/ ./app/
COPY run_bot.py ./
COPY optimized_strategy.json ./

# Create logs directory with proper permissions
RUN mkdir -p /app/logs && chown -R bomber:bomber /app/logs

# Runtime user
USER bomber

ENV PYTHONUNBUFFERED=1     UVICORN_WORKERS=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3   CMD python -c "import json,urllib.request;     print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz'))['status'])" | grep -q ok

CMD ["python", "run_bot.py"]
