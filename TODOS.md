# Plan: CLI-or-API backend for MTHDS validation & graph rendering

## Goal

Today the VS Code extension validates `.mthds` bundles and renders method graphs exclusively by spawning the `pipelex-agent` Python CLI. Add a second backend that calls the **Pipelex API** (`pipelex-api`) over HTTP via the **`mthds-js`** typed client, selectable through a setting. The CLI backend stays the default and is preserved unchanged.

This plan spans three repos plus the extension. The two upstream improvements — `pipelex` (expose structured validation errors over the API) and `mthds-js` (type and surface them) — are prerequisites for validation parity and are first-class phases here.

## Decisions locked

- **Expose structured validation errors over the API** — yes, make the `pipelex` runtime change. This is the gating prerequisite for validation parity.
- **One call returns both** — when the extension needs validation details *and* the graph for the same file state, it must get both from a single backend call; no separate validate + graph round-trips. The API's `/v1/validate` already returns both. The CLI's `validate bundle --view --format json` must be extended to return both in one combined envelope (today it throws on invalid bundles instead of returning errors alongside a null graph).
- **API target** — default local self-hosted `http://localhost:8081`, changeable in settings. Optional hosted `api.pipelex.com` via an API key. Key is picked up from the environment / VS Code SecretStorage — never stored as plaintext in settings.
- **Multi-file bundles** — send every `.mthds` file in the saved file's directory as `mthds_contents[]` (mirrors the CLI's `--library-dir <dir>`).
- **HTTP client** — use `mthds-js` (`MthdsApiClient`), not a hand-rolled fetch client.
- **Default backend** — `cli` (zero-config preserved); `api` is opt-in.
- **Per-pipe FAILURE as data** — it is acceptable for `/v1/validate` to report per-pipe dry-run FAILUREs as data on a 200 response (in `validated_pipes`) rather than always raising 422. The extension surfaces both the 422 `validation_errors` and any 200 `validated_pipes` FAILUREs as diagnostics. **Reality check (verified):** this is aspirational, not current behavior — the API response model and docstrings *allow* `FAILURE` entries in `validated_pipes`, but the current route raises 422 on *any* `ValidateBundleError`, so the 200-FAILURE channel never fires today. Keep the extension defensive (treat the channel as possibly-empty), but actually producing FAILURE-on-200 would require a deliberate behavior change in pipelex / pipelex-api that is **not** scoped in Phase 1 or 2 (which only confirm/document the boundary). Decide explicitly if that channel is needed.

## Decisions locked in eng review (2026-06-15)

These supersede or refine the items above where they conflict.

