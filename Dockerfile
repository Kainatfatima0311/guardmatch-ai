# syntax=docker/dockerfile:1

# ============================================================================
# GuardMatch AI — multi-stage build
#
# Two stages, because the build needs a compiler toolchain and the runtime does
# not. Shipping gcc in a production image adds several hundred megabytes and a
# larger attack surface, for no benefit once the wheels are built.
#
# Model artifacts are baked in rather than mounted. A running container should
# fully describe the model it is serving: rolling out a new model means deploying
# a new image, which keeps deployment history and model history in step. A
# mounted volume would let the two drift apart silently.
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# LightGBM needs a compiler and OpenMP headers to build if no wheel matches the
# platform. Present in the builder only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# A virtualenv rather than the system interpreter, so the runtime stage can copy
# one self-contained directory instead of reconstructing site-packages.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Dependency metadata first. Docker caches this layer, so an application change
# does not reinstall LightGBM and spaCy every build.
COPY pyproject.toml README.md ./
COPY src/guardmatch/__init__.py src/guardmatch/__init__.py

RUN pip install --upgrade pip setuptools wheel \
    && pip install .

# The spaCy model is a runtime requirement, not an optional download. Fetching
# it at container start would make startup depend on network access and turn a
# transient outage into a failed deploy.
RUN python -m spacy download en_core_web_sm

COPY src/ src/
RUN pip install --no-deps .

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# libgomp1 is the one build dependency that is also needed at runtime: LightGBM
# links against OpenMP.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root. A container that does not need to write to its own filesystem should
# not be able to.
RUN groupadd --system --gid 1001 guardmatch \
    && useradd --system --uid 1001 --gid guardmatch --create-home guardmatch

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Versioned artifacts, baked in and owned by the unprivileged user.
COPY --chown=guardmatch:guardmatch models/ models/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_VERSION=v0.1.0 \
    MODEL_DIR=/app/models \
    LOG_FORMAT=json \
    API_HOST=0.0.0.0 \
    API_PORT=8000

USER guardmatch

EXPOSE 8000

# Wired to /ready rather than /health. Liveness only says the process is up;
# readiness says the model loaded and its checksums verified. An instance serving
# from an unverified model is alive and must still be kept out of the pool.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "guardmatch.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
