# Base Python image
FROM python:3.10-slim

# Set environment variables to prevent buffering of stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create a working directory
WORKDIR /app

# Create a non-root user and switch to it
# Using numeric UID/GID is more portable for some environments like OpenShift
RUN useradd --create-home --no-log-init --shell /bin/bash -u 1001 -g 0 appuser && \
    chown -R appuser:0 /app && \
    chmod -R g+w /app
# The group is set to 0 (root) to allow write access to /app for appuser,
# which can be useful if pip needs to write to site-packages owned by root in some base images.
# Alternatively, ensure /app and any relevant site-packages are owned by appuser.

# For pip install, ensure appuser has a home directory it can write to for cache
# Or run pip install as root before switching user if installing globally

# Switch to the non-root user
USER appuser

# Default command (optional, can be overridden)
# CMD ["python"]
