FROM python:3.11-slim

# ─── system packages (build deps removed in same layer to keep image small) ────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ─── uv ────────────────────────────────────────────────────────────────────────
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy lockfile + project metadata first so dependency-install layer is cacheable.
# The extras this installs are the ones declared in pyproject.toml, and `cli` is deliberately not
# among them: the server selects the `json` log sink and a Rich-free pretty-print mode, so nothing
# it does on a request renders a terminal. (Rich itself is still in the image — typer and
# instructor both require it unconditionally — it is simply never reached.)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the app
COPY . /app
RUN uv sync --frozen --no-dev

# ─── Pipelex global config (terms acceptance, backends) ────────────────────────
# Move the bundled config to ~/.pipelex (the global config dir) and drop it from
# /app so users mounting overrides into /root/.pipelex aren't shadowed by a
# project-level .pipelex inside the image. See docs/configuration.md.
RUN cp -r /app/.pipelex /root/.pipelex && rm -rf /app/.pipelex

# Strip build-only system packages now that wheels are compiled.
RUN apt-get update \
    && apt-get purge -y --auto-remove git build-essential \
    && rm -rf /var/lib/apt/lists/*

# ─── runtime config ────────────────────────────────────────────────────────────
# Note: container runs as root. Relocating the bundled `.pipelex/` to a
# non-root user's $HOME is planned for the next minor release — coupling that
# with the documented mount path at `/root/.pipelex` would be a breaking
# change for current deployments.

LABEL org.opencontainers.image.title="pipelex-api" \
      org.opencontainers.image.description="Official Pipelex REST API server" \
      org.opencontainers.image.source="https://github.com/Pipelex/pipelex-api" \
      org.opencontainers.image.licenses="Elastic-2.0" \
      org.opencontainers.image.vendor="Evotis S.A.S."

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8081/health || exit 1

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8081"]
