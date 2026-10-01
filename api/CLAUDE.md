# Pipelex API

Pipelex API is the official FastAPI REST server for [Pipelex](https://github.com/Pipelex/pipelex). It wraps the Pipelex core library and exposes pipeline building, execution, and validation as HTTP endpoints. It is designed to be deployed via Docker and consumed by frontends, agents, and external services.

## Where this server lives

This directory is the `api/` member of the pipelex repository's uv workspace: the distribution `pipelex-api`, the import package `pipelex_api`, and the image `pipelex/pipelex-api`. It moved here from the `Pipelex/pipelex-api` repository at that repository's last release, v0.33.2, which remains the place to read its history; `git blame` here starts at the import. Its own `CHANGELOG.md` stops at 0.33.2, and a change to the server is now an entry in pipelex's `CHANGELOG.md`, at the repository root.

- **It runs the pipelex of the same commit.** `pyproject.toml` takes `pipelex` from the workspace (`[tool.uv.sources] pipelex = { workspace = true }`), and the repository keeps one `uv.lock`, at its root. There is no pin to bump and no git source to move: a library change reaches the server in the change that makes it, and the server's gate, which the root `make agent-check` and `make agent-test` run, fails that change when it breaks the server. pipelex's pull-request workflows do not run that gate, so run it before pushing. The dependency names no version, since uv ignores a specifier on a workspace source.
- **It has the library's version.** `pyproject.toml` declares the version dynamic and hatch reads it from the root `pyproject.toml` (`[tool.hatch.version]`), so a release bumps one file and `/v1/version`, the OpenAPI artifact and the image tag (`make deploy-docker-hub`) all carry the library's number. The published wheel's exact pin on `pipelex` is still to be added with the release chain that publishes it.
- **It has its own environment.** Every uv command in the Makefile targets `api/.venv` (`UV_PROJECT_ENVIRONMENT`), where `uv sync` installs this member with its extras and pipelex, in editable mode, with the server's extras and without `cli`. The targets that need the environment provision it, so a fresh worktree needs nothing run by hand first.
- **Its gate runs from the root.** The root `make agent-check` ends with `make -C api agent-check` and the root `make agent-test` with `make -C api agent-test`; run them here directly while working on the server. Upgrading dependencies is done for the whole workspace, at the root.
- **The image is built from the repository root** as its context, `docker build -f api/Dockerfile .`, which is what `make docker-build` runs, so the image installs the pipelex of the same commit. The root `.dockerignore` keeps that context to the files the build reads.

## Project Structure

```
pipelex_api/
  main.py              # App init (PipelexFastAPI), middleware, router registration (mounts at /v1)
  openapi_schema.py    # PipelexFastAPI — publishes every 4xx/5xx as application/problem+json
  openapi_responses.py # ProblemDocument + the shared per-status `responses=` declarations
  security.py          # Authentication (API Key + JWT)
  schemas/models.py    # Pydantic request/response models
  routes/
    health.py          # GET /health (no auth)
    version.py         # GET /v1/version (no auth — MTHDS Protocol handshake)
    pipelex/
      pipeline.py      # POST /v1/execute, /v1/start (MTHDS Protocol run routes)
      validate.py      # POST /v1/validate
      resolve.py       # POST /v1/resolve (closure → normalized crate)
      pipe_io.py       # POST /v1/pipe-io (closure → one pipe's, or every pipe's, I/O artifacts; no dry run)
      codegen.py       # POST /v1/codegen (crate → typed artifacts)
      crate_ops.py     # Closure resolution, the pipe selection chain, and the invalid-arm envelope the crate routes share
      tools.py         # POST /v1/lint, /v1/format (editor tooling)
      build/           # POST /v1/build/{inputs,output,runner}
      agent/           # POST /v1/build/{concept,pipe-spec}, GET /v1/models
tests/
  unit/                # Unit tests
scripts/
  export_openapi.py    # Writes or drift-checks the committed OpenAPI artifact
  sync_vendored_kit.py # Writes or drift-checks the vendored .pipelex/inference/ tree
```

This server is the reference implementation of the [MTHDS Protocol](https://mthds.ai): `POST /execute`, `POST /start`, `POST /validate`, `GET /models`, `GET /version` under the `/v1` base path, tagged `x-mthds-protocol: true` in the committed OpenAPI artifact (`docs/openapi/pipelex-api.openapi.yaml`, regenerated via `make openapi-export`, drift-checked via `make openapi-check`). Contract nesting: MTHDS Protocol ⊂ Pipelex API ⊂ Pipelex hosted API.

**Only those five operations carry `x-mthds-protocol`** — the flag is how a conformance suite or a third-party runner extracts the portable subset of the artifact, so tagging a Pipelex route would misrepresent the standard. Everything else this server serves is a Pipelex API extension: `/resolve` + `/codegen`, `/pipe-io`, `/build/*`, and `/lint` + `/format`. Watch `/resolve` and `/codegen` in particular: they *look* protocol-shaped (they speak the `/validate` verdict discipline, and the crate `/resolve` emits is genuinely standard-owned — the MTHDS Library Crate Format, so its wire fields stay brand-neutral), but the routes are ours and the standard specifies no type projection at all. `tests/unit/test_openapi_contract.py` pins the tagged set exactly, in both directions.

pipelex's own models ride this wire (the run result, the bundle blueprint, the validation error vocabulary), so a library change can move the artifact with no change to the server's code. `openapi-check` is part of `make agent-check` for that reason: regenerate with `make openapi-export` and read the diff, which states what the change did to the server's callers.

## The vendored inference tree

The image serves the models its `/root/.pipelex/inference/` tree declares, which is this member's `.pipelex/inference/`, and `make run` and the tests read the same tree. pipelex never falls back to the kit inside its own package once a config directory exists, so a kit change reaches the server only when this tree moves with it. `scripts/sync_vendored_kit.py` owns the tree: the kit's backend files, routing profiles, numbered deck files and manifests are mirrored byte for byte, while the `enabled` switches in `inference/backends.toml` and the `x_custom_*` deck overrides stay this server's own choice.

**The tree stays committed and checked, rather than generated when the image is built.** A kit change is synced in the same change that makes it: the root `make up-kit-configs` (`ukc`), the step a kit change already takes, runs the sync here too, and `make kit-check`, part of `make agent-check`, fails a change that skipped it. Generating the tree at build time was rejected for two reasons. `make run` and the tests read the committed tree, so an image generating its own would serve something no local run had exercised. And the sync refuses when the kit ships an entry none of its rules covers, which only a person can resolve, so a build-time sync would fail at release time, long after the change that caused it. Because the manifests are mirrored rather than recomputed, a release's version bump moves nothing in the tree.

## Commands

```bash
make install          # Create api/.venv and install the server's dependencies, pipelex from the workspace included
make run              # Run the API with uvicorn (hot reload, no Docker)
make fui              # Fix unused imports
make agent-check      # install, fix-unused-imports, format, lint, pyright, mypy, openapi-check, kit-check (use this)
make agent-test       # install, then the unit tests — output only on failure (use this)
make cleanderived     # Remove compiled files, caches, logs — run when the pyright/mypy cache is stale
make openapi-export   # Regenerate the committed OpenAPI artifact
make kit-sync         # Re-sync the vendored .pipelex/inference/ tree from the kit (the root `make ukc` runs it too)
make kit-check        # Fail if that tree drifts from the kit (part of agent-check)
make tp               # Run unit tests with prints visible
make test             # Run unit tests (sequential)
make gha-tests        # Tests for GitHub Actions (no inference)
make li               # lock + install
make docker-build     # Build the image from local source, with the repository root as the build context
make docker-run       # Build + run in Docker on http://localhost:8081 (foreground)
make docker-run-hub   # Pull + run the published Docker Hub image (no local build); HUB_TAG=<tag> to pin
make docker-stop      # Force-stop the Docker container
make docker-logs      # Tail Docker container logs
```

**ALWAYS** run `make agent-check` after code changes (it supersedes `make fui && make c`).
**ALWAYS** run `make agent-test` before committing to ensure tests pass (silent on success, output only on failure).

---

# Coding Standards

## Python Version

- **Python 3.11+** (requires-python = ">=3.11,<3.15")
- Avoid Python 3.10 idioms that changed in 3.11+

## Variable Naming

- Minimum 3 characters for variable names (e.g., `exc`, `idx`, not `e`, `i`)
- Exception: conventional unpacking like `_` for discarded values
- Use `for key, value in ...` instead of `for key in dict.keys()`
- Use `a = b or c` instead of `a = b if b else c`

## Type Hints

- **Always** type-annotate every function parameter and return value
- Use lowercase generic types: `dict[]`, `list[]`, `tuple[]` (not `Dict`, `List`, `Tuple`)
- Avoid `# type: ignore` -- use `cast()` or typed variables instead
- Use `Annotated` for FastAPI dependencies

## Imports

- All imports at top of file, no inline imports
- No re-exports in `__init__.py`
- `TYPE_CHECKING` blocks must be last in the import section
- Logging: `from pipelex import log`

## Enums

- Import `StrEnum` from the stdlib `enum`
- Use `match/case` for enum comparisons, never test equality directly
- Never add a default `case _:` in exhaustive match statements

## Error Handling

- Never catch generic `Exception`. Find the actual narrow exception types raised
  by the code you're calling (read the source if needed) and catch those.
- **Never** silence the `BLE001` lint rule with `# noqa: BLE001`. If `BLE001`
  fires, the right answer is always to identify the real exception types and
  narrow the `except`, not to suppress the warning.
- Always chain exceptions: `raise NewError(msg) from exc`
- Write the error message as a variable before raising
- Convert third-party exceptions to domain-specific ones

```python
try:
    result = some_operation()
except SomeSpecificError as exc:
    msg = "Descriptive message about what went wrong"
    raise DomainError(msg) from exc
```

## Pydantic Models

- Use Pydantic v2 standards
- Use `Field(default_factory=...)` for mutable defaults (lists, dicts)
- Keep models single-purpose and focused
- Use `ConfigDict(extra="forbid")` when appropriate

## Docstrings

- Google-style docstrings when needed
- Don't add docstrings to code you didn't write or change

## Testing

- **pytest-mock** only (never `unittest.mock`)
- One `TestClass` per test module
- Test files: `test_*.py` prefix
- Test data in `test_data.py` files
- Fixtures in `conftest.py` at appropriate hierarchy levels
- Use `@pytest.mark.asyncio(loop_scope="class")` for async test classes
- Use `@pytest.mark.parametrize` for multiple test cases
- Strong asserts: test values, not just types

---

# FastAPI Coding Standards

## Router Organization

- One router per feature domain, tagged for OpenAPI: `APIRouter(tags=["pipeline"])`
- Routers composed hierarchically in `routes/__init__.py`
- Auth applied at router level via `dependencies=[Depends(auth_dependency)]`
- Health check endpoint excluded from auth

## Endpoints

- All endpoints are `async`
- Always declare `response_model` on endpoints
- Use `Annotated[T, Depends(...)]` for dependency injection
- Return `JSONResponse` with `model_dump(mode="json", serialize_as_any=True, by_alias=True)` for complex responses

```python
@router.post("/execute", response_model=PipelexRunResult)
async def execute(
    run_request: Annotated[RunRequest, Depends(request_deserialization)],
) -> PipelexRunResult: ...
```

## Error Responses

Every error is rendered as RFC 7807 `application/problem+json` by the global handlers in `pipelex_api/exception_handlers.py`. **Route handlers do not shape errors themselves** — they call into pipelex and let exceptions propagate. The wire contract is documented at `docs/error-responses.md`.

- **Domain errors** (pipelex `PipelexError` subclasses) — raise from your code and let them propagate. The `PipelexError` global handler obtains an `ErrorReport` via `to_error_report()` and renders it into a problem document. Do not wrap, classify, or re-shape.
- **API-authored 4xx/5xx** — use the helpers in `pipelex_api/errors.py`: `raise_validation_error`, `raise_bad_request`, `raise_forbidden`, `raise_unauthenticated`, `raise_payload_too_large`, `raise_internal_server_error`. Each raises an `ApiError` carrying a pre-built problem document; the global handler emits it. **Do not raise `HTTPException` directly** — FastAPI's default handler wraps the body as `{"detail": <whatever>}` and cannot emit a flat RFC 7807 document.
- **Auth errors** — the helpers set `WWW-Authenticate: Bearer` automatically on 401.
- **Logging** — the global handlers emit one structured record per error, carrying `event: "api_error"`, `route`, `error_type`, `error_domain`, `retryable`, `status`, and `user_id` / `pipe_code` / `pipeline_run_id` when the request bound them. `detail` rides the API-authored path only: a Pipelex `ErrorReport`'s body text has been through disclosure redaction, so it is not the cause and is deliberately not logged. They travel as `fields=` on the runtime's log call, never interpolated into the message, and `request_id` is not among them: `RequestIdMiddleware` binds it on the runtime's log context, so every record emitted under the request already carries it. The server selects the `json` sink, so a record reaches stderr as one JSON object per line — see `docs/logging.md`. Log disposition follows the final HTTP status: 4xx logs at `warning` (caller mistakes, the provider-429 passthrough, and API-level 4xx overrides like the 409 conflict); 5xx logs at `error` with traceback. Routes should not log error tracebacks themselves.
- **Documenting a failure in OpenAPI** — the shared, typed `responses=` declarations live in `pipelex_api/openapi_responses.py` (`ProblemDocument` + one constant per status). Every auth-wrapped `/v1` route already documents `401`/`413`/`422`/`500` via the composite router's `responses=` (`pipelex_api/routes/__init__.py`); a route declares on its own decorator only the statuses **it alone** can produce. Never hand-write an error `content` block: `pipelex_api/openapi_schema.py` re-keys the generated schema onto `application/problem+json`, because FastAPI renders a response `model` under the route's response-class media type and offers no per-response override. Adding a new status means adding a constant there and referencing it — then `make openapi-export`.

Typical route:

```python
@router.post("/start", response_model=PipelexStartAck, status_code=202)
async def start(
    request: Request,
    run_request: Annotated[RunRequest, Depends(request_deserialization)],
    user: Annotated[RequestUser | None, Depends(get_optional_user)],
) -> PipelexStartAck:
    # Let PipelexError / EnvVarNotFoundError / etc. propagate to the global handler.
    # `request_id_of` (pipelex_api/middleware.py) reads back what RequestIdMiddleware put on the request.
    return await api_runner.start(run_request, user=user, request_id=request_id_of(request))
```

For an API-authored failure that has no `PipelexError`:

```python
if upload_size > MAX_UPLOAD_BYTES:
    raise_payload_too_large(message=f"Upload exceeds {MAX_UPLOAD_BYTES} bytes.")
```

## Request/Response Models

- Define in `pipelex_api/schemas/models.py`
- Use `Field(...)` with `description` for required fields
- Use descriptive field names

## Authentication

- Three modes via `AUTH_MODE` env var: `none` (default), `jwt`, `api_key`
- `none`: No auth (self-hosted default, or behind API Gateway in hosted version)
- `jwt`: Validate `Authorization: Bearer <jwt>` using `JWT_SECRET_KEY`
- `api_key`: Validate `Authorization: Bearer <key>` against `API_KEY` env var
- Selection is environment-based via `get_auth_dependency()`
- Bearer token format for jwt and api_key modes

## Middleware

- CORS configured in `main.py` (permissive for all origins)
- No custom middleware -- keep it simple

## Pipelex Integration

- App initializes with `Pipelex.make(IntegrationMode.FASTAPI)`
- Use `ApiRunner` (extends `PipelexMTHDSProtocol`) for pipeline execution
- Services are instantiated per-request, not as singletons