- **Part B deferred.** Do NOT add a combined exit-0 `validate bundle --view --format json` envelope. Verified: `bundle_cmd.py` validates first and runs the `if view:` block only on success, so a single `--view` spawn already yields graph on exit 0 or `validation_errors` on non-zero exit. Phase 1 is **Part A only**. Part B moves to Out of scope.
- **STRICT disclosure.** `validation_errors` IS surfaced on the untrusted external surface — add it to `_STRICT_KEPT_FIELDS` (`base_exceptions.py:54`), the documented single-decision contract for both STRICT branches. Rationale is NOT "like `caller_facing_message`" (that field is kept by separate branch logic, not this set) — cite the `_STRICT_KEPT_FIELDS` contract. They're the user's own submitted-bundle diagnostics, not server internals; redacting them would gut the hosted path.
- **Conformance coverage added.** Add a `docs/specs/` ↔ `conformance/` pair for the `/v1/validate` **error** envelope (not covered today) and run `make check-spec-links`. The conformance test must assert the **real wire response**, not just the hand-maintained `pipelex-api.openapi.yaml` (which is a 4th place the shape lives — keep it in sync).
- **MIN_AGENT_VERSION → 0.34.0.** Raise the CLI floor to the Part A version so the CLI's error JSON carries `source`/`field_name` and both backends use `source`. This IS a compatibility-floor break (older CLIs get a "too old" message) — state it explicitly; "CLI unchanged" refers to behavior, not the version requirement. Use the `bump-pipelex-version` skill to keep all floor references in sync.
- **API `source` fix (load-bearing).** The validate request carries bundle text as nameless `mthds_contents: list[str]`, so the API sets `blueprint.source = None` (`interpreter.py:43`; `handle_pipe_errors.py:106,162` hard-code `source=None`) — cross-file diagnostics misfire on the API backend. Fix: add an **optional, additive per-item name** to the validate request (e.g. parallel `mthds_names` or `list[{name, content}]`, neutral/standard field names per the MTHDS brand boundary) and thread it into `blueprint.source` on the in-memory load path. Coordinate with the active MTHDS protocol-surface-alignment work. Spans pipelex Phase 1 + pipelex-api Phase 2 + mthds-js Phase 3.
- **API transport-failure policy.** On a server-unreachable / non-`problem+json` / unparseable error (not a 422 validation failure): show an actionable notification ("Pipelex API unreachable at {baseUrl} — is pipelex-api running?"), set **no diagnostics**, **clear** any stale diagnostics, and do **not** auto-fall back to CLI. Applies to any non-validation API error, including HTML proxy pages / auth JSON / timeouts.
- **Privacy confirmation timing.** Fire the non-localhost confirmation **before the first remote request**, and state that it sends the **whole directory's `.mthds` contents**, not just the active file.
- **Multi-file gathering = disk read (v1).** Read siblings from disk to match CLI `--library-dir` semantics; verify the directory gather matches CLI bundle resolution (nested dirs, configured libraries, symlinks, ignored files, ordering) or document the divergence. Buffer-awareness is a follow-up TODO.
- **Version-gate leniency (v1).** Parse `implementation_version` leniently — treat unparseable / prerelease / dev tags (`0.4.0-dev`, `latest`) as capable (warn-once, don't hard-block). Capability-probe redesign is a follow-up TODO.
- **mthds-js runtime checklist.** Beyond "rollup bundles it": verify `fetch`, `AbortController`, proxy settings, TLS/cert handling, ESM/CJS interop on the VS Code extension-host Node runtime. Confirm SecretStorage→env token **precedence** actually overrides any native env read in `mthds-js`. Consider a file/workspace pin for `mthds` during dev while the npm publish is pending.

## ▶ Resume point — current status (last updated 2026-06-16)

**Strategy pivot (supersedes "release 0.34.0 to unblock Phase 2"):** we are NOT releasing pipelex first. We fix the **entire cross-repo train against an unreleased pipelex commit pin**, prove it end-to-end, and **cut pipelex 0.34.0 LAST**. This avoids a premature release PR and version juggling — the pipelex worktree stays at `0.33.0`, so pipelex-api's `==0.33.0` constraint keeps matching the pin throughout.

**Pin mechanism ("both"):** pipelex-api pins pipelex with an **editable path** locally (`pipelex = { path = "../_calls", editable = true }` in `[tool.uv.sources]`) for a tight iteration loop, but the **committed** form must be the **git-rev SHA** (reproducible/CI). A comment block in `../pipelex-api/pyproject.toml` records the alternate line to restore. The pipelex-api Checkpoint-2 commit was made with the **git-rev form** at the pushed pipelex tip `0ab2cb8b` (so CI/build is reproducible); swap back to the editable line + re-`uv lock` for the next local iteration loop.

**DONE:**

- **Phase 1 (pipelex)** — committed + **pushed**, branch `feature/Tweaks-for-validation-api` (version still `0.33.0`). See Checkpoint 1 below.
- **Pipelex side of T3 (the enabling refactor)** — committed + **pushed**, tip **`0ab2cb8b`** (`refactor(validation): extract validate_bundles_in_process + thread mthds_names through temporal dry-validate`):
  - NEW `pipelex/pipeline/validate_in_process.py::validate_bundles_in_process(*, mthds_contents, mthds_names=None, library_dirs=None, allow_signatures=False, log_context="validate")` — extracted the in-process validate orchestration out of `PipelexMTHDSProtocol.validate` (protocol signature untouched, delegates). Also corrected the protocol-path comment: that path carries nameless content so `source` stays `None`; the CLI populates `source` via the separate `validate_bundle(mthds_file_path=…)` disk entry point.
  - `DryValidateArg.mthds_names` + `act_dry_validate` threads it to `validate_bundle`.
  - Deferred follow-up #9 (library-window teardown hand-mirrored across `validate_in_process` + `act_dry_validate`) captured in `wip/dry-run-refactor/followup-dry-validate-hardening.md` — unify when `ApiRunner.validate` lands as the third consumer (now landed; revisit).
- **Phase 2 / Checkpoint 2 (pipelex-api)** — **DONE + committed** on `feature/validation-errors-source`, commit **`2941daa`** (`feat(validate): structured validation_errors + optional mthds_names source threading`). Pinned pipelex git-rev `0ab2cb8b`, bumped **0.3.0 → 0.4.0**, `uv lock`+`uv sync --all-extras`, `make agent-check` + full `make agent-test` + `make openapi-check` GREEN against the git-rev install. See Checkpoint 2 below for as-built.
- **Spec (T4)** — `docs/specs/pipelex-mthds-protocol.md` Error-contract section updated (validation_errors + mthds_names), committed on the workspace-root specs repo `dev` branch (**`a8b6b4b`**). `make check-spec-links` GREEN. **T4 divergence (deliberate):** the eng-review Issue 2 asked for a *conformance* test, but the conformance suite is CLI-only and the HTTP arm is **deferred (D5, `wip/conformance-http-arm.md`)** — so the real-wire 422 + `source` is verified in **pipelex-api's own suite** (`tests/unit/test_validate_errors.py`), referenced by the spec's `<!-- unverified -->` marker (the established pattern for HTTP-arm verification). No conformance HTTP harness was built.
- **Phase 3 / Checkpoint 3 (mthds-js, T5)** — **DONE + committed** on `feature/typed-validation-report`, commit **`ad74bde`** (`feat(validate): typed PipelexValidationReport + structured validation errors`). `make check` (build + depcruise + full suite) GREEN. See Checkpoint 3 below for as-built. **Version stays 0.10.0** (NOT bumped to 0.11.0) and **npm publish deferred** to the release-LAST phase — consistent with pipelex staying at 0.33.0; the vscode extension pins mthds-js via a local file/workspace pin during dev.

**NEXT (resume here):** **Phase 4 — vscode-pipelex (T6–T11)** in `.` (the vscode-pipelex repo). Backend abstraction (`ValidationBackend` with `CliValidationBackend` single-spawn exit-code discriminator + `ApiValidationBackend` over `MthdsApiClient`), settings (`pipelex.backend`, `pipelex.api.baseUrl`, SecretStorage key commands), multi-file disk gather + per-item names, cross-file diagnostics via `source`, version gating (raise `MIN_AGENT_VERSION`→0.34.0 + lenient API parse), transport-failure policy, privacy confirm. Add `mthds` as a **local file/workspace pin** (publish is pending). The whole train still releases LAST (pipelex 0.34.0 → re-pin pipelex-api `==0.34.0` → publish mthds-js 0.11.0 → vscode).

## Repos, paths, and current versions

| Repo | Path | Version | Role in this plan |
| --- | --- | --- | --- |
| pipelex (worktree) | `../_calls` (branch `feature/Tweaks-for-validation-api`) | 0.33.0 | Expose `validation_errors` on the API error contract |
| pipelex-api | `../pipelex-api` (branch `feature/validation-errors-source`) | 0.3.0 | Re-pin pipelex (done, editable), surface the field, bump `implementation_version` |
| mthds-js | `../mthds-js` (branch `feature/typed-validation-report`) | 0.10.0 | Type the validation report + structured errors (DONE, commit `ad74bde`); 0.11.0 bump + publish deferred to release-LAST |
| vscode-pipelex | `.` (this repo) | — | Backend abstraction, settings, consume `mthds-js` |

> All `pipelex` edits land in the worktree `../_calls`, treated as repo root — not `../pipelex`.
>
> **Doc vantage point.** Paths in this doc are written from the **vscode-pipelex** repo's perspective (`.` = vscode-pipelex, `../_calls` = the pipelex worktree). This copy of the doc currently lives in `../_calls`, so read the relative paths with that offset in mind.
>
> **Current state (updated 2026-06-15 — see "▶ Resume point" above for the authoritative status).** Phase 1 is committed + pushed (`feature/Tweaks-for-validation-api`, tip `ec6e3a811`). The pipelex side of T3 (the `validate_bundles_in_process` extraction + temporal `mthds_names`) is implemented but uncommitted, live via the editable pin. `pipelex-api` (branch `feature/validation-errors-source`) has been **re-pointed off `0e32c8c02` to an editable pin on `../_calls`** (the committed form will be a git-rev SHA newer than `ec6e3a811`). No pipelex-api code changes yet.

## Architecture overview — the seam

The verified facts that shape the design:

- **GraphSpec is already identical** on both paths. The CLI `--view` output and the API `graph_spec` field are the same `GraphSpec` model (`../_calls/pipelex/graph/graphspec.py`), serialized `by_alias=True`, and the webview's `@pipelex/mthds-ui` renderer mirrors it exactly. The only difference is the envelope key (`graphspec` from the CLI vs `graph_spec` inside the API's validation report) and that direction/layout is already client-side (ELK in the webview). No GraphSpec body transformation is needed.
- **Validation errors regress today.** On an invalid bundle the API returns HTTP 422 RFC-7807 `problem+json` with a single `detail` string. The structured per-error list the extension maps to per-line diagnostics exists on the `ValidateBundleError` instance but is dropped at the exception→`ErrorReport` boundary. Phase 1 fixes this.
- **One call must serve both.** When validation and graph are both wanted for a file, a single backend call returns them together. The API already does this (`/v1/validate` → report + `graph_spec`). The CLI does not yet — Phase 1 also makes `validate bundle --view --format json` return a combined envelope (validation details + best-effort graph).

We introduce a single `ValidationBackend` abstraction in the extension with two implementations (CLI, API), selected by `pipelex.backend`. It exposes one `analyze(files, { withGraph })` method that returns both the validation outcome and (when requested) the graph, so the "no two calls" requirement is structural. Both backends produce the same normalized outcome types, keeping the diagnostics and graph webview code backend-agnostic.

---

## Phase 1 — pipelex (`../_calls`): structured `validation_errors` over the API + a single combined validate+view envelope

This phase has two parts: (A) get structured errors onto the API wire, and (B) make the CLI return validation details and the graph from one call.

### Part A — expose structured `validation_errors` over the API

