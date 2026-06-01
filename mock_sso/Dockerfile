FROM python:3.12-slim

LABEL maintainer="MindBridge DevOps"
LABEL description="Mock SSO server implementing OAuth 2.0 authorization_code flow for local development"

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastapi==0.111.0 uvicorn[standard]==0.29.0 httpx==0.27.0 python-multipart==0.0.9

# Copy application
COPY main.py .

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
