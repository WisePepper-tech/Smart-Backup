# Using a specific hash of an image to protect against Supply Chain attacks
FROM python:3.13-slim@sha256:a208155746991fb5c4baf3c501401c3fee09e814ab0e5121a0f53b2ca659e0e2 AS builder

WORKDIR /app

# Installing dependencies in a virtual environment
ARG PIP_FIND_LINKS=/app/wheels
COPY wheels /app/wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=${PIP_FIND_LINKS} --user --require-hashes -r requirements.txt

# The final image (Runtime)
FROM python:3.13-slim@sha256:a208155746991fb5c4baf3c501401c3fee09e814ab0e5121a0f53b2ca659e0e2

# Creating a non-root user (default security)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

# Create the /data folder and grant the user rights BEFORE switching to it
RUN mkdir /data && chown appuser:appgroup /data
WORKDIR /app

# Copying only the installed packages from the builder layer
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appgroup . .

# Configuring Paths
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

USER appuser

# Health Check: check libraries and MinIO availability (if enabled)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, socket; \
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); \
    s.settimeout(2); \
    endpoint = os.getenv('S3_ENDPOINT', '').replace('http://', '').split(':'); \
    host = endpoint[0] if endpoint[0] else 'localhost'; \
    port = int(endpoint[1]) if len(endpoint) > 1 else 9000; \
    exit_code = s.connect_ex((host, port)); \
    s.close(); \
    exit(0 if exit_code == 0 or os.getenv('STORAGE_MODE') != '2' else 1)"

ENTRYPOINT ["python", "main.py"]
