<div align="center">
  <a href="https://www.pipelex.com/"><img src="https://raw.githubusercontent.com/Pipelex/pipelex/main/.github/assets/logo.png" alt="Pipelex Logo" width="400" style="max-width: 100%; height: auto;"></a>

  <h2 align="center">Pipelex API</h2>

The official REST API server for building and executing Pipelex pipelines. Deploy your pipelines as HTTP endpoints and integrate them into any application or workflow.

  <div>
    <a href="https://docs.pipelex.com/latest/api-server/"><strong>API Documentation</strong></a> -
    <a href="https://github.com/Pipelex/pipelex"><strong>Pipelex Core</strong></a> -
    <a href="https://go.pipelex.com/discord"><strong>Discord</strong></a>
  </div>
  <br/>

  <p align="center">
    <a href="https://docs.pipelex.com/latest/license/"><img src="https://img.shields.io/badge/License-Elastic--2.0-blue.svg" alt="Elastic License 2.0"></a>
    <a href="https://go.pipelex.com/discord"><img src="https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
    <a href="https://docs.pipelex.com/latest/api-server/"><img src="https://img.shields.io/badge/Docs-03bb95?logo=read-the-docs&logoColor=white&style=flat" alt="Documentation"></a>
  </p>
</div>

---

> **Released with pipelex, under pipelex's version.** This server is the [`api/` directory](https://github.com/Pipelex/pipelex/tree/main/api) of [`Pipelex/pipelex`](https://github.com/Pipelex/pipelex), and every pipelex release ships it: the `pipelex-api` package on PyPI pins the `pipelex` of the same version, and `pipelex/pipelex-api:X.Y.Z` runs pipelex X.Y.Z. It was released on its own from `Pipelex/pipelex-api` until v0.33.2, so the image tag that follows 0.33.2 is a pipelex version. The image keeps its name, its port and its `/root/.pipelex` configuration mount. Please open issues on `Pipelex/pipelex`.

# 📑 Table of Contents

