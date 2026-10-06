# Pipelex API Server

The Pipelex API server runs MTHDS methods over HTTP on infrastructure you host yourself. It is published as the [`pipelex/pipelex-api`](https://hub.docker.com/r/pipelex/pipelex-api) Docker image and as the `pipelex-api` package on PyPI, and its source is the [`api/` directory](https://github.com/Pipelex/pipelex/tree/main/api) of the pipelex repository.

!!! note "Released with pipelex, under pipelex's version"
    Every pipelex release also ships the server: the `pipelex-api` package pins the `pipelex` of the same version, and the image tag is that version too, so `pipelex/pipelex-api:X.Y.Z` runs pipelex X.Y.Z. The server was released on its own, from the `Pipelex/pipelex-api` repository, until v0.33.2; its image tag then jumped to the pipelex version that first shipped it. Its history up to then is the [server's changelog to v0.33.2](changelog.md), and its changes since are in the [Pipelex changelog](../changelog.md).

## The three-layer contract

This server is the source-available reference implementation of the **[MTHDS Protocol](https://mthds.ai)** — the minimal HTTP contract every MTHDS runner implements. The contracts nest:

```
MTHDS Protocol  ⊂  Pipelex API (this server)  ⊂  Pipelex hosted API
(the standard)     (protocol + extensions)       (+ durable runs, catalog, account)
```

- **MTHDS Protocol** — five routes: `POST /execute`, `POST /start`, `POST /validate`, `GET /models`, `GET /version`. Tagged `x-mthds-protocol: true` in the [committed OpenAPI artifact](openapi/pipelex-api.openapi.yaml), and **only** those five — the flag is how a conformance suite or a third-party runner extracts the portable subset.
- **Pipelex API (this server)** — the protocol verbatim, plus the Pipelex extensions: resolve and codegen (`/resolve`, `/codegen`), pipe I/O (`/pipe-io`), and editor tooling (`/lint`, `/format`). `/upload` and `/resolve-storage-url` were non-contract convenience routes and have been **removed** — see [Storage Transport](storage-transport.md) for where they went and why.
- **Pipelex hosted API** (`api.pipelex.com/v1`) — everything here, same shapes, plus durable runs, the method catalog, and account management.

All routes are served under the `/v1` base path (clients compose `{base}/v1/{endpoint}`).

## What the API Offers

The API currently allows you to:

1. **Run** any Pipelex pipeline with flexible inputs (sync or async)
2. **Validate** any Pipelex pipeline to ensure correctness
3. **Resolve** a library closure into its normalized crate, and **codegen** typed artifacts from it (TypeScript/Zod, Pydantic, Pipelex structures)
4. **Describe** a method's inputs and output — its pipe I/O contracts, input form and output form, from which a client projects an inputs template
5. **Lint and format** single `.mthds` files for editor workflows
6. **List** available model presets and configurations

## Deployment

Deploy the Pipelex API anywhere that runs Docker (your laptop, ECS, Cloud Run, Kubernetes, …) using our Docker image: [`pipelex/pipelex-api`](https://hub.docker.com/r/pipelex/pipelex-api).

### 1. Run with Docker

The only required env var is `OPENAI_API_KEY`. The image enables the `openai` backend, which serves every default language-model and image-generation tier of its model deck. To call another provider instead, such as Anthropic, Bedrock, Vertex or OpenRouter, mount your own backends override, as the [Configuration](configuration.md) page shows.

```bash
docker run --name pipelex-api -p 8081:8081 \
  -e OPENAI_API_KEY=your-openai-api-key \
  pipelex/pipelex-api:latest
```

To require authentication on the API itself, add `-e AUTH_MODE=api_key -e API_KEY=your-secret` (or `AUTH_MODE=jwt` + `JWT_SECRET_KEY`). The full set of accepted env vars is documented in [Configuration](configuration.md) and in the server's [`.env.example`](https://github.com/Pipelex/pipelex/blob/main/api/.env.example).

If you'd rather keep config out of your shell history, use `--env-file .env` or a `docker-compose.yml` instead — see [Configuration → Setting env vars in Docker](configuration.md#setting-env-vars-in-docker) for both patterns.

To build the image yourself instead of pulling, replace `pipelex/pipelex-api:latest` with a local tag after `docker build -f api/Dockerfile -t pipelex-api .`, run from the root of a `Pipelex/pipelex` checkout: the build context is the repository root, so the image installs the pipelex library of the same commit.

### 2. Verify

```bash
curl http://localhost:8081/health
```

### 3. Run your first pipeline

Send an inline MTHDS bundle and inputs to `/v1/execute`:

```bash
curl -s http://localhost:8081/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "pipe_code": "summarize",
    "mthds_contents": ["domain = \"hello\"\nmain_pipe = \"summarize\"\n\n[pipe.summarize]\ntype = \"PipeLLM\"\ndescription = \"Summarize the input text in one sentence\"\ninputs = { text = \"Text\" }\noutput = \"Text\"\nprompt = \"Summarize in one sentence:\\n@text\"\n"],
    "inputs": { "text": "Pipelex turns plain-language pipeline definitions into reproducible AI workflows that run as HTTP endpoints." }
  }'
```

The response contains `state: "COMPLETED"` and the result under `pipe_output.working_memory.root.<main_stuff_name>.content`. See **[Pipe Run →](pipe-run.md)** for every input shape (text, structured objects, `Document`, `Image`, …) and the full `/execute` and `/start` reference.

### 4. Customize the configuration

Need to change the execution mode, point to a different storage backend, or ship your own model deck? See **[Configuration →](configuration.md)** for how to provide your own `.pipelex/` config files to the Docker image. The base runs every pipeline in-process by default; distributed execution (Temporal, …) is added by a deployment flavor, not configured on the base.

## Base URL

Once deployed locally, the API is available at:

```
http://localhost:8081/v1
```

## Authentication

The API supports three authentication modes via the `AUTH_MODE` environment variable:

### No Authentication (Default)

By default (`AUTH_MODE=none`), the API requires no authentication. This is the default for self-hosted deployments and for running behind an API Gateway that handles auth.

If you sit this API behind a trusted reverse proxy that authenticates users and forwards the caller identity via the `X-User-Id` header, set `TRUST_FORWARDED_IDENTITY_HEADERS=true` to honor it. The runner is a generic execution engine — it does not own user metadata (email, OAuth subject, auth method), so a single opaque caller id is the entire trusted surface. The value must be a single path-safe segment (`is_safe_user_id`). **Default is off** — without this flag the API ignores `X-User-Id` entirely and the deployment is treated as single-tenant. With it on, a request arriving *without* the header is rejected with `401`: turning the flag on asserts that a proxy authenticates every caller, so a missing id means that proxy is absent, misconfigured or bypassed. Only enable it when your proxy strips any inbound copy of the header before adding its own; otherwise, any external client can spoof user identity by sending it directly.

### API Key Authentication

Set `AUTH_MODE=api_key` and provide the `API_KEY` environment variable. Include it in the Authorization header:

```
Authorization: Bearer YOUR_API_KEY
```

```bash
docker run --name pipelex-api -p 8081:8081 \
  -e AUTH_MODE=api_key \
  -e API_KEY=your-api-key \
  pipelex/pipelex-api:latest
```

### JWT Authentication

Set `AUTH_MODE=jwt` and provide the `JWT_SECRET_KEY` environment variable:

```bash
docker run --name pipelex-api -p 8081:8081 \
  -e AUTH_MODE=jwt \
  -e JWT_SECRET_KEY=your-jwt-secret-key \
  pipelex/pipelex-api:latest
```

**JWT Requirements:**

- Tokens must be signed with the HS256 algorithm
- Tokens must contain a `user_id` claim that is a single path-safe segment (`is_safe_user_id`) — it becomes a key segment in storage paths, so provider-issued `sub` values carrying `/`, `#` or `:` (like `"google#abc"`) are NOT accepted. Deployments using OAuth must mint their own `user_id` claim mapping each caller to such a value.
- Pass the JWT in the Authorization header: `Authorization: Bearer YOUR_JWT_TOKEN`

## API Endpoints

Every failure is an RFC 7807 `application/problem+json` problem document — see **[Error Responses →](error-responses.md)**, and the [committed OpenAPI artifact](openapi/pipelex-api.openapi.yaml) for the statuses each route can produce.

### Health & Version

- `GET /` — Service identity banner (no auth required)
- `GET /health` — Health check (no auth required)
- `GET /v1/version` — MTHDS Protocol version handshake (no auth required): `{protocol_version, implementation, implementation_version, runtime_version}`. Replaces the former `/pipelex_version` and `/api_version` routes.

### Pipe Run
Execute pipelines with flexible input formats, either synchronously or asynchronously.

- `POST /v1/execute` — Run a pipeline and wait for completion (200 + full result)
- `POST /v1/start` — Start a pipeline execution without waiting (202 + `StartAck`)

[Learn more →](pipe-run.md)

### Pipe Validate
Validate MTHDS content to ensure pipelines are correctly defined before execution.

- `POST /v1/validate` — Parse, validate, and dry-run pipelines

[Learn more →](pipe-validate.md)

### Pipe I/O
Read a method's I/O artifacts without a validation. A Pipelex API extension carrying the standard's artifacts.

- `POST /v1/pipe-io` — The pipe I/O contracts, input form and output form of one pipe, or of every pipe with `all_pipes`, beside the method's entry pipe and its pending signatures; no dry run. Takes the same closure selector as `/v1/resolve`, and `include_files` echoes the closure's `.mthds` files

[Learn more →](pipe-io.md)

### Resolve & Codegen
Resolve a library closure into its normalized crate, and project that crate into typed artifacts. Pipelex API extensions — not MTHDS Protocol routes, though the crate they emit is the standard's Library Crate Format.

- `POST /v1/resolve` — Resolve a closure into the normalized library crate (fully qualified refs, flattened refinement, materialized natives, fingerprint)
- `POST /v1/codegen` — Generate typed artifacts from the crate: `kind` (`types`) × `target` (`ts-zod`, `python-pydantic`, `python-structures`), plus the `codegen.lock` that makes the result reproducible offline

[Learn more →](codegen.md)

### MTHDS Tools
Lint and format single `.mthds` files without loading or executing a pipeline.

- `POST /v1/lint` — Return syntax, semantic, or schema diagnostics
- `POST /v1/format` — Return formatted content, changed status, and blocking syntax diagnostics

[Learn more →](mthds-tools.md)

### Models
List the models this runner can route to.

- `GET /v1/models` — The protocol model deck this runner routes to (flat `models` list, plus category-keyed `aliases`/`waterfalls` routing extensions); optional single `?type=` category filter

### Uploader (removed)

`POST /v1/upload` and `POST /v1/resolve-storage-url` have been **removed** ([Storage Transport](storage-transport.md)). The storage provider itself is untouched — only the two HTTP routes are gone.

For most use cases you don't need either: pass any public HTTP(S) URL (or base64 data URL) directly as `Document.content.url` and skip the upload step entirely.
