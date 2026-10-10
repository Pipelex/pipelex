# Configuration

This page covers how to configure the **Docker image** — the env vars it needs at boot, and how to pass your own Pipelex config files into the container.

For the syntax and meaning of Pipelex config itself (storage backends, tracing, inference routing, model decks, …), see the official Pipelex documentation: **https://docs.pipelex.com**. This page does not duplicate that.

> **The official `pipelex/pipelex-api` image is generic and orchestrator-agnostic.** It runs every pipeline **in-process** (no distributed orchestrator), with no S3, no remote tracing, and `openai` as the only enabled model provider. Anything environment-specific is meant to be supplied by you, on top of the image, via a mounted `.pipelex/` override file. Distributed execution (Temporal, Mistral Workflows, …) is **not** built in — it is added by installing exactly one orchestrator plugin on top of this base to produce a deployment *flavor* (see "Execution mode" below).

## Environment variables

The API reads its settings from environment variables. With Docker, the easiest way is a `.env` file:

```bash
# OpenAI API key — the image enables the openai backend, which serves every
# default language-model and image-generation tier of its model deck.
# Required only if you keep the bundled backends. If you enable other providers
# (Anthropic, Bedrock, OpenRouter, …) in a mounted backends override, you'll
# need those providers' own env vars instead — see https://docs.pipelex.com.
OPENAI_API_KEY=your-openai-api-key

# Authentication for the API itself (optional — defaults to AUTH_MODE=none)
AUTH_MODE=none                 # one of: none | api_key | jwt (any other value refuses to start)
API_KEY=your-api-key           # used when AUTH_MODE=api_key
JWT_SECRET_KEY=your-jwt-secret # used when AUTH_MODE=jwt

# Selects which pipelex_{PIPELEX_ENV}.toml override file is layered on top
# (see "Pipelex configuration files" below). Defaults to "dev" when unset.
PIPELEX_ENV=dev

# Required ONLY if you use POST /v1/start with `callback_urls`
# (see pipe-run.md → "Async Completion Callbacks"). HMAC secret shared between
# this server (signs callbacks) and your callback receiver (verifies them).
# Read lazily — the server boots without it; the env var is only required at
# the moment a callback signature is computed.
# COMPLETION_CALLBACK_SECRET=<shared-with-your-callback-receiver>

# Maximum request body size, in MiB, before the body-size middleware
# rejects with 413. Defaults to 100 MiB. Raise it for larger documents,
# lower it to harden the server. Read at startup — change requires a restart.
# MAX_REQUEST_BODY_MIB=100
# A JSON body may also nest its arrays and objects at most 128 levels deep. That bound is
# fixed, not configurable (see error-responses.md).

# ── Running a method by address (`method_ref`) ────────────────────────────
# See pipe-run.md → "Running a method by address". All read at startup.
#
# The per-instance clone cache (one entry per resolved commit SHA):
# METHOD_CACHE_DIR=/var/cache/pipelex-api-methods  # default: under the OS temp dir
# MAX_METHOD_CACHE_CLONES=64          # cached clones kept before oldest-first eviction
# MAX_METHOD_CACHE_TOTAL_KIB=524288   # total bytes across cached clones (default 512 MiB)
# MAX_METHOD_CACHE_AGE_HOURS=24       # a clone unused this long is evicted
#
# Fetched-package ceilings (enforced by the pipelex runtime on every fetch):
# PIPELEX_MAX_FETCHED_PACKAGE_FILES=256       # files in the selected package
# PIPELEX_MAX_FETCHED_PACKAGE_TOTAL_KIB=8192  # bytes across the selected package (default 8 MiB)
# PIPELEX_MAX_SCANNED_MANIFESTS=100           # METHODS.toml files considered per repository
# PIPELEX_MAX_MANIFEST_FILE_KIB=256           # per METHODS.toml read during package location
```

Pipelex config TOML files can reference env vars via `${VAR}` substitution — that's how secrets like provider API keys flow from the container's environment into Pipelex's runtime config without hard-coding them. Set whichever vars your mounted `.pipelex/` files reference.

### Setting env vars in Docker

You have three idiomatic options. Pick whichever fits your workflow — they all do the same thing.

