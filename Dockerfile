# Use python 3.12 slim image
FROM python:3.12-slim-bookworm

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Install system dependencies (git, build tools for tree-sitter, runtimes)
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    curl \
    nodejs \
    npm \
    php-cli \
    php-mbstring \
    php-xml \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first
COPY pyproject.toml .
COPY uv.lock .

# Sync dependencies
RUN uv sync --frozen

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Command using uv run
CMD ["uv", "run", "python", "-m", "astra.main"]