**Problem.** `ErrorReport` (`../_calls/pipelex/base_exceptions.py`, ~lines 233-266) is `frozen` / `extra="forbid"` and `PipelexError.to_error_report()` (~lines 482-508) copies only a fixed flat field set, so the three per-error lists on `ValidateBundleError` never reach the wire. The CLI dodges this by catching the exception itself and calling `extract_validation_errors(exc)` (`../_calls/pipelex/cli/agent_cli/commands/agent_output.py`, ~lines 409-473), which reads `pipelex_bundle_blueprint_validation_errors`, `pipe_factory_errors`, and `pipe_validation_errors`.

**Changes.**

1. **Promote a typed wire item.** Define a `ValidationErrorItem` Pydantic model carrying the *true* union of fields across the three error-data models. Verified against the current extractor (`extract_validation_errors`, `../_calls/pipelex/cli/agent_cli/commands/agent_output.py:410`) and the models (`PipeFactoryErrorData`, `PipesAndConceptValidationErrorData`, `PipelexBundleBlueprintValidationErrorData`), the union is: `category`, `error_type`, `pipe_code`, `concept_code`, `domain_code`, `source`, `field_path`, `field_name`, `variable_names`, `missing_concept_code`, `declared_concepts`, `message`. Place it next to the source error-data models (`../_calls/pipelex/core/exceptions.py`, `../_calls/pipelex/core/bundles/exceptions.py`). Corrections vs the field list this plan originally proposed:

   - **Keep `missing_concept_code` and `declared_concepts`.** The current CLI extractor emits both for `pipe_factory` errors (`agent_output.py:451-454`). Because the shared typed builder (item 2 below) becomes canonical for *both* the CLI and the API, dropping them would silently regress today's CLI output.
   - **`field_name` is new, not "already emitted".** The extractor emits only `field_path` today; `field_name` exists on `PipesAndConceptValidationErrorData` but is never extracted. Adding it is fine, but `field_name` / `field_path` are a confusable pair — populate both intentionally.
   - **Add `source` (the declaring file path).** Present on `PipesAndConceptValidationErrorData` and `PipelexBundleBlueprintValidationErrorData` (absent on `PipeFactoryErrorData`), and not extracted today. Threading it onto `ValidationErrorItem` hands the extension the owning file for those two categories directly, substantially de-risking Phase 4's cross-file diagnostic mapping. Surface it whenever present.
2. **Extract a shared builder.** Move the `extract_validation_errors()` logic out of the CLI command module into a shared location (e.g. `../_calls/pipelex/pipeline/validation_errors.py`) and have it return `list[ValidationErrorItem]`. The CLI command and the new `to_error_report()` override both call it, so the CLI and API shapes can never drift.
3. **Add the field to `ErrorReport`.** Declare `validation_errors: list[ValidationErrorItem] | None = None` on `ErrorReport`. Because `to_problem_document()` (~lines 315-357) already projects non-omitted payload fields onto the envelope, the field appears on the 422 body automatically once populated.
4. **Override `ValidateBundleError.to_error_report()`** (`../_calls/pipelex/pipeline/exceptions.py`, ~lines 72-118) to call `super().to_error_report()` then attach `validation_errors` via the shared builder.
5. **STRICT disclosure.** Add `validation_errors` to `_STRICT_KEPT_FIELDS` (`../_calls/pipelex/base_exceptions.py:54`) so the structured list survives STRICT error disclosure (production hosted). **Rationale (corrected):** that set is the documented single-decision contract for both STRICT branches — adding a top-level `ErrorReport` field there surfaces it on both branches. (NOT "like `caller_facing_message`" — that field is kept by separate branch logic at `base_exceptions.py:40-49`, not by this set.) Decision: surface them, because they describe the user's own submitted bundle, not server internals; redacting would gut hosted-path diagnostics. The test must assert retention on **both** STRICT branches (caller-facing + redacted).

   **NEW (eng review, Issue 5 — API `source` fix):** thread an optional per-content name into `blueprint.source` on the in-memory (string) load path so the API populates `source` instead of `None` (`interpreter.py:43`, `handle_pipe_errors.py:106,162`). Keep the request field neutral/standard (MTHDS brand boundary). This makes cross-file diagnostics work on the API backend; the CLI path keeps real file paths.
6. **(Optional, same boundary)** `PipelexInterpreterError.validation_errors` is lost the same way. Apply the same override if cheap; otherwise note as a follow-up.

### Part B — single combined validate+view envelope (CLI) — ❌ DEFERRED (eng review 2026-06-15)

> **DEFERRED to Out of scope.** A single `validate bundle --view --format json --allow-signatures` spawn already serves both channels today: `bundle_cmd.py` validates first and runs the `if view:` block only on success, so valid → exit 0 + `graphspec`, invalid → non-zero exit + `validation_errors` (the path the extension already parses). So "one call returns both" is satisfied without a CLI contract change. Phase 4's `CliValidationBackend` reads the exit code as the valid/invalid discriminator — see the rewritten Phase 4 note. The text below is retained for context only; do NOT implement it.

**Problem.** Today the extension makes two CLI invocations when the graph is open: `validate bundle ...` for diagnostics (errors arrive on the exit-1 error path) and `validate bundle ... --view --format json` for the graph (success on exit 0). To satisfy "one call returns both", `validate bundle --view --format json` must return a single machine-readable envelope that carries both validation details and the best-effort graph, without throwing on an invalid bundle.

