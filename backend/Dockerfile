# Backend image for the Banking CRM agent (FastAPI + LangGraph).
FROM python:3.11-slim

# Keep Python lean and unbuffered for predictable container logs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy the project and install it (deps resolved from pyproject.toml). asyncpg and
# the other deps ship pure-python/manylinux wheels, so no system build tools needed.
COPY . .
# INSTALL_DEV=true adds the test extras (pytest) — used only by the `test` compose
# service. The default app image stays lean (no test deps).
ARG INSTALL_DEV=false
RUN pip install --upgrade pip && \
    if [ "$INSTALL_DEV" = "true" ]; then pip install -e ".[dev]"; else pip install -e .; fi

EXPOSE 8000

# Default to serving the API; docker-compose overrides this to migrate + seed first.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
