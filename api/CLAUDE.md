# Pipelex API

Pipelex API is the official FastAPI REST server for [Pipelex](https://github.com/Pipelex/pipelex). It wraps the Pipelex core library and exposes pipeline execution, validation and method tooling as HTTP endpoints. It is designed to be deployed via Docker and consumed by frontends, agents, and external services.

## Where this server lives

This directory is the `api/` member of the pipelex repository's uv workspace: the distribution `pipelex-api`, the import package `pipelex_api`, and the image `pipelex/pipelex-api`. It moved here from the `Pipelex/pipelex-api` repository at that repository's last release, v0.33.2, which remains the place to read its history; `git blame` here starts at the import. Its own `CHANGELOG.md` stops at 0.33.2, and a change to the server is now an entry in pipelex's `CHANGELOG.md`, at the repository root.

- **It runs the pipelex of the same commit.** `pyproject.toml` takes `pipelex` from the workspace (`[tool.uv.sources] pipelex = { workspace = true }`), and the repository keeps one `uv.lock`, at its root. There is no pin to bump and no git source to move: a library change reaches the server in the change that makes it, and the server's gate fails that change when it breaks the server. The root `make agent-check` and `make agent-test` run that gate, and so does every pull request, with no path filter: `Lint (api)`, `Tests (api)`, `Tests (packages)` and `Tests (api image)` in pipelex's workflows.
- **It has the library's version.** `pyproject.toml` declares the version dynamic and hatch reads it from the root `pyproject.toml` (`[tool.hatch.version]`), so a release bumps one file and `/v1/version`, the OpenAPI artifact and the image tag (`make deploy-docker-hub`) all carry the library's number.
- **Its dependencies are written in the metadata hook's table.** `dependencies` is dynamic: the server's requirements live in `[tool.hatch.metadata.hooks.custom]` of `pyproject.toml`, and `hatch_build.py` writes them into the metadata, pinning each `lockstep-dependencies` entry (pipelex with the server's extras) to `==` the release's version. uv ignores that pin on the workspace source, so it changes nothing here; in a published wheel it makes `pip install pipelex-api` take exactly the pipelex it was released with. Add or change a server dependency in that table by hand, then `make lock` at the root: `uv add` would write a static `[project] dependencies` list, which hatch refuses beside the dynamic one. `scripts/check_lockstep_pin.py` (`make build check-lockstep-pin`) checks the pin in a build, and the release workflow runs it before uploading.
- **It has its own environment.** Every uv command in the Makefile targets `api/.venv` (`UV_PROJECT_ENVIRONMENT`), where `uv sync` installs this member with its extras and pipelex, in editable mode, with the server's extras and without `cli`. The targets that need the environment provision it, so a fresh worktree needs nothing run by hand first.
- **Its gate runs from the root.** The root `make agent-check` ends with `make -C api agent-check` and the root `make agent-test` with `make -C api agent-test`; run them here directly while working on the server. Upgrading dependencies is done for the whole workspace, at the root.
- **The image is built from the repository root** as its context, `docker build -f api/Dockerfile .`, which is what `make docker-build` runs, so the image installs the pipelex of the same commit. The root `.dockerignore` keeps that context to the files the build reads. `make docker-smoke` boots the image and checks that `/v1/version` reports this version for both the server and its pipelex.
- **A pipelex release ships it.** The root's `.github/workflows/publish-pypi.yml` publishes the `pipelex-api` wheel and sdist once the `pipelex` wheel is on PyPI and the release is tagged, then calls `publish-docker-hub.yml` to push `pipelex/pipelex-api:X.Y.Z` from the commit the tag names through `make deploy-docker-hub`, which smoke-tests before it pushes. `latest` moves only to the newest stable release, and a version already on Docker Hub is never rebuilt. A failed push is retried by re-running the failed job, or by dispatching `publish-docker-hub.yml` with the version. The Docker Hub overview is not part of the chain and is still updated by hand from `README.md`. `docs/contribute/api-server.md` at the root describes the whole chain.
- **Its documentation is part of the pipelex docs site**: the pages are `docs/api-server/` at the repository root, served by the root `make docs` and checked by `make docs-check`, and published on docs.pipelex.com with each release. The committed OpenAPI artifact sits among them, at `docs/api-server/openapi/pipelex-api.openapi.yaml`.

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
    blob_upload.py     # PUT /v1/blobs/{sha256} (no bearer auth — the signed upload target authorizes it)
    pipelex/
      pipeline.py      # POST /v1/execute, /v1/start (MTHDS Protocol run routes)
      blobs.py         # POST /v1/blobs/missing (MTHDS Protocol blob route; the signed upload targets)
      validate.py      # POST /v1/validate
      method_selection.py # The method tree a diagnostic request names (`files` or `method_ref`), read as the run routes read it
      resolve.py       # POST /v1/resolve (method tree → normalized crate)
      pipe_io.py       # POST /v1/pipe-io (method tree → one pipe's, or every pipe's, I/O artifacts; no dry run)
      codegen.py       # POST /v1/codegen (crate → typed artifacts)
      crate_ops.py     # Writing and resolving the method's tree, the pipe selection chain, and the invalid-arm envelope the crate routes share
      tools.py         # POST /v1/lint, /v1/format (editor tooling)
      agent/           # GET /v1/models, GET /v1/models/check (the model reference check)
tests/
  unit/                # Unit tests
scripts/
  export_openapi.py        # Writes or drift-checks the committed OpenAPI artifact
  sync_vendored_kit.py     # Writes or drift-checks the vendored .pipelex/inference/ tree
  check_lockstep_pin.py    # Checks that a built wheel and sdist pin pipelex to the release's version
  check_served_version.py  # Checks the versions a running server reports (make docker-smoke)
hatch_build.py             # The metadata hook that writes the dependencies and the lockstep pin
```

This server is the reference implementation of the [MTHDS Protocol](https://mthds.ai): `POST /execute`, `POST /start`, `POST /validate`, `GET /models`, `GET /version`, and the optional blob routes `POST /blobs/missing` and `PUT /blobs/{sha256}`, under the `/v1` base path, tagged `x-mthds-protocol: true` in the committed OpenAPI artifact (`docs/api-server/openapi/pipelex-api.openapi.yaml` at the repository root, regenerated via `make openapi-export`, drift-checked via `make openapi-check`). Contract nesting: MTHDS Protocol ⊂ Pipelex API ⊂ Pipelex hosted API.

**Only the protocol's own operations carry `x-mthds-protocol`** — the flag is how a conformance suite or a third-party runner extracts the portable subset of the artifact, so tagging a Pipelex route would misrepresent the standard. Everything else this server serves is a Pipelex API extension: `/resolve` + `/codegen`, `/pipe-io`, `/models/check`, and `/lint` + `/format`. Watch `/resolve` and `/codegen` in particular: they *look* protocol-shaped (they speak the `/validate` verdict discipline, and the crate `/resolve` emits is genuinely standard-owned — the MTHDS Library Crate Format, so its wire fields stay brand-neutral), but the routes are ours and the standard specifies no type projection at all. `tests/unit/test_openapi_contract.py` pins the tagged set exactly, in both directions.

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
make build            # Build the pipelex-api wheel and sdist into dist/
make check-lockstep-pin  # Check that the built distributions pin pipelex to this version
make docker-build     # Build the image from local source, with the repository root as the build context
make docker-smoke     # Boot the built image and check /health and the versions /v1/version reports
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
- The one exception is the absolute root of the API, the case pipelex's own
  rule sanctions: `AnsweredErrorBarrier` in `pipelex_api/exception_handlers.py`,
  outside Starlette's catch-all, which must stop whatever reaches it. It takes
  the suppression form pipelex uses, `# ruff: ignore[BLE001]`, with a comment
  line under the `except` naming that case. The code is spelled out because this
  member's ruff runs without `preview`, which a rule's name, as pipelex writes
  it (`blind-except`), needs.
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
- A router whose routes declare a JSON body is built with `route_class=JsonBodyRoute` (`pipelex_api/json_body.py`), which refuses a body nested deeper than `MAX_JSON_NESTING_DEPTH` before FastAPI parses it; `tests/unit/test_json_body.py` fails on a body-declaring route that is not one. A route that reads its raw body parses it with `decode_json_body`, never with a bare `json.loads`
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

Every error is rendered as RFC 9457 `application/problem+json` by the global handlers in `pipelex_api/exception_handlers.py`, and every problem carries a registry `code`, a 404 or a 405 included; there is no `error_type` and no `instance`, and `request_id`, which `RequestIdMiddleware` takes from an inbound `X-Request-ID` or mints, correlates a response with its log lines. **Route handlers do not shape errors themselves** — they call into pipelex and let exceptions propagate. The wire contract is documented at `docs/api-server/error-responses.md`, at the repository root.

- **Domain errors** (pipelex `PipelexError` subclasses) — raise from your code and let them propagate, choosing the error's code and parameters where you raise it (`with_error_code()`, `with_params()`) when its class declares a set. The `PipelexError` global handler builds the error's problem in the operator view, `to_problem(view=ProblemView.OPERATOR)`, and `problem_response` renders it with the status the problem's code declares, in the view the request's identity gives it (`pipelex_api/problem_view.py`: the operator's for the API key and for a request the trusted proxy forwarded, the caller's otherwise). A failure a route receives as a value, such as a validator's refusal that carries no validation items, goes through `problem_response` too. Do not wrap, classify, or re-shape.
- **The runner's own refusals** are `PipelexError`s too, the classes of `pipelex_api/exceptions.py`, each declaring its code or its set of codes: `RunnerRequestError` (`request.invalid` naming the refused `field`, or the code the raise site chooses: `request.malformed` with a `reason`, `request.too_large` with `limit` and `size`, `request.unsupported`, `request.blobs_missing`, `request.not_found`, `request.method_not_allowed`, and `runtime.unavailable` for a framework 429), `RunnerAuthError` (the `auth.*` codes and `pipelex.deployment.token_claims_invalid`, with the `challenge` its 401 carries), `RunnerMisconfiguredError` (`runtime.misconfigured`, its `component` read by the operator alone), `RequestMethodError` (`method.package_invalid` with a `reason`, a `MethodPackageReason` or the standard's tree refusal code, and a `path` or a `limit`, `method.syntax`, `method.resource_missing`, `security.input_path_refused`), `RequestFieldConflictError` (`request.invalid` from a model validator judging several fields, naming the one to change), `BlobStoreDamagedError` (`pipelex.storage.not_found`, a 500 never retried, which the routes reading held blobs declare as `PROBLEM_500_HELD_BLOBS`), `OrchestrationOverrideForbiddenError`, `CustomCodeRequiresSandboxError`, `ReservedObjectKeyError` and `CallbackUrlRefusedError`. Raise one, choosing the code with `with_error_code()` and giving its parameters with `with_params()`; the message is the operator's and rides `diagnostics` alone, while the caller reads the code's sentence. A new class goes in that module, declares its code in its own body (`tests/unit/test_error_code_gate.py`), and is recorded with the root `make generate-error-identity`. A request the route's model refuses becomes `request.invalid` with one item per refused field (`pipelex_api/request_refusals.py`); a model validator over several fields raises `RequestFieldConflictError` so its item names a field rather than `body`. A typed body is parsed by `JsonBodyRoute` before FastAPI validates it, so a body that does not decode or parse is the caller's `request.malformed`, never FastAPI's bare 400. Pick the registry code that fits; the vendored registry is not edited here. **Do not raise `HTTPException` directly** — no route raises one: `handle_http_exception` answers the framework's own, each 4xx keeping its status and its meaning under a code whose required parameters the runner can fill, since the framework names nothing but a status and a header (`framework_refusal`: a 400 or 422 is `request.malformed` with the reason `unreadable`, a 401 `auth.missing_credential` keeping its challenge, a 403 `auth.invalid_credential`, a 404 or 405 from routing, a 413 `request.malformed` with the reason `too_large`, a 429 `runtime.unavailable` naming the rate limiter, keeping its `Retry-After`, any other `request.malformed` with the reason `unreadable`; `tests/unit/test_exception_handlers.py` checks every 4xx fills its code's parameters), never as a 500, and a 5xx as `runtime.unexpected`. A refusal standing in for a framework exception (`_standing_in_for`) is chained from it, so the record's `error.chain` names it.
- **Auth errors** — a 401 carries the `WWW-Authenticate` challenge its `RunnerAuthError` names, `Bearer` from the token and API-key verifiers, and none behind a trusted proxy, which reads no bearer token; `problem_json_response` adds no challenge of its own. A forwarded `X-User-Id` that is not path-safe is a `RunnerRequestError` naming the header, a 422.
- **Logging** — the global handlers emit one structured record per error, with the fixed message `A request ended in an error response` (the key the error stream is selected by; there is no `event` field) and the fields `url.path`, `error.code`, `error.type`, `error.chain`, `error_domain`, `retryable`, `http.response.status_code`, and `user.id` / `pipe_code` / `pipeline_run_id` when the request bound them, plus `error_category` and the diagnostics' `backend_name`, `model_handle`, `provider_status_code` and `provider_request_id` when the failure has them. `error.type` is the class of the exception that escaped, which for an exception that is not a `PipelexError` is that exception's class rather than the stand-in its problem names, and `error.chain` the classes of the exceptions it was raised from or while handling. **No record carries an exception's text or its traceback**: a foreign exception's text can quote a run's inputs or a model's answer, so an `error` record adds `error.frames`, where the deepest exception of the chain was raised, every record adds the problem's operator-only parameters as `error.params.<name>` (the `component` of a `runtime.misconfigured`), and the message rides the operator view's `diagnostics` alone, which only an operator-authenticated request reads. `AnsweredErrorBarrier`, between `RequestIdMiddleware` and the app in `main.py`, stops the exception Starlette's `ServerErrorMiddleware` raises again after the catch-all answered it, so uvicorn never logs its traceback; a failure no handler recorded once a response had started, the catch-all's own, it records first as `A request failed after its response had started`, by class alone. The record is built from the operator view, and carries no `detail`. The fields travel as `fields=` on the runtime's log call, never interpolated into the message, and `request_id` is not among them: `RequestIdMiddleware` binds it on the runtime's log context, so every record emitted under the request already carries it. The server selects the `json` sink, so a record reaches stderr as one JSON object per line — see `docs/api-server/logging.md` at the repository root. The record's level says who has to act (`record_level_of`, from the final HTTP status and the code's domain, the registry's who-must-act): a 4xx logs at `warning` (caller mistakes, the provider-429 passthrough, and the 409 conflict); a 5xx logs at `error`, with frames, only when its domain is `runtime` or `operator`, and at `warning` without frames when it is a 501, what this deployment does not offer, which any caller can ask for again, or when its domain is the caller's; a routing 404 or 405 logs at `debug`, as scanners send them by the thousand. Decide a new level from those two facts, never from a list of codes. A security refusal also logs its security event. Routes should not log errors themselves.
- **Documenting a failure in OpenAPI** — the shared, typed `responses=` declarations live in `pipelex_api/openapi_responses.py` (`ProblemDocument` + one constant per status, such as `PROBLEM_404_METHOD_PACKAGE`, `PROBLEM_409_DUPLICATE_RUN`, `PROBLEM_501_RUN_POLICY` and `PROBLEM_501_START`, each describing the codes it answers). Every auth-wrapped `/v1` route already documents `401`/`413`/`422`/`500` via the composite router's `responses=` (`pipelex_api/routes/__init__.py`, `COMMON_PROBLEM_RESPONSES`); a route declares on its own decorator only the statuses **it alone** can produce. A schema reachable from the standard's `ProblemItem` is published under a `Problem` prefix (`pipelex_api/openapi_schema.py`), so it never takes the name of pipelex's own model of the same name. Never hand-write an error `content` block: `pipelex_api/openapi_schema.py` re-keys the generated schema onto `application/problem+json`, because FastAPI renders a response `model` under the route's response-class media type and offers no per-response override. Adding a new status means adding a constant there and referencing it — then `make openapi-export`.

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

For a refusal the runner authors itself:

```python
if upload_size > MAX_UPLOAD_BYTES:
    msg = f"The upload is {upload_size} bytes, over the {MAX_UPLOAD_BYTES}-byte limit."
    raise RunnerRequestError(msg).with_error_code(CoreCode.REQUEST_TOO_LARGE).with_params(limit=MAX_UPLOAD_BYTES, size=upload_size)
```

## Request/Response Models

- Define in `pipelex_api/schemas/models.py`
- Use `Field(...)` with `description` for required fields
- Use descriptive field names

## Authentication

- The `AUTH_MODE` env var names an `AuthMode` member: `none` (default), `jwt`, `api_key`
- Unset or empty means `none`; any other value raises `InvalidAuthModeError` when `main.py` selects the dependency at import, so the server refuses to boot. The match is exact, case included, and there is no fallback: a mistyped mode must never serve the routes unauthenticated
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
