# --- Build stage: install dependencies ---
FROM python:3.11-slim AS base

WORKDIR /app

# Install dependencies first (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY templates/ templates/
COPY config.yaml .

# Create directories for runtime data (volume mount targets)
RUN mkdir -p data logs

# Run as non-root user for security
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 0.0.0.0 required so connections from outside the container can reach it
# Single worker (default) — multiple workers would duplicate background tasks
# No --reload — source files don't change inside the image
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
