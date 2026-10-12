# Dockerfile for the NegotiateIQ Orchestrator (FastAPI / Python 3.11)
# Deployed to Cloud Run — listens on $PORT (default 8080).

FROM python:3.11-slim

WORKDIR /app

# Install deps first so Docker can cache this layer between code-only rebuilds
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and prompt files
COPY src/     ./src/
COPY prompts/ ./prompts/

EXPOSE 8080

# $PORT is injected by Cloud Run; fall back to 8080 for local docker run
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --app-dir src"]
