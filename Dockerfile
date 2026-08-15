FROM python:3.13-slim

WORKDIR /app

# Use the same dependency tool and version as the local development environment.
RUN pip install --no-cache-dir uv==0.11.6

# Install locked runtime dependencies before copying application code so source
# edits do not invalidate the slower dependency-installation layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY resolve_ai ./resolve_ai

# uv installs dependencies into /app/.venv. Adding it to PATH lets the container
# run Uvicorn directly without using a shell or a custom entrypoint script.
ENV PATH="/app/.venv/bin:$PATH"

# EXPOSE documents the container port. Compose publishes it on the host.
EXPOSE 8000

CMD ["uvicorn", "resolve_ai.api:app", "--host", "0.0.0.0", "--port", "8000"]