**Option 1 — `.env` file (recommended).** Edit your `.env` and pass it to the container with `--env-file`. Best for long-lived deployments and when you want the config in version control next to your `docker-compose.yml`.

```bash
# .env
OPENAI_API_KEY=your-openai-api-key
MAX_REQUEST_BODY_MIB=200
AUTH_MODE=api_key
API_KEY=your-strong-secret
```

```bash
docker run --name pipelex-api -p 8081:8081 --env-file .env pipelex/pipelex-api:latest
```

**Option 2 — Inline `-e` flags on `docker run`.** Best for one-off overrides or quickly testing a single value without editing files.

```bash
docker run --name pipelex-api -p 8081:8081 \
  -e OPENAI_API_KEY=your-openai-api-key \
  -e MAX_REQUEST_BODY_MIB=200 \
  pipelex/pipelex-api:latest
```

**Option 3 — Compose `environment:` block.** Same as `env_file:` but inline, useful when you want the values visible in `docker-compose.yml` itself.

```yaml
services:
  pipelex-api:
    image: pipelex/pipelex-api:latest
    ports: ["8081:8081"]
    env_file: .env                # for shared values + secrets
    environment:                  # for explicit per-service overrides
      MAX_REQUEST_BODY_MIB: "200"
```

You can mix `env_file:` and `environment:` — values in `environment:` win.

> **After changing any env var, restart the container.** All API-side env vars are read once at startup; live changes don't take effect until the process restarts (`docker restart pipelex-api` or `docker compose up -d` after editing).

## Pipelex configuration files

The Pipelex runtime loads `.toml` config files in a layered, deep-merged order. Later layers override earlier ones:

1. Package defaults (shipped inside the `pipelex` Python library)
2. Global config — `~/.pipelex/pipelex.toml`
3. Project config — `{cwd}/.pipelex/pipelex.toml` (if present and different from global)
4. `pipelex_local.toml`
5. `pipelex_{PIPELEX_ENV}.toml` — picked from the `PIPELEX_ENV` env var (e.g. `pipelex_dev.toml`, `pipelex_prod.toml`)
6. `pipelex_{run_mode}.toml`
7. `pipelex_override.toml` — your final override
8. `pipelex_temporary_override.toml` — ephemeral, safe for tools to write/delete

In the official Docker image, the server's `.pipelex/` directory (`api/.pipelex/` in the pipelex repository) is copied to `/root/.pipelex` at build time, and the image holds no project-level `.pipelex/`. That means **`/root/.pipelex/` is the single config dir the runtime reads from**, and any file you mount there participates in the layering above. To override anything, you only need to provide the keys you want to change — the layering does the rest.

**The inference tree the image ships is the defaults of the `pipelex` it runs.** The image is released together with `pipelex`, under the same version, and every file under `inference/backends/`, the routing profiles and the numbered model deck files are that release's defaults, unchanged, so the models an own-key backend offers are the ones that `pipelex` lists: read `api/.pipelex/inference/backends/<backend>.toml` in the pipelex repository at the image's tag to see them. Only two things are this image's own choice: the `enabled` switches in `inference/backends.toml`, which leave `openai` and the software-only `internal` backend on and every other backend off, and the `x_custom_*` deck overrides. A copy of `inference/backends.toml` you mount yourself therefore keeps the backend list of the release you took it from, so take it again when you move to a newer image. The numbered deck points its default language-model and image-generation tiers at models that only `openai` and `azure_openai` serve, so a deployment that runs on another provider also repoints those aliases in an `x_custom_llm_deck.toml` override of its own.

For the schema and meaning of every key in these files, see https://docs.pipelex.com.

## Orchestration mode

The base is **orchestrator-agnostic**. WHICH backend a top-level run dispatches to is a deployment choice, read from a separate **`api.toml`** config file (not the main `pipelex_{env}.toml` — the core config rejects unknown sections). It is layered exactly like the Pipelex config above, but with its own base name: `api.toml` (packaged default) → `api_{PIPELEX_ENV}.toml` → `api_override.toml`. Two keys:

