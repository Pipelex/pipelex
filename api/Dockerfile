# The build context is the repository root, not this directory:
#
#   docker build -f api/Dockerfile .        (what `make -C api docker-build` runs)
#
# The server is a member of the uv workspace rooted there, and it installs pipelex from the same
# commit rather than from PyPI, so the image cannot run a pipelex other than the one it was released
# with. The root `.dockerignore` keeps that context down to the files this build reads.

# ─── builder: the virtual environment, built from the workspace lock ──────────
FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# The lock and the two projects' metadata first, so the layer holding the third-party dependencies
# is cached across source changes. The server's metadata includes `hatch_build.py`, the hook that
# writes its dependencies and pins pipelex to the release's version. `--package pipelex-api` installs
# the server's dependency set: pipelex with the extras the server's pyproject.toml names, and `cli`
# deliberately not among them, because the server selects the `json` log sink and a Rich-free
# pretty-print mode, so nothing it does on a request renders a terminal. (Rich itself is still
# installed — typer and instructor both require it unconditionally — it is simply never reached.)
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY api/pyproject.toml api/hatch_build.py api/README.md api/LICENSE api/
RUN uv sync --frozen --no-dev --package pipelex-api --no-install-workspace

# Then the two packages themselves, built as wheels rather than linked to the source tree, so the
# image runs what the published `pipelex` and `pipelex-api` distributions contain. hatchling leaves
# out of a wheel what the project's `.gitignore` ignores, so those come first: without them, a local
# build would ship whatever ignored files lie in the working tree.
COPY .gitignore ./
COPY api/.gitignore api/
COPY pipelex/ pipelex/
COPY api/pipelex_api/ api/pipelex_api/
RUN uv sync --frozen --no-dev --package pipelex-api --no-editable

# ─── runtime ──────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# curl serves the HEALTHCHECK below, and git is what pipelex runs to fetch a method by its address
# (`method_ref` on the run and validate routes).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

# ─── Pipelex global config (terms acceptance, backends) ────────────────────────
# The server's bundled config becomes ~/.pipelex (the global config dir), and no project-level
# .pipelex exists in the image, so users mounting overrides into /root/.pipelex aren't shadowed.
# See api/docs/configuration.md.
COPY api/.pipelex/ /root/.pipelex/

# ─── runtime config ────────────────────────────────────────────────────────────
# Note: container runs as root. Relocating the bundled `.pipelex/` to a
# non-root user's $HOME is planned for the next minor release — coupling that
# with the documented mount path at `/root/.pipelex` would be a breaking
# change for current deployments.

LABEL org.opencontainers.image.title="pipelex-api" \
      org.opencontainers.image.description="Official Pipelex REST API server" \
      org.opencontainers.image.source="https://github.com/Pipelex/pipelex" \
      org.opencontainers.image.licenses="Elastic-2.0" \
      org.opencontainers.image.vendor="Evotis S.A.S."

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8081/health || exit 1

CMD ["uvicorn", "pipelex_api.main:app", "--host", "0.0.0.0", "--port", "8081"]
