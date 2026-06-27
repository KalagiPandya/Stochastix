# ──────────────────────────────────────────────────────────────────────────
# Stochastix PRO — Multi-stage Dockerfile
#
# The optional ML stack (prophet, torch) pulls in build tools (gcc, cmake)
# and is large (~1.5GB with torch CPU wheels). To keep the default image
# lean, dependencies are split:
#
#   - requirements-core.txt  -> always installed (core app + auth + DB drivers)
#   - requirements.txt       -> full set, including ML libs (scikit-learn,
#                                prophet, torch) and streaming clients
#
# Build the full image (default):
#   docker build -t stochastix-pro .
#
# Build a lean image without heavy ML deps (Isolation Forest still works
# via scikit-learn; Prophet/LSTM pages report "not installed" gracefully):
#   docker build --build-arg REQUIREMENTS_FILE=requirements-core.txt -t stochastix-pro:lean .
# ──────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

ARG REQUIREMENTS_FILE=requirements.txt

WORKDIR /app

# Build tools needed for prophet (cmdstanpy/cmdstan) and some sklearn/torch wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt requirements-core.txt ./
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

# Copy project
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