**Changes** (in `../_calls`, around the agent-CLI `validate bundle` command and `pipelex/graph/graph_rendering.py`'s `generate_view_for_bundle`):

7. In `--view --format json` mode, **do not raise on validation failure** — catch `ValidateBundleError` and emit a combined envelope on exit 0:
   - valid bundle → `{ "success": true, "validated_pipes": [...], "pending_signatures": [...], "is_runnable": true, "graphspec": {...}, "pipe_code": "...", "direction": "..." }`
   - invalid bundle → `{ "success": false, "validation_errors": [...], "graphspec": null }` (reusing the same shared `extract_validation_errors()` builder from Part A so the CLI's combined output and the API 422 stay identical).
   This mirrors the API: errors and graph never coexist (an invalid bundle has no graph), but a single call always returns whichever applies.
8. Leave the plain `validate bundle` path (no `--view`) untouched for the diagnostics-only / cheaper case — graph dry-run cost is only paid when `--view` is requested.

**Tests** (`../_calls/tests/...`):
- Part A: an invalid bundle's `ErrorReport` / problem document contains `validation_errors[]` with all fields populated; STRICT mode retains them; a parity test asserting the API-bound shape equals the CLI's `extract_validation_errors()` output.
- Part B: `validate bundle --view --format json` on a valid bundle returns `graphspec` + `validated_pipes` with exit 0; on an invalid bundle returns `success:false` + `validation_errors` + `graphspec:null` with exit 0 (no throw).

**Versioning & docs.** Bump pipelex 0.33.0 → 0.34.0 (new error-contract field + new combined `--view` output). Update CHANGELOG and the relevant `../_calls/docs/` pages (validate error envelope + the `--view --format json` output contract).

> **CHECKPOINT 1 — ✅ IMPLEMENTED (code + tests + docs), release pending.** The pipelex runtime now serializes structured `validation_errors` on `ValidateBundleError` problem documents (Part A). Part B was deferred (eng review), so the combined `--view` envelope is intentionally NOT built — the single `--view` spawn already serves both channels via exit code.
>
> **As-built (2026-06-15, branch `feature/Tweaks-for-validation-api`, uncommitted):**
>
> - `ValidationErrorItem` + `ValidationErrorCategory` live in `pipelex/base_exceptions.py` (next to `ErrorReport`, NOT in `core/exceptions.py` as the plan originally suggested — that would create a `base_exceptions ← core.exceptions` import cycle, since `ErrorReport` references the item as a typed field). The union fields match the plan: `category`, `message`, `error_type`, `pipe_code`, `concept_code`, `domain_code`, `source`, `field_path`, `field_name`, `variable_names`, `missing_concept_code`, `declared_concepts`.
> - Shared builder `build_validation_error_items` in `pipelex/pipeline/validation_errors.py`. **Signature note:** it takes the three categorized error *lists* (keyword-only) rather than a `ValidateBundleError` instance — a `TYPE_CHECKING` back-reference to `ValidateBundleError` tripped pyright's `reportImportCycles` (it counts type-only imports). Both `ValidateBundleError.to_error_report()` and the CLI's `extract_validation_errors` call it.
> - `ErrorReport.validation_errors: list[ValidationErrorItem] | None` added; `"validation_errors"` added to `_STRICT_KEPT_FIELDS` (surfaced on BOTH STRICT branches — caller's own bundle diagnostics).
> - `ValidateBundleError.to_error_report()` override attaches the list; CLI `extract_validation_errors` is now a thin dump-adapter over the shared builder (and now also surfaces the previously-dropped `source` / `concept_code` / `field_name`).
> - **Issue 5 / T1 source fix:** `make_pipelex_bundle_blueprint(mthds_name=...)` sets `blueprint.source` (and seeds `blueprint_dict["source"]` before validation so blueprint-validation errors carry it). `validate_bundle(mthds_names=...)` threads per-content names (length-mismatch → `ValidateBundleError`). The MTHDS protocol `validate` signature was deliberately NOT touched (cross-repo protocol change) — Phase 2's `ApiRunner.validate` will call `validate_bundle(mthds_names=...)` directly.
> - Tests: `tests/unit/pipelex/pipeline/test_validation_errors.py`, `test_validate_bundle_error_report.py`, additions to `test_error_report_disclosure_mode.py` (STRICT both branches), `tests/integration/pipelex/pipeline/test_validate_bundle_source_threading.py`. `make agent-check` + full `make agent-test` GREEN.
> - Docs: `docs/under-the-hood/error-model.md` (schema row + `validation_errors` subsection + File→Purpose). CHANGELOG entries under `[Unreleased]` (NOT bumped to 0.34.0 — versioning happens at release time).
>
> **Checkpoint 1 boundary — REVISED (strategy pivot, see "▶ Resume point").** We no longer cut the 0.34.0 release here. Phase 2 is unblocked by **pinning pipelex-api to the unreleased commit** (editable locally / git-rev SHA committed) instead of a release. The **pipelex 0.34.0 release is now the LAST step of the whole train** (after pipelex-api + mthds-js + vscode are all proven against the pin). When it's time: `/release` bumps `pyproject.toml`, finalizes `[Unreleased]` → `[0.34.0]`, opens PR to main; then re-point every consumer's pin from the git-rev SHA to `==0.34.0`. **Record the released version here once cut.**
>
> **Also done this session (T3 enabling refactor, uncommitted, live via editable pin):** `validate_bundles_in_process` extracted into `pipelex/pipeline/validate_in_process.py` (protocol `validate` signature untouched, delegates) + `DryValidateArg.mthds_names`. Full detail in "▶ Resume point". These pipelex commits must be pushed and the recorded pin SHA bumped past `ec6e3a811` before pipelex-api is committed with its git-rev form.

---

## Phase 2 — pipelex-api (`../pipelex-api`): surface the field, version, docs

The route `validate_mthds` (`api/routes/pipelex/validate.py`) lets `ValidateBundleError` propagate to the global handler, so once Phase 1 ships the field flows onto the 422 with no route change.

**Changes.**

1. **Re-pin pipelex** — ✅ DONE (editable path pin on `../_calls`; committed form will be a git-rev SHA newer than `ec6e3a811`). Branch `feature/validation-errors-source`, 253/253 tests green.
1b. **Validate request gains optional per-item names (Issue 5).** — ✅ DONE. `ValidateRequest` (in `api/routes/pipelex/validate.py`, not `schemas/models.py` — it subclasses the shared `MthdsContentsRequest`) gained optional parallel `mthds_names: list[str] | None` + a `model_validator(mode="after")` length-match guard → 422. `ApiRunner.validate` threads it into `blueprint.source` (direct + temporal). Additive → old callers (n8n, app) keep working. `pipelex-api.openapi.yaml` regenerated via `make openapi-export`.
2. **Contract docs.** Update `docs/openapi/pipelex-api.openapi.yaml` (error response schema gains `validation_errors`), `docs/error-responses.md`, and `docs/pipe-validate.md` with the structured-error shape and an example 422.
3. **Version surface.** Bump pipelex-api 0.3.0 → 0.4.0 so `GET /v1/version` reports an `implementation_version` the extension can gate on.
4. **Confirm 200-vs-422 boundary.** *Verified:* today the route raises 422 on any `ValidateBundleError` and never emits per-pipe `FAILURE` entries on a 200 — the response model supports them, the handler does not produce them. Document this as the actual contract. If the 200-FAILURE channel is wanted, scope it as an explicit behavior change here (out of scope as currently written); otherwise the extension's 200 `validated_pipes` FAILURE channel stays empty.

**Tests** (`../pipelex-api/tests/...`): `POST /v1/validate` with an invalid bundle returns 422 whose body contains `validation_errors[]`; `allow_signatures=true` still tolerates signature stubs.

**Conformance — DECIDED: add it (eng review Issue 2).** The `/v1/validate` error envelope is not covered by the `docs/specs/` ↔ `conformance/` pair today. Add a spec section + a verifying test for the structured-error contract (`validation_errors[]` incl. `source`), and run `make check-spec-links` in `conformance/`. The test must assert the **real wire response**, not just the hand-maintained `pipelex-api.openapi.yaml` — otherwise the Python model, the OpenAPI YAML, and the mthds-js types become three drifting contracts. Conformance is the single guard against cross-repo drift on this brand-new surface.

> **CHECKPOINT 2 — ✅ REACHED (code + tests + docs + spec), release pending.** The Pipelex API emits structured `validation_errors` on 422 and advertises `implementation_version = 0.4.0`.
>
> **As-built (2026-06-16, branch `feature/validation-errors-source`, commit `2941daa`):**
>
> - **T3 — `mthds_names` request field + threading.** `ValidateRequest` (`api/routes/pipelex/validate.py`) gains optional `mthds_names: list[str] | None` + a `model_validator(mode="after")` length-match guard (mismatch → 422 via the custom `RequestValidationError`→problem+json handler, *before* the runtime, which would treat a mismatch as a 500). `ApiRunner.validate` (`api/routes/pipelex/pipeline.py`) gains the `mthds_names` param (additive over the protocol signature, `@override` LSP-safe): the in-process branch now calls `validate_bundles_in_process(mthds_names=…)` directly (not `super().validate`, which can't carry names); the Temporal branch threads names through `DryValidateArg` **and** the `make_pipelex_bundle_blueprint(mthds_name=…)` parse loop. Route passes `request_data.mthds_names`.
> - **`validation_errors` rides automatically.** No route shaping — `ValidateBundleError.to_error_report()` (pinned pipelex) attaches the list; `to_problem_document()` projects it onto the 422 body. Default disclosure VERBOSE; retained under STRICT (`_STRICT_KEPT_FIELDS`).
> - **Version + pin.** `pyproject.toml` 0.3.0 → 0.4.0; pinned pipelex git-rev `0ab2cb8b` (committed form). `/version`'s `implementation_version` reads `importlib.metadata.version("pipelex-api")` → 0.4.0.
> - **Tests (real wire).** NEW `tests/unit/test_validate_errors.py::TestValidateErrors` — invalid bundle → 422 + `error_type=ValidateBundleError` + structured `validation_errors[]`; `mthds_names` → `validation_errors[].source` (blueprint-validation item) on the direct path AND `bundle_blueprint.source` on success; length mismatch → 422 request error; Temporal arm threads names through the dispatched `DryValidateArg` + onto `bundle_blueprint.source`. Added `INVALID_MAIN_PIPE_MTHDS` to `tests/unit/_constants.py`. Existing `test_validate_envelope.py` unchanged + green.
> - **Docs.** Regenerated `docs/openapi/pipelex-api.openapi.yaml` (auto-export — `mthds_names` field + updated 422 description + `version: 0.4.0`; `make openapi-check` clean). `docs/error-responses.md` (new "Structured validation errors" section + field + updated 422 example). `docs/pipe-validate.md` ("Naming submitted files" section + `mthds_names` field + structured-error example). `CHANGELOG.md` `[Unreleased]` entries (NOT a `[v0.4.0]` header — finalized at release time).
> - **Spec/conformance (T4).** `docs/specs/pipelex-mthds-protocol.md` Error-contract section documents `validation_errors[]` + `mthds_names`; `<!-- unverified -->` marker points at `pipelex-api/tests/unit/test_validate_errors.py` (real wire) — conformance HTTP arm stays deferred (D5). `make check-spec-links` GREEN. Committed on specs-repo `dev` (`a8b6b4b`).
>
> **Checkpoint 2 boundary — release deferred (strategy pivot).** No pipelex-api image is cut here. At release time: re-pin pipelex `==0.34.0` (once pipelex 0.34.0 is cut LAST), ship the image, bump `api_image_tag` in `pipelex-api-infra`. **Record the released image tag / version here once cut.**

---

## Phase 3 — mthds-js (`../mthds-js`): type the report and surface structured errors

`MthdsApiClient.validate()` currently returns an opaque `ValidationReport` and throws `ApiResponseError` on 422 with the body as raw text (`src/runners/api/client.ts`, ~lines 425-442; `src/runners/api/exceptions.ts`).

**Changes.**

1. **Typed report.** Add a `PipelexValidationReport` interface (Pipelex-API extension over the protocol's extension-open `ValidationReport`) with the fields the runner returns: `bundle_blueprint`, `pipe_io_contracts`, `graph_spec`, `validated_pipes`, `pending_signatures`, `is_runnable`, `success`, `message`. Keep neutral, standard-aligned field names (no `pipelex_` prefix on bundle/graph artifacts). Have `validate()` return this type.
2. **Typed error item.** Add a `ValidationErrorItem` type mirroring the Phase 1 wire shape and export it.
3. **Surface structured errors on 422.** In the error-construction path, when the problem+json body carries `validation_errors`, parse it into a typed `validationErrors?: ValidationErrorItem[]` property on `ApiResponseError`. Keep throw-on-422 semantics (an invalid bundle is still an `ApiResponseError`); the consumer catches and reads the typed field. Export the augmented error type.
4. **graph_spec typing.** Keep `graph_spec` as opaque transport (`unknown`) in mthds-js to avoid duplicating the canonical GraphSpec schema that `@pipelex/mthds-ui` already owns; the extension casts it to the renderer's type. (Note the choice; revisit only if a shared graph type is wanted.)
5. **Type `implementation_version` for gating.** *Verified:* `MthdsApiClient.version()` returns `VersionInfo`, which has typed `protocol_version` / `runner_version?` plus an open extension index signature — it has **no** typed `implementation_version`, even though `pipelex-api` populates one (`api/routes/version.py:43`). Add `implementation_version?: string` to `VersionInfo` (or a `PipelexVersionInfo` extension) so Phase 4 can gate on it without reading an untyped extension field. **Note (eng review F4):** this is cosmetic, not a gate — `install.ts:155` already reads `ver.implementation_version` via the index signature today, so it does not block Phase 4.
6. **Send per-item names on `validate()` (Issue 5).** Extend the `validate()` signature to carry the optional per-content name alongside each content string (matching the Phase 2 request shape), so the extension's API path gets a real `source`. Keep `allowSignatures` semantics. Confirm SecretStorage→`MTHDS_API_KEY` token **precedence** in the client constructor (the wrapper must be able to override a native env read).

**Tests** (`../mthds-js/...`): `validate()` returns the typed report on success; on 422 it throws `ApiResponseError` with a populated typed `validationErrors`; round-trips the Phase 2 example bodies.

**Versioning, docs, publish.** Bump 0.10.0 → 0.11.0; update `README.md` / `CLI.md` / `docs/architecture.md`; publish to npm so the extension can pin it.

> **CHECKPOINT 3 — ✅ REACHED (code + tests + docs), publish deferred.** `mthds-js` exposes a typed validation report and typed structured errors. The extension can now consume the API path with full diagnostics parity (against a local file/workspace pin).
>
> **As-built (2026-06-16, branch `feature/typed-validation-report`, commit `ad74bde`):**
>
> - **Typed report (item 1).** `MthdsApiClient.validate()` returns `PipelexValidationReport` (in `src/runners/api/models.ts` — the Pipelex-API extension home next to `DictPipeOutput`, NOT `protocol/models.ts` which stays slim). Fields mirror the canonical pipelex `PipelexValidationReport` + the route's wire extras: `bundle_blueprint`, `pipe_io_contracts`, `graph_spec`, `validated_pipes` (`ValidatedPipeEntry {pipe_ref, status: DryRunStatus}`), `pending_signatures`, `is_runnable`, `success`, `message`, optional `mthds_contents` echo. `bundle_blueprint`/`pipe_io_contracts` are `Record<string, unknown>` and `graph_spec` is `unknown` — opaque transport (item 4), schemas owned by the runtime + `@pipelex/mthds-ui`.
> - **Structured errors on 422 (items 2–3).** `ValidationErrorItem` (+ `ValidationErrorCategory`) mirrors the Phase 1 wire shape (union fields, `category`+`message` required). `parseErrorBody` (client.ts) now also extracts the problem envelope's **top-level** `validation_errors[]` (shallow `Array.isArray` guard) and `throwApiResponseError` threads it into the new `ApiResponseError.validationErrors?: ValidationErrorItem[]`. Throw-on-422 unchanged; `undefined` for non-validation errors. Generic across all endpoints (only the `ValidateBundleError` 422 populates it).
> - **Named contents (item 6 / Issue 5).** `validate(mthdsContents, allowSignatures = false, mthdsNames?)` sends `mthds_names` only when provided (omission keeps the exact old body). **Protocol `MTHDSProtocol.validate` signature deliberately NOT changed** — `mthds_names` is a Pipelex-API extension, not protocol surface (brand boundary); the widened impl (extra optional param + covariant `PipelexValidationReport` return) stays assignable to the `Runner` interface, so `PipelexRunner` is untouched. **Token precedence confirmed** (item 6 tail): constructor `options.apiToken ?? process.env.MTHDS_API_KEY` — an explicit token (vscode SecretStorage) overrides the env read. No code change needed; documented.
> - **`implementation_version` typed (item 5).** Added `implementation_version?: string` named optional to `VersionInfo` (`protocol/models.ts`); other extensions (`implementation`, `runtime_version`) still ride the index signature.
> - **Exports.** `PipelexValidationReport`, `ValidatedPipeEntry`, `DryRunStatus`, `ValidationErrorItem`, `ValidationErrorCategory` exported from the barrel (`src/index.ts`).
> - **Tests.** `tests/unit/client/client.test.ts` — typed report fields on 200, sends `mthds_names` parallel array, omits it when absent, structured `validation_errors[]` with threaded `source` on an invalid 422, `validationErrors` undefined on a plain (length-mismatch) 422, typed `implementation_version` on `version()`. Full `make check` GREEN (build + depcruise boundary intact + suite).
> - **Docs.** README API-method table row, `docs/architecture.md` (module map + new "Typed Pipelex-API extensions over the validate surface" section incl. token precedence), `CHANGELOG.md` `[Unreleased]` `### Added` (CLI.md needs no change — its `validate` commands forward to the pipelex CLI and don't expose `mthds_names`).
>
> **Checkpoint 3 boundary — release deferred (strategy pivot).** Version stays **0.10.0**; the 0.11.0 bump + `npm publish` is step 3 of the release-LAST phase. During Phase 4 dev, vscode pins `mthds` via a local file/workspace pin (eng-review note). **Record the published version here once cut.**

---

## Phase 4 — vscode-pipelex: backend abstraction, settings, mthds-js integration

**Dependency.** Add `mthds` (pinned to the Phase 3 version) to `editors/vscode/package.json`. **Verified:** the extension's *main* code is bundled by **rollup** (via `rollup-plugin-esbuild`); esbuild on its own only builds the webview bundle. Since `mthds` is imported by the backend code, verify it bundles cleanly under **rollup**, not esbuild. `mthds` is pure ESM (`"type": "module"`, `tsc`-only build, no internal bundler) — generally fine, but confirm the Node target, ESM interop, and that `fetch` is available on the VS Code Node runtime.

**Backend abstraction** (new module under `editors/vscode/src/pipelex/validation/`):

- Define a single-call `ValidationBackend` interface:
  - `analyze(files, { withGraph }): Promise<BundleAnalysis>` where `BundleAnalysis = { validation: { ok: true; report } | { ok: false; errors: ValidationErrorItem[] }; graph?: GraphSpec | null }`. `graph` is populated only when `withGraph` is true. This single method makes "no two calls" structural.
  - `getBackendVersion(): Promise<...>` for gating/warnings.
- `CliValidationBackend` — refactor the existing logic (`cliResolver.ts`, `processUtils.ts`, `extractJson`) behind this interface. **Single spawn per `analyze()` (Part B deferred):** `withGraph:false` → `validate bundle ... --allow-signatures` (diagnostics only, no graph cost). `withGraph:true` → one `validate bundle ... --allow-signatures --view --format json` spawn; **read the exit code as the discriminator** — exit 0 → parse `graphspec` (+ `validated_pipes`), non-zero → parse `validation_errors` from the structured error payload (the path the diagnostics-only flow already uses) and set `graph = null`. No double dry-run. Existing CLI diagnostics behavior stays identical.
- `ApiValidationBackend` — wraps `MthdsApiClient`. One `client.validate(contents, /* allowSignatures */ true)` call: on success map the typed report into `validation` and read `graph_spec` into `graph`; on 422 map caught `ApiResponseError.validationErrors` into `validation`. **Transport / non-validation failures (Issue 4):** any server-unreachable, non-`problem+json`, HTML-proxy, auth, timeout, or otherwise-unparseable response → show an actionable notification ("Pipelex API unreachable at {baseUrl} — is pipelex-api running?"), set **no diagnostics**, **clear** stale diagnostics, and do **not** auto-fall back to CLI. Client constructed with `baseUrl` from settings and `apiToken` from SecretStorage→env (confirm the wrapper's token precedence actually overrides any native env read).

**Dual-channel diagnostics.** The `{ ok:false; errors }` branch is fed by **two** sources that both map to diagnostics: the 422 `validation_errors` (hard failures) and any 200 `validated_pipes` entries with FAILURE status (per-pipe dry-run failures returned as data). The CLI combined envelope exposes the same two channels (`validation_errors` and `validated_pipes`). Normalize both into the `ValidationErrorItem[]` the diagnostics path already consumes.

**One-call orchestration.** The on-save handler is the single orchestration point: it sets `withGraph = (graph panel is open for this doc)`, makes one `analyze` call, routes the validation outcome to the Problems panel via the existing `toDiagnostic()` / `locateError()` path, and — when `withGraph` — hands the returned graph to the panel instead of letting the panel make its own call. A fresh panel open (or the manual graph command) makes its own `analyze(withGraph:true)` call. Net effect: save-with-panel-open is one call serving both.

**Wire the consumers** to go through the selected backend:

- `pipelexValidator.ts` (`onSave`) — replace the direct `spawnCli(...)` validate call with the `analyze(...)` orchestration above.
- `graph/methodGraphPanel.ts` — replace the `validate bundle --view` spawn with `backend.analyze(..., { withGraph:true })` and read `analysis.graph`. The canonical GraphSpec reaches the webview unchanged regardless of backend; direction stays a client-side `pipelex.graph.direction` concern.

**Settings** (`contributes.configuration` in `editors/vscode/package.json`):

- `pipelex.backend`: enum `["cli", "api"]`, default `"cli"` (preserve current zero-config behavior; `api` is opt-in).
- `pipelex.api.baseUrl`: string, default `"http://localhost:8081"`.
- **API key handling (best practice):** no plaintext key setting. The `ApiValidationBackend` resolves the token as SecretStorage → `MTHDS_API_KEY` env (which `mthds-js` reads natively). Add a command `Pipelex: Set Hosted API Key` that writes to `vscode.ExtensionContext.secrets`, and `Pipelex: Clear Hosted API Key`.

**Multi-file gathering.** For a saved `.mthds` file, read every `*.mthds` in `path.dirname(file)` **from disk** (v1 — matches CLI `--library-dir`; buffer-awareness is a follow-up, see Out of scope) and build the contents array, mirroring `--library-dir <dir>`. **Verify the gather matches CLI bundle resolution** (nested dirs, configured libraries, symlinks, ignored files, deterministic ordering) or document the divergence. Keep a content-index → file-URI map for diagnostic placement. **For the API backend, also send the per-item name** (Issue 5) so the API can populate `source` — without it the API returns `source=None` and cross-file placement fails.

**Cross-file diagnostics.** Validation errors may reference pipes/concepts declared in sibling files. **Prefer the `source` field** (the declaring file path) added to `ValidationErrorItem` in Phase 1 — it is populated for pipe/concept-validation and blueprint-validation errors and gives the owning file directly. Fall back to mapping via `domain_code` / `pipe_code` → declaring file only for categories that lack `source` (e.g. `pipe_factory` errors). Set diagnostics on the owning file's URI using `sourceLocator.locateError()` against its text; errors that don't resolve fall back to the saved file or the output channel. This is the subtlest part of the API path — design it explicitly and cover it with tests.

**Version gating (both backends).**
- CLI: raise `MIN_AGENT_VERSION` (currently 0.31.0) to the Phase 1 version (0.34.0) that delivers the new `source`/`field_name` error fields, using the repo's `bump-pipelex-version` skill so all version-floor references stay in sync. **This is a compatibility-floor break** — older CLIs get a "too old" message; "CLI unchanged" refers to behavior, not the version requirement. State it explicitly in the changelog.
- API: add a `MIN_API_IMPLEMENTATION_VERSION` constant (the Phase 2 version). On first API use, call `client.version()` and read `implementation_version` (typed in Phase 3 item 5; `pipelex-api` populates it at `version.py:43`), cache it, and if too old show an upgrade message — analogous to `agentCliVersion.ts`. **Parse leniently:** treat unparseable / prerelease / dev tags (`0.4.0-dev`, `latest`, git pins) as capable (warn-once, don't hard-block). Capability-probe is a follow-up (Out of scope).

**Privacy.** The API backend sends file contents to `baseUrl` on every save. The localhost default keeps this local. Show the one-time confirmation **before the first remote request** (not lazily after a send has already happened), and state clearly that it sends the **whole directory's `.mthds` contents**, not just the active file.

> **CHECKPOINT 4.** The extension validates and renders graphs through either backend, selected by `pipelex.backend`, with full diagnostics parity on the API path. CLI remains the default and unchanged.

---

## Phase 5 — vscode-pipelex: tests, docs, QA, release

- **Tests (vitest):** `ApiValidationBackend` against a mocked `MthdsApiClient` (success report, 422 with `validationErrors`, transport error); multi-file gathering; cross-file diagnostic mapping; version gating; settings/secret resolution. Preserve all existing CLI-path tests.
- **Docs:** add a backend page under `editors/vscode` docs (or this repo's `docs/`) covering CLI vs API, settings, key handling, and self-hosting `pipelex-api`; update CHANGELOG and README. Update `CLAUDE.md` if the backend seam introduces a new concept worth recording.
- **Quality gate:** `make check` (fmt, plxt fmt, clippy `-D warnings`, crate tests, vitest, WASM check).
- **Manual QA:** both backends against valid/invalid bundles, multi-file directories, graph rendering, and a hosted endpoint with a key in SecretStorage.

---

## Cross-repo release ordering

**Strategy pivot (2026-06-15):** *build* against an unreleased pipelex commit pin, *release* in dependency order at the end. Concretely:

- **Build/iterate phase (now):** pipelex-api → mthds-js → vscode are all developed against the pinned (editable / git-rev SHA) unreleased pipelex `0.33.0`. Prove the full path before any release.
- **Release phase (last):** once the train is proven, ship in dependency order, re-pointing each consumer's pin from the git-rev SHA to the released version:
  1. **pipelex (`../_calls`)** — `/release` the `validation_errors` field as **0.34.0** (Checkpoint 1).
  2. **pipelex-api** — re-pin pipelex `==0.34.0`, release image + bumped `implementation_version` (Checkpoint 2).
  3. **mthds-js** — typed report + errors, publish to npm (Checkpoint 3).
  4. **vscode-pipelex** — pin the published `mthds`, gate the API backend on the min pipelex-api version, release the extension (Checkpoints 4–5).

The graph-only API path could technically ship before 1–3 (GraphSpec already matches), but validation diagnostics would regress, so prefer shipping the whole feature together.

## Risks & open questions

> **Eng review 2026-06-15 resolved several of these** — see "Decisions locked in eng review" above and the GSTACK REVIEW REPORT at the end. Newly resolved: API `source=None` (now fixed via per-item names, Issue 5), conformance coverage (added, Issue 2), `MIN_AGENT_VERSION` (→ 0.34.0), transport-failure policy, STRICT disclosure. New follow-ups captured in Out of scope.

Decided (no longer open): default backend = `cli`; per-pipe FAILURE *may* be returned as data on a 200 and the extension surfaces it **if present** (verified: not produced today — see the locked decision and Phase 2 item 4); cross-file error→file mapping is the accepted main complexity of the directory-wide approach (eased by the `source` field — see Phase 1 item 1 and Phase 4).

Remaining to verify during implementation:

- **Cross-file diagnostics** — the error→file mapping (error references a pipe/concept declared in a sibling file) is the trickiest piece; needs explicit design and tests in Phase 4.
- **`client.version()` shape** — *resolved:* `mthds-js` `VersionInfo` has no typed `implementation_version` (only `protocol_version` / `runner_version?` + an open index signature), though `pipelex-api` returns it (`version.py:43`). Phase 3 item 5 adds the typed field; until then it is only reachable via the untyped extension signature.
- **Bundler for `mthds`** into the extension — *resolved:* the main extension bundles via **rollup** (esbuild only builds the webview). Verify the ESM `mthds` import bundles cleanly under rollup early in Phase 4.
- **Conformance coverage** of the validate error envelope — *resolved:* not covered today; decide whether to *add* a spec section + test for the new `validation_errors` contract (not just "sync if covered").
- **Secret UX** — final shape of the SecretStorage commands and env fallback.

## Out of scope (possible follow-ups)

- Pipeline **execution** via the API (`/v1/execute`, `/v1/start`, durable run lifecycle).
- The build endpoints (`/v1/build/inputs|output|runner`, concept/pipe-spec) — separate features the extension doesn't use today.
- Surfacing the richer report fields the API returns but the CLI on-save path ignores (`pipe_io_contracts`, `bundle_blueprint`, `pending_signatures`, `is_runnable`).
- **Part B — combined exit-0 CLI validate+view envelope** (eng review 2026-06-15). Not needed: the single `--view` spawn already serves both channels via exit code. Revisit only if a cleaner exit-0 contract is wanted later (no functional gain).
- **The 200-`validated_pipes`-FAILURE channel** (deliberate behavior change in pipelex / pipelex-api). When/if built, **split the diagnostic type** — a per-pipe dry-run FAILURE is pipe-level, not line-level, and must not be forced into `ValidationErrorItem` (which would fabricate code locations). (eng review TODO 2)
- **Buffer-aware sibling gathering** — v1 reads siblings from disk (CLI parity). Follow-up: read unsaved editor buffers for fresher cross-file diagnostics, deliberately and with tests, on both backends. (eng review TODO 1)
- **Capability probe for API gating** — replace the coarse `implementation_version` SemVer gate with a "does this server return `validation_errors`?" probe, robust for self-hosted/dev/prerelease servers. v1 ships the lenient version gate. (eng review TODO 3)
- **`mthds_names` is an `MthdsApiClient`-only param, not on the `MTHDSProtocol`/`Runner` interface** (code-review finding, Phase 3 / `ad74bde`). **Deliberate** — `mthds_names` is a Pipelex-API extension, not protocol surface (MTHDS brand boundary), and Phase 4's `ApiValidationBackend` holds the concrete `MthdsApiClient` so it can pass names directly. Tradeoff: the cross-file-diagnostics capability is unreachable through a `Runner`-typed reference (a caller wiring names via the interface would need an `instanceof MthdsApiClient` downcast). Revisit IF/when the protocol surface formally adopts per-content names (coordinate with [[project_protocol_surface_alignment]]) — then promote it to `MTHDSProtocol.validate` as an optional 3rd arg (no-op on `PipelexRunner`). Do NOT reflexively add it to the interface now just to avoid the downcast; the brand boundary is the stronger constraint.
- **`PipelexValidationReport.mthds_contents` typed optional but always present on the pipelex-api wire** (code-review finding). Minor under-promise (safe). The shallow `Array.isArray` cast on `validation_errors` + `JSON.parse as` on 200 bodies manufacture type guarantees the wire doesn't runtime-enforce — consistent with the client's pervasive `as`-cast style and the real server always sends well-formed data; harden to per-item validation only if a non-pipelex MTHDS runner ever feeds this client. The lone-named `VersionInfo.implementation_version` (vs `implementation`/`runtime_version` on the index signature) is a deliberate plan-scoped choice; type the cluster together if a second extension field ever needs gating.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | outside-voice surfaced the API `source=None` blocker + hardening points |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 5 issues + 3 TODOs, all resolved; 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | n/a (editor diagnostics, no visual UI) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | not run |

**CODEX:** ran (read-only, high effort). Confirmed D1/Q1, then found the load-bearing miss: the API request is nameless `mthds_contents: list[str]`, so `source=None` and cross-file diagnostics misfire on the API backend. Verified in code; resolved as Issue 5 (Option A: per-item names). Also folded: "one call" wording, transport stale-clear, privacy timing/directory-wide, non-`problem+json` handling, conformance-asserts-real-wire, mthds-js runtime checklist, compat-floor explicitness.

**CROSS-MODEL:** One tension — my Issue 3 ("both backends use `source`") was infeasible as stated until Issue 5 fixed the API `source`. Resolved in the user's favor by adding per-item names. No remaining disagreement.

**Scope decision (Step 0):** SCOPE_REDUCED then re-expanded for correctness — Part B deferred (D1), but Issue 5 added the API `source` contract change back because it is load-bearing for the headline goal. Net: leaner CLI surface, fuller API surface.

**What already exists (reused, not rebuilt):**

- GraphSpec is identical on both paths (`graphspec.py`, `by_alias=True`) — no body transform.
- The extension's diagnostics pipe (`toDiagnostic`/`locateError`/`sourceLocator`/`extractJson`) and existing `ValidationErrorItem` shape — the API path feeds it, not a parallel one.
- `extract_validation_errors()` (`agent_output.py:410`) — promoted to a shared builder, not rewritten.
- The single `--view` spawn already serves both channels (exit-code discriminator) — no new CLI contract needed.
- `graph_spec: unknown` opaque-transport pattern already established in `mthds-js` (`runs.ts`).

**Failure modes (new codepaths):**

| Failure | Test? | Error handling? | User sees? |
|---|---|---|---|
| API server unreachable | yes (T7/T11) | yes (Issue 4: notify, clear, no fallback) | clear actionable notification — not silent |
| API returns non-`problem+json` (proxy/auth/timeout) | yes (T7) | yes (same policy) | notification, no garbage diagnostics |
| Multi-file error, `source` unresolved | yes (T11) | yes (fallback to saved file/output channel) | diagnostic on saved file or channel, never lost |
| STRICT redacts validation_errors (hosted) | yes (T11, both branches) | n/a | full diagnostics retained |
| Old CLI (<0.34.0) selected | yes (T8) | yes (upgrade message) | clear "too old" message |
| Dev/prerelease API tag false-fails gate | folded (lenient parse) | yes | warn-once, not hard-blocked |

No critical gaps (no failure that is untested AND unhandled AND silent).

**Worktree parallelization:** Largely SEQUENTIAL — the cross-repo release train is a hard dependency chain (pipelex → pipelex-api → mthds-js → vscode). Only meaningful parallelism: the extension's CLI-backend refactor (T6) can be built against pipelex 0.34.0 in parallel with the pipelex-api (T3/T4) and mthds-js (T5) releases, since it does not need the API path. All other extension work (T7–T10) shares `editors/vscode/src/pipelex/validation/` and is sequential.

**Implementation Tasks** (also in `tasks-eng-review-*.jsonl` for /autoplan):

- [x] **T1 (P1)** pipelex — thread per-item name into `blueprint.source` on the in-memory load path (Issue 5) — DONE (`make_pipelex_bundle_blueprint(mthds_name=)` + `validate_bundle(mthds_names=)`)
- [x] **T2 (P1)** pipelex — Part A: ValidationErrorItem + shared builder + ErrorReport field + ValidateBundleError override + `_STRICT_KEPT_FIELDS` (Issues 1) — DONE
- [x] **T2b (P1)** pipelex — T3 enabling refactor (this session, uncommitted/editable-live): extract `validate_bundles_in_process` (protocol `validate` signature untouched) + `DryValidateArg.mthds_names`; tests reconciled; `make agent-check` GREEN — DONE
- [x] **T3 (P1)** pipelex-api — optional `mthds_names` on ValidateRequest (+ length validator → 422), threaded through `ApiRunner.validate` (direct→`validate_bundles_in_process`, temporal→`DryValidateArg`+blueprint loop) + route (Issue 5) — DONE (commit `2941daa`)
- [x] **T4 (P2)** pipelex-api — spec Error-contract section documents `validation_errors`+`mthds_names`; real-wire verified in `pipelex-api/tests/unit/test_validate_errors.py` (Issue 2). **Divergence:** conformance HTTP arm stays deferred (D5) — verified in pipelex-api's own suite + spec `<!-- unverified -->` marker, NOT a new conformance test. `check-spec-links` GREEN. DONE (spec commit `a8b6b4b`)
- [x] **T5 (P1)** mthds-js — typed report + `ApiResponseError.validationErrors` + named contents on `validate()` (Issue 5) — DONE (branch `feature/typed-validation-report`, commit `ad74bde`; version stays 0.10.0, publish deferred to release-LAST)
- [ ] **T6 (P1)** vscode — `CliValidationBackend` single-spawn exit-code discriminator (D1/Q1)
- [ ] **T7 (P1)** vscode — `ApiValidationBackend` transport/non-problem+json policy: notify, clear stale, no fallback (Issue 4)
- [ ] **T8 (P2)** vscode — raise `MIN_AGENT_VERSION`→0.34.0 (compat-floor break) + lenient API version parse (Issue 3)
- [ ] **T9 (P2)** vscode — privacy confirm before first remote request, directory-wide wording
- [ ] **T10 (P2)** vscode — multi-file disk gather + CLI-resolution parity verify + send per-item names (TODO 1)
- [ ] **T11 (P1)** cross-repo — tests: STRICT both-branches, CLI==API parity, transport, cross-file mapping, conformance

**VERDICT:** ENG CLEARED — ready to implement. CEO + Design reviews not required (backend/editor-diagnostics change, no product-direction or visual-UI scope).

NO UNRESOLVED DECISIONS