- [Introduction](#introduction)
- [Quick Start with Docker](#-quick-start-with-docker)
- [Run your first pipeline](#-run-your-first-pipeline)
- [How to scale Pipelex](#-how-to-scale-pipelex)
- [API Documentation](#-api-documentation)
- [Support](#-support)
- [License](#-license)

# Introduction

The **Pipelex API Server** is a FastAPI-based REST API that allows you to execute [Pipelex](https://github.com/Pipelex/pipelex) pipelines via HTTP requests. Deploy your pipelines as HTTP endpoints and integrate them into any application or workflow.

It is the source-available reference implementation of the **[MTHDS Protocol](https://mthds.ai)** — the minimal HTTP contract every MTHDS runner implements (`POST /execute`, `POST /start`, `POST /validate`, `GET /models`, `GET /version`). The contracts nest: **MTHDS Protocol ⊂ Pipelex API (this server) ⊂ Pipelex hosted API**. This server adds the build tooling extensions (`/build/*`) on top of the protocol; the hosted API at `api.pipelex.com/v1` adds durable runs, the method catalog, and account management on top of this server — same shapes throughout. All routes live under the `/v1` base path; the committed contract is [`pipelex-api.openapi.yaml`](https://github.com/Pipelex/pipelex/blob/main/docs/api-server/openapi/pipelex-api.openapi.yaml).

# 🚀 Quick Start with Docker

**Official Docker image available at:** [`pipelex/pipelex-api`](https://hub.docker.com/r/pipelex/pipelex-api)

The published image is **generic and configuration-light**: Temporal is off, no S3, no remote tracing. It boots with a single required env var (`PIPELEX_GATEWAY_API_KEY`), and you bring your own [Pipelex configuration](https://docs.pipelex.com/latest/api-server/configuration/) on top to enable storage, tracing, Temporal, or anything else.

### 1. Run with Docker

The only required env var is `PIPELEX_GATEWAY_API_KEY`. Get a free key (with free credits) at https://app.pipelex.com, then run:

```bash
docker run --name pipelex-api -p 8081:8081 \
  -e PIPELEX_GATEWAY_API_KEY=your-pipelex-gateway-api-key \
  pipelex/pipelex-api:latest
```

To require authentication on the API, add `-e AUTH_MODE=api_key -e API_KEY=your-secret` (or `AUTH_MODE=jwt` + `JWT_SECRET_KEY`). See [`.env.example`](https://github.com/Pipelex/pipelex/blob/main/api/.env.example) for the full list of supported variables and the [Configuration page](https://docs.pipelex.com/latest/api-server/configuration/) for `--env-file` and `docker compose` patterns if you'd rather keep config out of your shell history.

If you'd rather build the image yourself instead of pulling, replace `pipelex/pipelex-api:latest` with a local tag after `docker build -f api/Dockerfile -t pipelex-api .`, run from the root of a `Pipelex/pipelex` checkout: the build context is the repository root, so the image installs the pipelex library of the same commit.

### 2. Verify

```bash
curl http://localhost:8081/health
```

The API is now running at `http://localhost:8081`. To customize behavior (enable Temporal, swap to S3 storage, layer in env-specific overrides, …), see the [Configuration page](https://docs.pipelex.com/latest/api-server/configuration/).

# 🧪 Run your first pipeline

Once `/health` is green, send an inline pipeline definition and inputs to `/v1/execute`. The example below summarizes a string with a one-pipe MTHDS bundle — no files, no auth, copy-paste:

```bash
curl -s http://localhost:8081/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "pipe_code": "summarize",
    "mthds_contents": ["domain = \"hello\"\nmain_pipe = \"summarize\"\n\n[pipe.summarize]\ntype = \"PipeLLM\"\ndescription = \"Summarize the input text in one sentence\"\ninputs = { text = \"Text\" }\noutput = \"Text\"\nprompt = \"Summarize in one sentence:\\n@text\"\n"],
    "inputs": { "text": "Pipelex turns plain-language pipeline definitions into reproducible AI workflows that run as HTTP endpoints." }
  }'
```

You'll get back a JSON response with `state: "COMPLETED"` and the summary under `pipe_output.working_memory.root.<main_stuff_name>.content`.

**Passing files (PDFs, images) as inputs.** Use the `Document` concept and point it at any HTTP(S) URL:

```json
{
  "pipe_code": "your_pipe",
  "mthds_contents": ["...your MTHDS..."],
  "inputs": {
    "cv": { "concept": "Document", "content": { "url": "https://example.com/resume.pdf" } }
  }
}
```

`Document` accepts public HTTP/HTTPS URLs, `pipelex-storage://` URIs, or base64 data URLs. For images, use the `Image` concept with the same `{ "url": "..." }` shape.

For inline MTHDS in the request, `mthds_contents` is a JSON array of raw `.mthds` (TOML) file contents as strings — typically `[open("my_pipe.mthds").read()]` from a client. See the [Pipe Run page](https://docs.pipelex.com/latest/api-server/pipe-run/) for every supported input shape and the full `/execute` reference.

# 📈 How to scale Pipelex

A single Pipelex API container is great for development, prototyping, and low-concurrency workloads — pipelines run in-process and `/v1/execute` blocks the request thread until they finish.

For production-scale workloads (high concurrency, long-running pipelines, retries, durable execution, horizontal scaling), the recommended path is to run Pipelex on top of [**Temporal**](https://temporal.io/). With Temporal enabled:

- Pipeline runs become durable workflows — survive worker crashes, support retries and timeouts out of the box.
- The API container becomes a thin orchestrator: it submits workflows to a Temporal cluster and returns a `pipeline_run_id` immediately (this is what `POST /v1/start` already does).
- Pipeline execution itself runs on a separate pool of **Pipelex workers** that you scale independently from the HTTP layer.
- Async completion callbacks (`callback_urls` + `X-Completion-Signature`, see [Pipe Run](https://docs.pipelex.com/latest/api-server/pipe-run/)) let your application be notified when each run finishes, without polling.

Pipelex already integrates with Temporal under the hood, and the Docker image accepts `TEMPORAL_API_KEY` plus a `[temporal] is_enabled = true` override in `.pipelex/`. **A complete deployment recipe (Temporal cluster sizing, worker container, autoscaling guidance, and an end-to-end docker-compose) is coming soon.** In the meantime, if you need to scale today, get in touch on [Discord](https://go.pipelex.com/discord) and we'll help you wire it up.

# 📖 API Documentation

The full reference for this API server is part of the Pipelex documentation, under [API Server](https://docs.pipelex.com/latest/api-server/):

- [Overview](https://docs.pipelex.com/latest/api-server/) — endpoints, authentication, deployment
- [Pipe Run](https://docs.pipelex.com/latest/api-server/pipe-run/) — `/execute`, `/start`, every input shape
- [Pipe Validate](https://docs.pipelex.com/latest/api-server/pipe-validate/) — `/validate`
- [Pipe Builder](https://docs.pipelex.com/latest/api-server/pipe-builder/) — `/build/inputs`, `/build/output`, `/build/runner`
- [Configuration](https://docs.pipelex.com/latest/api-server/configuration/) — env vars, mounting your own `.pipelex/` config

For broader Pipelex documentation (MTHDS language, concepts, pipe types, the Gateway): **[https://docs.pipelex.com/](https://docs.pipelex.com/)**

# 💬 Support

- **API Documentation**: [https://docs.pipelex.com/latest/api-server/](https://docs.pipelex.com/latest/api-server/)
- **Pipelex Documentation**: [https://docs.pipelex.com/](https://docs.pipelex.com/)
- **Discord Community**: [https://go.pipelex.com/discord](https://go.pipelex.com/discord)
- **Main Repository**: [https://github.com/Pipelex/pipelex](https://github.com/Pipelex/pipelex)

# 📝 License

This project is licensed under the Elastic License 2.0 (ELv2); see [LICENSE](https://github.com/Pipelex/pipelex/blob/main/LICENSE) for the terms, and the [license page](https://docs.pipelex.com/latest/license/) for how Pipelex reads them. Runtime dependencies are distributed under their own licenses via PyPI.

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025-2026 Evotis S.A.S.