| Key | Meaning | Base default |
| --- | --- | --- |
| `orchestration_mode` | Which **backend** (orchestrator) a top-level run dispatches to. An **open string token**: `direct` (in-process), `temporal`, and any plugin-provided token are accepted; an unregistered token fails loud at dispatch with the plugin's install hint. | `direct` |
| `allow_request_orchestration_mode_override` | Whether a caller may set `orchestration_mode` per request on `POST /v1/execute`, `POST /v1/start`, and `POST /v1/validate`. When `false`, a requested token that differs from the deployment default is refused with a `403`. | `false` |

The packaged default (`orchestration_mode = "direct"`, override off) is what the generic image ships.

**Boot-coherence guard.** A process boots under exactly one orchestrator (the server derives it from `orchestration_mode`), so enabling `allow_request_orchestration_mode_override` on a `direct` default is **refused at boot**: a request overriding to a non-direct mode would resolve that orchestrator's dispatch arm while the process claimed no async execution hub, failing only at dispatch. The app fails fast at startup instead — set a non-direct `orchestration_mode` default (which claims the hub, and still serves a per-request `direct` override in-process) or leave override off.

**`orchestration_mode` is one of two orthogonal axes.** It names only the **backend**. The other axis — *delivery*, i.e. whether the caller waits — is **endpoint-intrinsic**, never configured and never requestable:

- `POST /v1/execute` and `POST /v1/validate` are **synchronous** (`BLOCKING` delivery): they return the full output / the verdict.
- `POST /v1/start` is **fire-and-forget** (`FIRE_AND_FORGET` delivery): it returns immediately with a `workflow_id`. It works only on a backend that is genuinely async-capable. A Temporal deployment (`orchestration_mode = "temporal"`) enqueues on `/start` and returns a `workflow_id`. On the orchestrator-agnostic base (`orchestration_mode = "direct"`) the in-process orchestrator is blocking-only, so `/start` is **HONEST**: it refuses with a `400` (`StartRequiresAsyncOrchestration`) — use `/execute` — rather than silently running blocking and acking.

So a deployment sets **one** `orchestration_mode` and each endpoint applies its own delivery — there is no fire-and-forget token to configure or request.

**`orchestration_mode` vs `boot_orchestrator` — two knobs, two jobs.** `orchestration_mode` (here) selects the backend a **top-level entry** (`/execute`, `/start`, `/validate`) dispatches to. `boot_orchestrator` (a core Pipelex setting) selects the **execution stack** used wherever a pipe actually runs — on a distributed worker, and for the in-process scoping inside the `direct` orchestrator. On a correctly-configured deployment the two agree (a Temporal flavor sets `orchestration_mode = "temporal"` *and* boots under Temporal); keeping them distinct is what lets `orchestration_mode` be the single source of truth for top-level dispatch without coupling it to how the stack is booted. A `temporal` `orchestration_mode` still requires the process to be booted under Temporal — set them together on a Temporal flavor.

A **flavor** image (e.g. the hosted Temporal flavor) installs one orchestrator plugin and bakes an `api_{env}.toml` to flip the default, e.g.:

```toml
# api_prod.toml  (keys at the file root — no [api] wrapper)
orchestration_mode = "temporal"   # /start is fire-and-forget (async-capable); /execute + /validate stay blocking
allow_request_orchestration_mode_override = false
```

Mount your own `api_{env}.toml` / `api_override.toml` into `/root/.pipelex/` exactly like any other override file (see below).

## Providing your own configuration to Docker

Two patterns. Both rely on mounting files into `/root/.pipelex/` inside the container.

### Option 1 — Override individual files

You can mount **any single file** that lives under `/root/.pipelex/` in the image. The bind mount replaces just that one file; everything else stays as shipped. **Recommended for most users.**

Common targets:

```yaml
services:
  pipelex-api:
    image: pipelex/pipelex-api:latest
    ports: ["8081:8081"]
    env_file: .env
    volumes:
      # Layer your overrides on top of the baseline (one of the override tiers
      # — see "Pipelex configuration files" above for the load order):
      - ./pipelex_override.toml:/root/.pipelex/pipelex_override.toml:ro

      # Or env-specific (selected by PIPELEX_ENV):
      - ./pipelex_dev.toml:/root/.pipelex/pipelex_dev.toml:ro

      # Or replace inference layer files directly:
      - ./backends.toml:/root/.pipelex/inference/backends.toml:ro
      - ./routing_profiles.toml:/root/.pipelex/inference/routing_profiles.toml:ro

      # Or the telemetry config:
      - ./telemetry.toml:/root/.pipelex/telemetry.toml:ro
```

