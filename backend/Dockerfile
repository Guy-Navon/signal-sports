# Signal Sports backend image (#263). ONE image, two commands:
#   API:    uvicorn app.main:app --host 0.0.0.0 --port 8000
#   worker: python -m app.worker
# Build context is backend/ (backend/.dockerignore is an allowlist: no .env,
# no data/, no venv). Single-arch amd64 by design (docs/HOSTING_PLAN.md §8).
#
# The base image is pinned by digest: rebuilding the same commit gives the same
# OS layer. Bump it deliberately, in its own PR.
FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so code changes reuse this layer. Hash-pinned (#198);
# the installed set is recorded in the image for audits.
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock \
    && pip freeze > /app/PIP_FREEZE.txt

COPY app ./app
COPY scripts ./scripts

# Non-root service identity. 10001 is shared with no login user on the host;
# the host data dir is owned by it (docs/DEPLOYMENT.md). The code stays
# root-owned and read-only to the service user.
ARG SIGNAL_UID=10001
ARG SIGNAL_GID=10001
RUN groupadd --gid "${SIGNAL_GID}" signal \
    && useradd --uid "${SIGNAL_UID}" --gid "${SIGNAL_GID}" --no-create-home \
       --home-dir /tmp --shell /usr/sbin/nologin signal \
    && mkdir -p /app/data \
    && chown "${SIGNAL_UID}:${SIGNAL_GID}" /app/data \
    && chmod 0700 /app/data

# The corpus lives on a bind mount at /app/data. This is also the path the
# corpus guard (app/db/corpus_protection.py) protects inside the image.
ENV DATABASE_URL=sqlite:////app/data/signal_sports.db \
    HOME=/tmp

ARG GIT_SHA=unknown
LABEL org.opencontainers.image.title="signal-backend" \
      org.opencontainers.image.source="https://github.com/Guy-Navon/signal-sports" \
      org.opencontainers.image.revision="${GIT_SHA}"

USER ${SIGNAL_UID}:${SIGNAL_GID}
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-m", "app.healthcheck", "api"]

# No --reload, one uvicorn worker: the API runs no scheduler (docs/SCHEDULER.md).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