In other words: any `.toml` file the runtime reads from `/root/.pipelex/` (top-level files OR nested files like `inference/backends.toml`) is replaceable via a single-file bind mount. The image keeps everything else, so you only ship what differs.

For overrides that fit the layering model (`pipelex_override.toml`, `pipelex_<env>.toml`, …), Pipelex deep-merges them on top of the baseline. For files that aren't layered (like `inference/backends.toml`), the mount fully replaces the file — so include all the keys you need.

### Option 2 — Replace the entire config directory

Drop a full `.pipelex/` next to your `docker-compose.yml`:

```yaml
services:
  pipelex-api:
    image: pipelex/pipelex-api:latest
    ports: ["8081:8081"]
    env_file: .env
    volumes:
      - ./.pipelex:/root/.pipelex:ro
```

Use this when you want full control — for example, to ship your own inference backends, model deck, or routing profiles. You're now responsible for keeping the contents in sync with the version of Pipelex inside the image (the image's bundled `inference/`, `pipelex.toml`, etc. are no longer present at runtime).

!!! warning "Your `pipelex.toml` must re-supply the logging keys"

    The shipped `pipelex.toml` is what puts this server on structured logs, and replacing the directory replaces it. Without these three keys Pipelex falls back to its own defaults, which are written for someone at a terminal: the Rich console sink instead of JSON lines, and the "Output of pipe" panel rendered on the thread serving each request. Copy them into your own file:

    ```toml
    [runtime.log]
    sink = "json"
    console_log_target = "stderr"
    pretty_print_mode = "silent"
    ```

    See [Logging](logging.md#configuration) for what each one does. Option 1 above does not have this problem — a layered override keeps the keys you did not mention.

### `docker run` equivalent

```bash
docker run --name pipelex-api -p 8081:8081 \
  --env-file .env \
  -v $(pwd)/pipelex_override.toml:/root/.pipelex/pipelex_override.toml:ro \
  pipelex/pipelex-api:latest
```

## Quick recipes

### Local, default everything

`.env`:

```bash
OPENAI_API_KEY=your-openai-api-key
```

`docker-compose.yml`:

```yaml
services:
  pipelex-api:
    image: pipelex/pipelex-api:latest
    ports: ["8081:8081"]
    env_file: .env
```

`docker compose up`, then `curl http://localhost:8081/health`. No override file needed.

### Local, with API key auth

Same as above but add:

```bash
AUTH_MODE=api_key
API_KEY=your-strong-secret
```

Clients now need `Authorization: Bearer your-strong-secret`.

### Documents on an intranet host, or egress through a proxy

When a run fetches a URL that a value carries (a document to extract, a prompt image for a provider that does not take URLs, a generated image a provider returned as a link), the runtime refuses a host that is `localhost`, a cloud metadata alias, or that resolves to a private, loopback, link-local or metadata address, on the first request and on every redirect hop. The pipe fails with `SsrfBlockedError` naming the host. The guarded fetch also connects directly, ignoring `HTTP_PROXY` and `HTTPS_PROXY`. The image ships with the guard on, which is right for any deployment that runs methods it did not write.

A deployment whose documents live on an intranet host, or whose only way out is an HTTP proxy, turns it off in a `pipelex_override.toml`:

```toml
[runtime.network]
is_fetch_ssrf_guard_enabled = false
```

Webhook delivery stays guarded whatever this says.

### Customizing Pipelex (storage, tracing, inference, model decks, …)

Write a `pipelex_override.toml` (or env-specific `pipelex_<env>.toml`) with the keys you want to change. Reference any provider credentials from env vars via `${VAR}` so they stay out of the file. Mount it into the container as shown above. Refer to https://docs.pipelex.com for the full set of available keys and their semantics.
