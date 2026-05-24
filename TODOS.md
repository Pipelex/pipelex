# TODOS — `feature/API-readiness-2`

Follow-up work for the next branch after PR #931 (error-handling overhaul). This plan finalizes the loose ends a `/review` pass on #931 surfaced: a documentation clean slate first, then the deferred Critical #2, the half-wired plan Item B, and the tracked follow-ups.

**Docs come first on purpose.** We work and review step by step. Every time a doc contradicts the code or another doc, the PR review agents (Greptile, Codex, Cubic) get confused and burn the review on noise. Phase 0 makes the error-handling doc set a single coherent description of what shipped and what is still wanted — so every later phase is reviewed against a correct spec.

Each phase is self-contained; checkpoints between them are hard stops where the agent must verify, record state, and make this doc cold-start-safe.

## Branch setup

- Cut `feature/API-readiness-2` from `dev` **after PR #931 has merged**. Every phase below builds on #931's code — the `ErrorReport` BaseModel, `DisclosureMode`, `recover_error_report`, the error-page generator. If you must start before #931 merges, branch from `feature/API-readiness-merge` instead.
- The `/review` pass on #931 left uncommitted doc-alignment edits on `feature/API-readiness-merge` (`pipelex/errors/error_pages_generator.py`, `pipelex/temporal/exceptions.py`, `docs/under-the-hood/error-model.md`, `wip/error-handling/api-companion-revisions.md`, and the new `wip/error-handling/track-strict-disclosure-input-domain-gap.md`). Those should land with #931. Phase 0 below is written to be idempotent — it re-applies anything that did not land, so it does not matter whether those edits made it into #931 or not.

## How to start (cold start)

1. Read this whole file, then read the linked tracker docs under `wip/error-handling/` and `wip/security/`.
2. Check the **Session log** at the bottom — it records what the last session landed and the exact next action.
3. Resume at the first unchecked box. Respect the checkpoints — do not run past a `⛔ CHECKPOINT` without doing its stop-and-record steps.

## Ground rules

- No backward-compat shims. The Temporal integration has never shipped — there is no prior on-wire schema to preserve.
- `request_id` is transported on `JobMetadata`. **Do not introduce a `ContextVar`** for it — a ContextVar is process-local and does not cross the Temporal activity/workflow serialization boundary in distributed execution. (The CLI-delivery track uses a ContextVar legitimately because it is single-process — do not conflate the two.)
- After any code change run `make agent-check`. Use `make agent-test` to verify a phase before its checkpoint.
- Spec vs Blueprint: language rules go on blueprints, authoring convenience on specs (see `pipelex/builder/CLAUDE.md`).

---

## Phase 0 — Documentation coherence pass (clean slate)

No code-behavior changes in this phase — docs and docstrings only. Goal: every error-handling doc and docstring describes either shipped code (accurately) or wanted work (clearly, marked as wanted-not-done). No doc contradicts the code; no two docs contradict each other.

### 0.1 — Reference docs and docstrings must match shipped code

- [x] `docs/under-the-hood/error-model.md` — verify the `extra="forbid"` warning no longer claims `recover_error_report()` trims unknown keys. Then read the whole file against the shipped `ErrorReport` / `recover_error_report` / disclosure-mode code and fix any other drift.
- [x] `pipelex/temporal/exceptions.py` — verify the `UnrecoverableWorkflowFailureError` docstring no longer claims it is synthesized on a `from_dict` version-skew failure. It is synthesized only when no report dict is found at all.
- [x] `pipelex/temporal/log_temporal.py` — the `WorkflowLog` / `ActivityLog` docstrings claim "activities/workflows read the value off `job_metadata.request_id` and pass it explicitly." No caller does that yet. Soften the docstrings to describe the parameter honestly (accepted; wiring tracked in Phase 2) so a review agent does not flag a false claim.
- [x] Sweep docstrings in the #931-touched modules for code-doc drift and fix what no longer matches: `base_exceptions.py` (`ErrorReport`, `DisclosureMode`, `to_dict`, `to_problem_document`, `title`, `type_uri`), `temporal_error.py` (`recover_error_report`, `_message_from_exc`, `_find_error_report_dict`), `delivery_executor.py`, `error_pages_generator.py`, `error_module_registry.py`.

### 0.2 — Plan doc `api-companion-revisions.md` coherence

- [x] Verify §D.1 and "What landed in Stage 2" describe `recover_error_report` correctly (no embedded report → synthesize; found-but-invalid dict → raise as an internal contract bug) and that the `_declared_title` value quoted matches the code.
- [x] Rewrite §B — it says "Activity logs carry it via a `ContextVar` (same pattern as `session_id`)." That is wrong. State the decided design: `request_id` is transported on `JobMetadata` and threaded explicitly into log calls; no `ContextVar`, because a ContextVar is process-local and does not survive the Temporal serialization boundary.
- [x] Reconcile the "Current state" Stage checklist with reality: Stages 1-4 landed, Stage 5 (webhook signing) pending. Add a pointer to this `TODOS.md` for the post-review follow-ups so a reader knows where the remaining work lives.
- [x] Make every "What landed in Stage X" section honest — in particular Stage 1's `request_id` claim must not imply the logging is wired end-to-end when it is not.

### 0.3 — The `wip/error-handling/` hub

- [x] `wip/error-handling/README.md` — the "Status at a glance" table does not list the API-readiness / `api-companion-revisions.md` track at all, and "What's still open" mentions only the metadata-model long tail. Add the API-readiness track to the table, and rewrite "What's still open" to list the real open items — webhook signing (Stage 5), the STRICT disclosure gap, the webhook-payload collision, the `request_id` wiring, the metadata-model long tail — each linking its tracker doc and/or this `TODOS.md`.
- [x] Confirm the new trackers (`track-strict-disclosure-input-domain-gap.md`, `track-webhook-payload-collision.md`) are linked from the README and consistent with it.
- [x] Confirm every `archive-*.md` file reads unambiguously as an archive (point-in-time, superseded). Do NOT rewrite archive contents — only fix a header line if one genuinely reads as a current contract.
- [x] `changes-for-api-early-draft.md` — add a one-line "superseded — see `api-companion-revisions.md`" banner at the top if it does not already have one, so a review agent never treats the original draft spec as the contract.

### 0.4 — Cross-doc coherence check

- [x] Final read: `TODOS.md` ↔ `api-companion-revisions.md` "Current state" ↔ `wip/error-handling/README.md` "What's still open" must agree on what is done and what is pending. Resolve any disagreement.
- [x] `make agent-check` clean (docstring edits can trip formatting/linting).

**Acceptance:** a PR review agent reading the error-handling docs cold gets one coherent story — no doc contradicts the code, no two docs contradict each other, and pending work is clearly marked as pending.

### ⛔ CHECKPOINT 0 — Clean slate verified, STOP and record

- [x] Run `make agent-check` — must pass.
- [x] Commit Phase 0 as a single docs-only commit.
- [x] Tick every Phase 0 box above.
- [x] Append a dated **Checkpoint 0** entry to the Session log: confirm the doc set is coherent, list any doc deliberately left as-is and why, and the next action (start Phase 1).

---

## Phase 1 — STRICT disclosure: close the INPUT-domain leak (Critical #2)

Full analysis and options: [`wip/error-handling/track-strict-disclosure-input-domain-gap.md`](wip/error-handling/track-strict-disclosure-input-domain-gap.md).

STRICT disclosure mode keys its redaction passthrough on `error_domain == ErrorDomain.INPUT`, but `error_domain` is inherited up the `__cause__` chain by `_enrich_error_report_from_cause`. Two consequences: a domain-less wrapper raised `from` an INPUT cause leaks its own internal `message` through STRICT; and `to_problem_document` echoes `provider` / `model` / `provider_metadata` for INPUT reports even in STRICT.

- [x] **Decision D1** — pick the Gap 1 fix: Option 1 (per-class `ClassVar` flagging classes that genuinely author caller-facing messages; gate STRICT passthrough on the flag) or Option 2 (stop inheriting `error_domain` onto a domain-less wrapper). Recommended: **Option 1** — it gates redaction on message provenance rather than an inherited classification, and avoids the `http_status` side effects Option 2 carries. Record the choice in the Decisions section. **→ Decided 2026-05-22: Option 1** (see [Decisions](#decisions)).
- [x] Implement the chosen Gap 1 fix in `pipelex/base_exceptions.py` (`to_dict` STRICT branch, and `_enrich_error_report_from_cause` / the report-construction path as the option requires).
- [x] Gap 2 — strip `provider` / `model` / `provider_metadata` from the INPUT passthrough branch of `to_dict(DisclosureMode.STRICT)`. An input-classification error has no business carrying provider metadata onto an external surface.
- [x] Align the `DisclosureMode` docstring in `pipelex/base_exceptions.py` with the implemented redaction set.
- [x] Tests: a domain-less wrapper (`PipelexUnexpectedError`) raised `from` an INPUT-domain cause must not leak the wrapper's `message` through `to_dict(STRICT)`; `to_problem_document(disclosure_mode=STRICT)` must never emit `provider` / `model` / `provider_metadata` regardless of `error_domain`. Mirror the existing STRICT tests in `tests/unit/pipelex/test_error_report_disclosure_mode.py`.
- [x] `make agent-check` clean; STRICT-related tests green.
- [x] Update [`wip/error-handling/track-strict-disclosure-input-domain-gap.md`](wip/error-handling/track-strict-disclosure-input-domain-gap.md) — mark it landed, note the option taken.

**Acceptance:** STRICT never reflects a non-caller-facing message or provider metadata to an external surface, for any `error_domain`. The `DisclosureMode` docstring matches the code.

### ⛔ CHECKPOINT 1 — STOP, verify, record

- [x] Run `make agent-check` and `make agent-test` — both must pass.
- [x] Commit Phase 1 as a single coherent commit.
- [x] Tick every Phase 1 box above.
- [x] Append a dated **Checkpoint 1** entry to the Session log with: Decision D1 outcome, files touched, the exact redaction behavior now in effect, anything deferred, and the next action (start Phase 2).

---

## Phase 2 — Finish wiring `request_id` into Temporal logs (Plan Item B)

Plan Item B is half-landed. `JobMetadata.request_id`, the `pipeline_run_setup(request_id=...)` kwarg, and the `request_id` kwarg on every `WorkflowLog` / `ActivityLog` method plus `_build_extra` all shipped — but **no pipelex activity or workflow reads `job_metadata.request_id` and passes it to a log call.** The kwarg is dead surface today.

- [x] **Decision D2** — pick the call-site strategy. Either pass the `request_id` kwarg at each meaningful Temporal log call, or build a per-invocation bound logger/adapter from `job_metadata.request_id` at activity/workflow entry. Recommended: **the bound-adapter approach**, rebuilt every invocation, to avoid threading the kwarg through every call site. It must NOT be a ContextVar and must NOT be module/process state — it is rebuilt per activity/workflow invocation from that invocation's `JobMetadata`. Record the choice. **→ Decided 2026-05-22: bound adapter** (see [Decisions](#decisions)).
- [x] Wire it: at each activity and workflow entry point that has `job_metadata` in scope, read `job_metadata.request_id` and make that invocation's log records carry it via the `_build_extra` → `extra={"request_id": ...}` path.
- [x] Remove dead surface: if the bound-adapter approach wins, drop the now-unused per-method `request_id` kwargs, or fold them into the adapter — leave no unused parameter and no inaccurate docstring behind.
- [x] Test: a pipeline run dispatched with a `request_id` produces Temporal activity/workflow log records carrying that `request_id`. Add coverage of the `_build_extra` / logging request_id path — there is none today.
- [x] Update the docs to reflect Item B fully landed — `api-companion-revisions.md` "What landed" / "Current state", `wip/error-handling/README.md`, and the `log_temporal.py` docstrings (which can now state the wiring as fact).
- [x] `make agent-check` clean.

**Acceptance:** a run dispatched with a `request_id` has that id on its Temporal log records; no dead `request_id` parameter or inaccurate docstring remains.

### ⛔ CHECKPOINT 2 — STOP, verify, record

- [x] Run `make agent-check` and `make agent-test` — both must pass.
- [x] Commit Phase 2 as a single coherent commit.
- [x] Tick every Phase 2 box above.
- [x] Append a dated **Checkpoint 2** entry to the Session log with: Decision D2 outcome, the wiring mechanism chosen, files touched, whether the per-method kwargs were kept or dropped, and the next action (start Phase 3).

---

## Phase 3 — Webhook payload reserved-key collision

Full analysis and options: [`wip/error-handling/track-webhook-payload-collision.md`](wip/error-handling/track-webhook-payload-collision.md).

`DeliveryExecutor._notify_webhook` copies the caller's `WebhookTarget.payload` and writes Pipelex-owned keys (`pipeline_run_id`, `status`, `result_url`, `error`) on top. A caller can put any of those keys in their static payload and have the meaning shift silently with delivery status.

- [x] Implement Option 1 from the tracker: a `field_validator` on `WebhookTarget.payload` in `pipelex/pipe_run/delivery_assignment.py` that rejects the reserved-key set at construction time, with a clear error naming the offending key(s).
- [x] Tests: constructing a `WebhookTarget` with a reserved key in `payload` raises a validation error; a clean payload passes.
- [x] `make agent-check` clean.
- [x] Update [`wip/error-handling/track-webhook-payload-collision.md`](wip/error-handling/track-webhook-payload-collision.md) — mark it landed.

**Acceptance:** a caller cannot register a webhook whose static payload collides with a Pipelex-owned key; the failure is loud and at construction time.

---

## Phase 4 — Test coverage backfill

The `/review` pass found gaps where the refactor removed or never added coverage. Some depend on Phase 2 — do this phase after Phase 2.

- [x] `recover_error_report` — `tests/integration/pipelex/temporal/test_recover_error_report.py` lost the cases that pinned the old "malformed → None" behavior. Add a case pinning the current contract: a report dict that is *found* but fails `ErrorReport` validation raises `pydantic.ValidationError` (treated as an internal contract bug, not synthesized).
- [x] `_message_from_exc` (`pipelex/temporal/tprl/temporal_error.py`) — add a test for the `id()`-based cycle guard (a self-referential `__cause__` chain must terminate) and a test for the `repr(exc)` fallback when every message in the chain is empty.
- [x] `DeliveryActivityArg` — add a focused unit round-trip test (`model_validate_json(model_dump_json())`) with a populated nested `error_report`, so a nested-model serialization regression is caught without a real Temporal worker.
- [x] Logging `request_id` path — covered by Phase 2's test; confirm it exists and is green here.
- [x] `make agent-check` and `make agent-test` clean.

**Acceptance:** the behaviors the refactor introduced or changed are pinned by tests; no silent regression path remains for `recover_error_report`, `_message_from_exc`, or the activity-arg round-trip.

### ⛔ CHECKPOINT 3 — STOP, verify, record

Phases 0–4 are a coherent unit: the in-repo finalization of the error-handling overhaul. Phase 5 is a separate cross-repo track.

- [x] Run `make agent-check` and `make agent-test` — both must pass.
- [x] Commit Phases 3–4.
- [x] Tick every Phase 3 and Phase 4 box.
- [x] Append a dated **Checkpoint 3** entry to the Session log: confirm all in-repo follow-ups are done, list anything still deferred, and state whether Phase 5 (webhook signing) is being picked up now or scheduled separately.
- [x] At this point the in-repo work is shippable. Decide with the user whether to open a PR for `feature/API-readiness-2` now and run Phase 5 on its own branch, or continue. **→ Decided 2026-05-22: stop here** — no PR opened, Phase 5 not started; both deferred to a later session.

---

## Phase 5 — Webhook signing (Plan Item F / Stage 5) — separate cross-repo track

This is the last unshipped stage of the original error-handling plan. It is **cross-repo** (pipelex side + the API side land in coordinated lockstep) and has its own design and checkpoints. Treat it as an independent track — it can land on its own schedule and does not block Phases 0–4.

- [ ] Read [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md) end to end — it is the authoritative plan for this work.
- [ ] Follow that doc's own phases and checkpoints. Do not duplicate them here.
- [ ] Coordinate the cross-repo PRs (pipelex + API) so the signing secret and verification land together.

**Acceptance:** as defined in `wip/security/webhook-signing.md`.

---

## Phase 6 — Error class location convention + static enforcement

Discovery of `PipelexError` subclasses in `pipelex/errors/error_module_registry.py` relies on a filesystem pattern scan (`exceptions.py`, `*_exceptions.py`, `*_errors.py`) plus a hand-maintained allowlist `_NON_STANDARD_ERROR_MODULES`. A spot check found ~20 production error classes living in files matching neither convention — plugin worker/factory modules (`anthropic_factory.py`, `bedrock_llm_worker.py`, `openai_client_factory.py`, the google workers), single-error utility modules (`validate_bundle.py`, `module_inspector.py`, `index_loader.py`, `dry_run.py`, `model_reference.py`, `extract_input.py`, `pypdfium2_renderer.py`, `func_registry.py`, `concept_spec.py`, `stuff_spec_factory.py`), and mixed-concern modules (`pipeline_manager.py`, `template_image_analyzer.py`). They are silently absent from the generated `docs/errors/` pages and from `test_pipelex_error_type_uri_uniqueness`.

The fix is structural, not a runtime patch. Pipelex errors are part of the documented public contract (each has a `type_uri`, a docs page, stable identity) — they belong in dedicated exception modules, like Django's `django.core.exceptions` or SQLAlchemy's `sqlalchemy.exc`. Enforce that via filename convention and a static check; refactor stragglers into properly-named modules; remove discovery from runtime entirely.

- [x] **Decision D3** — pick the filename pattern. Recommended: **`exceptions.py` (default, one per package directory) + `*_exceptions.py` (for dirs that host multiple separate-concern error modules, e.g. plugin subpackages — the existing `portkey_exceptions.py` / `anthropic_exceptions.py` / `mistral_exceptions.py` / `gateway_exceptions.py` pattern)**. Drop `*_errors.py` — it is a redundant synonym (3 files today: `jinja2_errors.py`, `secrets_errors.py`, `template_errors.py`) and synonyms are exactly what produced the drift. Record the choice in the Decisions section. **→ Decided 2026-05-23: `exceptions.py` + `*_exceptions.py`** (see [Decisions](#decisions)).

### 6.1 — Static check first (TDD)

- [x] New test: AST-scan `pipelex/` for every `class X(...)` whose any transitive base resolves to `PipelexError`; assert each file matches the chosen pattern (plus the top-level `pipelex/base_exceptions.py`, which is special-cased as the root). Watch it fail, capture the misplaced list — that list is the authoritative refactor target.
- [x] Backstop test: walk `PipelexError.__subclasses__()` transitively after normal imports, assert each subclass's `__module__` resolves to a properly-named file. Catches dynamic / decorator-registered cases the AST scan would miss, and is the regression net once `error_module_registry.py` is gone.

### 6.2 — Refactor misplaced error classes

Expected starting list (the static check is authoritative — extend or trim as needed):

- `pipelex/pipeline/pipeline_manager.py` → append to existing `pipelex/pipeline/exceptions.py`.
- `pipelex/pipeline/validate_bundle.py` → `pipelex/pipeline/validate_bundle_exceptions.py` (sibling pattern keeps the error next to its caller in import-graph terms).
- `pipelex/pipe_operators/shared/template_image_analyzer.py` → `pipelex/pipe_operators/shared/exceptions.py`.
- `pipelex/tools/misc/{context_provider_abstract,filetype_utils,json_utils,toml_utils}.py` → consolidate into `pipelex/tools/misc/exceptions.py`.
- `pipelex/tools/secrets/secrets_utils.py` and `pipelex/tools/secrets/secrets_errors.py` (rename) → consolidate into `pipelex/tools/secrets/exceptions.py`.
- `pipelex/tools/pdf/pypdfium2_renderer.py` → `pipelex/tools/pdf/exceptions.py`.
- `pipelex/tools/typing/module_inspector.py` → `pipelex/tools/typing/exceptions.py`.
- `pipelex/tools/jinja2/jinja2_errors.py` → rename to `pipelex/tools/jinja2/exceptions.py`.
- `pipelex/cogt/templating/template_errors.py` → rename to `pipelex/cogt/templating/exceptions.py`.
- `pipelex/core/pipes/stuff_spec/stuff_spec_factory.py` → append to existing `pipelex/core/pipes/stuff_spec/exceptions.py`.
- `pipelex/plugins/google/google_{llm,img_gen}_worker.py` → `pipelex/plugins/google/google_exceptions.py` (or `exceptions.py` — D3 will decide whether to match the existing portkey/anthropic/mistral/gateway prefix style).
- `pipelex/plugins/anthropic/anthropic_factory.py` → append to existing `anthropic_exceptions.py`.
- `pipelex/plugins/bedrock/{bedrock_llm_worker,bedrock_factory}.py` → `pipelex/plugins/bedrock/bedrock_exceptions.py`.
- `pipelex/plugins/openai/{openai_client_factory,vertexai_factory}.py` → `pipelex/plugins/openai/openai_exceptions.py`.
- `pipelex/kit/index_loader.py` → append to existing `pipelex/kit/exceptions.py`.
- `pipelex/system/environment.py` → append to existing `pipelex/system/exceptions.py`.
- `pipelex/system/registries/func_registry.py` → `pipelex/system/registries/exceptions.py`.
- `pipelex/pipe_run/dry_run.py` → append to existing `pipelex/pipe_run/exceptions.py`.
- `pipelex/builder/concept/concept_spec.py` → `pipelex/builder/concept/exceptions.py`.
- `pipelex/cogt/models/model_reference.py` → `pipelex/cogt/models/exceptions.py`.
- `pipelex/cogt/extract/extract_input.py` → `pipelex/cogt/extract/exceptions.py`.

For each move:

- Update every import site (search by class name; do not rely on the static check to surface them).
- Watch for circular imports — if appending to an existing `exceptions.py` would create a cycle, prefer a new `<topic>_exceptions.py` module that imports only `PipelexError` / its immediate base.
- Don't leave shims or re-exports behind. Per project policy (no backward compatibility), update callers and move on.

### 6.3 — Delete the registry, simplify discovery

- [x] Delete `pipelex/errors/error_module_registry.py`. Replace `iter_pipelex_error_subclasses()` callers with a small inline transitive `__subclasses__()` walk in `error_pages_generator.py` (the only production consumer plus the URI-uniqueness test). Normal imports load everything now — no force-import phase needed, no allowlist to maintain. *(Refined by Phase 7: discovery is rehydrated by a dev/test-time `_force_load_all_error_modules` helper. Production bootstrap remains untouched.)*
- [x] `pipelex-dev generate-error-pages` — regenerate `docs/errors/` and verify the page set is complete (new pages appear for previously-missed classes; no orphan pages).

### 6.4 — Rule, docs, and the absorbed minor follow-up

- [x] Add the rule to `pipelex/.claude/rules/python-standards.md` under a new "Error class location" section: every `PipelexError` subclass lives in a module whose filename matches `exceptions.py` or `*_exceptions.py` (final wording per D3); the static check from 6.1 enforces it.
- [x] Reference it from `pipelex/CLAUDE.md` if appropriate. *(N/A — no `pipelex/CLAUDE.md` exists; the rule lives in `.claude/rules/python-standards.md` which is consulted by the top-level CLAUDE.md.)*
- [x] Also resolve here, since it touches the same generator: the `pascal_case_to_kebab` acronym collision (`LLMError` / `LlmError` both kebab to `llm-error`). Add a defensive assert in `error_pages_generator.generate_error_pages` that fails loudly if two target classes resolve to the same slug, and a short note near `PipelexError` warning that acronym-casing variants of an existing error class name collide. (Today this is caught reactively by `test_pipelex_error_type_uri_uniqueness` only.)

### 6.5 — Verify

- [x] Static check passes against the full tree.
- [x] Generated `docs/errors/` set is complete and `make agent-check` clean.
- [x] `make agent-test` clean.

**Acceptance:** every `PipelexError` subclass lives in a properly-named module; the static check fails the PR if a new error class lands outside the convention; `error_module_registry.py` is gone; discovery has no production-runtime side effects (the dev/test-time `_force_load_all_error_modules` helper added in Phase 7 walks the filesystem inside the docs generator and the URI uniqueness test only); the kebab-slug collision footgun is caught at generation time, not only by the uniqueness test.

### ⛔ CHECKPOINT 6 — STOP, verify, record

- [x] `make agent-check` and `make agent-test` clean.
- [x] Commit as a single coherent refactor (or a small ordered series: test-first → moves → registry deletion → rule).
- [x] Tick every Phase 6 box.
- [x] Append a dated **Checkpoint 6** entry to the Session log: Decision D3 outcome, files moved, import sites updated, the kebab-collision defense added, anything left as-is and why, next action.

---

## Minor follow-ups (low priority — batch into any checkpoint)

- (none open — `pascal_case_to_kebab` acronym collision and `error_module_registry` discovery fragility both folded into Phase 6.)

---

## Phase 7 — Error-class discovery contract (Fix #1 follow-up)

Phase 6 deleted `pipelex/errors/error_module_registry.py` on the premise that *every error class lives in a properly-named module that normal imports pull in*. The premise turned out **false**. A `/code-review` pass on the Phase 6 commit `0fa4440b` found that `docs/errors/index.md` had already regressed by 23 entries because plugin worker/factory modules use deferred imports (rightly so — the SDKs are heavy / optional), so the colocated `*_exceptions.py` modules for `anthropic`, `bedrock`, `google`, `openai`, `azure_rest`, `mistral`, `gateway`, `portkey`, plus a handful of non-plugin classes (`FalCredentialsError`, `GraphSpecError`/`GraphSpecValidationError`, `PipeBatchFactoryError`, `PipeSearchError`/`PipeSearchFactoryError`, `PipelexBundleSpecBlueprintError`) are never reached by `Pipelex.make()` at docs-generation time. Their `__subclasses__()` registration never happens, so the new `iter_pipelex_error_subclasses()` silently misses them.

A second commit (the Fix #2/#3/#4 commit landing right after this analysis) added the orphan-deletion path to `generate_error_pages` (so the 23 stale `.md` files are cleaned up rather than left as orphans on disk), a `removed` bucket in `ErrorPagesReport`, the `tomli` runtime-import fix in `pipelex/tools/misc/exceptions.py`, and an `xfail(strict=True)` completeness assertion at `tests/unit/pipelex/errors/test_error_class_location_convention.py::TestErrorClassLocationConvention::test_runtime_walk_discovers_every_ast_classified_subclass`. The xfail makes the gap visible in CI; the moment Phase 7 closes it, `strict=True` turns the unexpected pass into a CI failure that demands the marker be removed.

### Goal

Close the gap. Discovery must yield the same set the AST scan finds. The convention test's completeness assertion should pass without `xfail`.

### Decision D4 — discovery strategy

Three architectural options (all preserve the Phase 6 file-naming convention):

- **Option A — Explicit registration manifest.** A single source file (e.g. `pipelex/errors/_all_exceptions.py`) imports every `*_exceptions.py` module explicitly. The convention test grows a two-sided check: every `*_exceptions.py` on disk has a matching import in the manifest; every manifest import points at an existing `*_exceptions.py`. **Pros:** explicit, no runtime filesystem scan, fails loudly when someone adds a module without registering it. **Cons:** one extra edit per new error module; the manifest grows.
- **Option B — Eager `*_exceptions.py` import at `Pipelex.make()`.** Filesystem-walk for the convention patterns during bootstrap; force-import each one. Only error modules are loaded (verified safe: each plugin's `*_exceptions.py` imports only `CogtError`/`CredentialsError`/`PipelexError` — none pull in the plugin's SDK). **Pros:** zero maintenance; convention enforcement is structural. **Cons:** runtime filesystem touch (the smell the Phase 6 refactor wanted to delete); breaks in zip-wheel installs where `rglob` returns nothing.
- **Option C — Build-time codegen.** A `pipelex-dev` command regenerates `pipelex/errors/_all_exceptions.py` from the filesystem; CI fails if the generated file is stale. **Pros:** explicit at rest, automatic at update; eliminates runtime filesystem touch. **Cons:** needs CI integration; adds a generator + a check; two commits to land any new error module.

**Recommendation: Option A.** Explicit manifest. Trade one extra edit per module for visibility-in-source. The convention test makes forgetfulness an immediate CI failure on either side.

Record the decision in the Decisions section when taken.

### 7.1 — Implement the chosen option

- [x] **Decision D4** — pick A / B / C from above. Record date and rationale. **→ Decided 2026-05-23: Option B' (scoped rglob + force-import in dev/test consumers; no production bootstrap touch)** (see [Decisions](#decisions)).
- [x] Implement.
- [x] Verify: `make agent-test` runs the completeness assertion *without* the `xfail` marker (or, equivalently, the test passes and pytest reports `XPASS` under `strict=True`, prompting the marker's removal).
- [x] Remove `@pytest.mark.xfail(...)` from `test_runtime_walk_discovers_every_ast_classified_subclass`.

### 7.2 — Regenerate `docs/errors/`

- [x] `pipelex-dev generate-error-pages` — the previously-dropped pages reappear (recreated, not "removed"). Verify `ErrorPagesReport.written` lists them.
- [x] `docs/errors/index.md` carries every AST-discovered class.

### 7.3 — Update the docs / rules

- [x] In `.claude/rules/python-standards.md`, document the chosen discovery strategy alongside the existing "Error class location" rule. The convention is about file naming; D4 is about how those files become discoverable.

### Acceptance

- The completeness assertion test passes without `xfail`.
- `docs/errors/index.md` contains every AST-discovered class (no silent drops).
- Generating docs from a clean clone (`pipelex-dev generate-error-pages` after `git clean`) produces the same set as the AST scan.

### ⛔ CHECKPOINT 7 — STOP, verify, record

- [x] `make agent-check` and `make agent-test` clean (and the formerly-`xfail` test now passes without the marker).
- [x] Commit.
- [x] Tick every Phase 7 box.
- [x] Append a dated **Checkpoint 7** entry to the Session log: Decision D4 outcome, files touched, the AST/runtime set diff before and after, next action.

### Cold-start context for a fresh session

1. The smoking gun: `git show 0fa4440b -- docs/errors/index.md | head -50` shows the dropped entries. The current `docs/errors/index.md` is consistent with the deferred-import discovery state (208 entries); when Phase 7 closes, it should match the AST scan (231+ entries).
2. The completeness assertion lives at `tests/unit/pipelex/errors/test_error_class_location_convention.py::test_runtime_walk_discovers_every_ast_classified_subclass`. Run it first thing: it should xfail today. After Phase 7, remove the `@pytest.mark.xfail(...)` decorator.
3. The deleted `error_module_registry.py` (visible at `git show HEAD~N:pipelex/errors/error_module_registry.py` for the Phase 6 commit) had a body shaped roughly like the Option B implementation — useful as reference, but the recommended approach is Option A.
4. Plugin `*_exceptions.py` files were verified safe to force-import in any environment (extras-only included) — they don't transitively import the plugin SDK. So Option B isn't blocked by extras availability.

---

## Out of scope (recorded, not planned here)

- Webhook VERBOSE disclosure to caller-supplied URLs — sending a full `ErrorReport` to the run caller's own endpoint is by design (plan §D.3: the endpoint belongs to the caller, who already owns the run data; the receiver decides what to re-expose). Webhook signing (Phase 5) is orthogonal — it authenticates origin, it does not reduce disclosure. No separate task; revisit only if the threat model changes.
- Critical #1 from the `/review` pass (`recover_error_report` raising on a stale report dict) — resolved as not-a-bug: the Temporal integration has never shipped, so there is no prior on-wire schema. Docs are aligned in Phase 0. Nothing else to do.

---

## Decisions

Record each decision here as it is taken, with date and rationale.

- **D1** (Phase 1, Gap 1 fix) — **Option 1**, decided 2026-05-22. Add a per-class `ClassVar` flagging error classes that genuinely author caller-facing messages, and gate the STRICT-disclosure passthrough on that flag instead of on the inherited `error_domain == INPUT`. Rationale: keys redaction on the *provenance of the message* rather than an inherited classification, and avoids the `http_status` side effects Option 2 (dropping `error_domain` inheritance for domain-less wrappers) would carry.
- **D2** (Phase 2, request_id call-site strategy) — **Bound adapter**, decided 2026-05-22. `WorkflowLog` / `ActivityLog` gain an instance-level `request_id` (held by a shared `_RequestIdLog` base), built once per workflow/activity invocation from `job_metadata.request_id`; the dead per-method `request_id` kwargs are dropped. Rationale: a new log call added inside a wired entry point picks up `request_id` automatically — no per-call threading, nothing to forget — and the per-method kwarg was unused dead surface.
- **D3** (Phase 6, error class location filename pattern) — **`exceptions.py` + `*_exceptions.py`**, decided 2026-05-23. Every module declaring a `PipelexError` subclass must be named `exceptions.py` (default — one per package directory) or `<topic>_exceptions.py` (for directories that host multiple separate-concern error modules, matching the existing `pipelex/plugins/*/` pattern: `portkey_exceptions.py`, `anthropic_exceptions.py`, `mistral_exceptions.py`, `gateway_exceptions.py`). The `*_errors.py` synonym is dropped — it adds no information, and three files (`jinja2_errors.py`, `secrets_errors.py`, `template_errors.py`) get renamed. The root `pipelex/base_exceptions.py` is special-cased. Rationale: synonyms are exactly what produced the drift the registry exists to paper over; one canonical pattern + one topical variant covers the legitimate cases without inviting a third.
- **D4** (Phase 7, error class discovery strategy) — **Option B' (scoped rglob + force-import in dev/test consumers only)**, decided 2026-05-23. `pipelex/errors/error_pages_generator.py` gains a `functools.cache`-d `_force_load_all_error_modules()` helper that rglob-scans the package for `exceptions.py` / `*_exceptions.py` and `importlib.import_module`s each; `iter_pipelex_error_subclasses` calls it as its first statement. Production bootstrap (`Pipelex.make()`) does NOT touch it — discovery has zero runtime side effect outside the docs generator and the type-URI uniqueness test. Rationale: this option carries the convention contract through to discovery without re-introducing a hand-maintained list (Phase 6's original drift target). Option A (explicit manifest) was rejected because the manifest is a second copy of information already on disk under the convention — it would have to be maintained for the life of the codebase and the two-sided test would be the only thing keeping it in sync. Option B' achieves the same end with zero maintenance: empirically verified that every `*_exceptions.py` imports only base error classes (zero SDK pulls), and Phase 6's filename convention guarantees the rglob is complete. The Phase 6 deletion of `error_module_registry.py` was right to remove the production runtime touch but overshot — Phase 7 restores the discovery helper, scoped to the two dev/test-time consumers that legitimately need it.

---

## Session log

Append one dated entry per session / checkpoint. Each entry must leave the next session enough to cold-start: what landed, decisions taken, current code state, what is broken or deferred, and the exact next action.

- **2026-05-22 — Checkpoint 0 (Phase 0 complete).** Documentation coherence pass landed as a single docs-only commit on `feature/API-readiness-2`. No code-behavior change — docstrings, comments, and markdown only. `make agent-check` clean (pyright + mypy: 0 errors).

  **Drift found and fixed:**

    - `docs/under-the-hood/error-model.md` — `ErrorReport` now described as a frozen Pydantic *model* (was "dataclass", stale since the Stage 3 `BaseModel` conversion); added the `title` / `type_uri` rows to the field table (they were missing). The `extra="forbid"` warning was already correct — it does not claim `recover_error_report()` trims unknown keys.
    - `pipelex/temporal/log_temporal.py` — softened the `WorkflowLog` / `ActivityLog` docstrings: the `request_id` kwarg is accepted but not yet threaded by any caller (wiring is Phase 2).
    - `pipelex/base_exceptions.py` — fixed a stale inline comment on `_declared_type_uri` ("bootstrap-registered errors base URI" → the `URLs.error_docs_base` constant; `type_uri()` is pure since the `ErrorManager` removal).
    - `pipelex/temporal/tprl/temporal_error.py` — dropped two stale references to the removed in-process `PipeRouter` retry loop (`TemporalError` class docstring + `_is_non_retryable`).
    - `api-companion-revisions.md` — rewrote §B Acceptance (`request_id` rides on `JobMetadata` and is threaded explicitly into log calls; **no `ContextVar`**, because a ContextVar is process-local and does not survive the Temporal serialization boundary); made the Stage 1 `request_id` claim honest (kwarg accepted, not wired end to end); rewrote "Net to the API team" to point at this `TODOS.md` for the post-review follow-ups.
    - `wip/error-handling/README.md` — added the API-readiness track to the "Status at a glance" table; rewrote "What's still open" to list webhook signing, the STRICT-disclosure gap, the webhook-payload collision, the `request_id` wiring, and the metadata-model long tail, each linking its tracker.
    - `wip/error-handling/archive-error-handling-2.md` — added an `ARCHIVED — COMPLETE` header line (the only archive whose title still read as a current plan).
    - `wip/error-handling/changes-for-api-early-draft.md` — added a "superseded — see `api-companion-revisions.md`" banner.

  **Verified correct, left as-is:** `pipelex/temporal/exceptions.py` `UnrecoverableWorkflowFailureError` docstring (already states it is synthesized only when no report dict is found); `base_exceptions.py` / `delivery_executor.py` / `error_pages_generator.py` / `error_module_registry.py` docstrings (swept — no drift). **Deliberate omission:** `error-model.md` does not yet document `DisclosureMode` / `to_problem_document` — not a contradiction (an under-the-hood doc need not be exhaustive), and Phase 1 changes STRICT behavior, so documenting it now would only be rewritten.

  **Coherence:** `TODOS.md`, `api-companion-revisions.md` "Current state", and `README.md` "What's still open" now agree — Stages 1-4 landed via PR #931; pending = webhook signing (Stage 5) + the four `/review` follow-ups.

  **Decisions:** none taken — D1 (Phase 1) and D2 (Phase 2) remain pending.

  **Next action:** start **Phase 1** — STRICT disclosure INPUT-domain leak. Take **Decision D1** first (recommended: Option 1 — per-class `ClassVar` flagging caller-facing-message authors).

- **2026-05-22 — Decision D1 recorded.** Per the user, Decision D1 is **Option 1** (see the Decisions section for the full rationale); the Phase 1 D1 box is ticked to reflect it. Phase 1 **implementation is not started** — no implementation boxes ticked, no code touched. Next action: begin Phase 1 (STRICT disclosure INPUT-domain leak) at the first unticked box (implement the Gap 1 fix).

- **2026-05-22 — Checkpoint 1 (Phase 1 complete).** STRICT-disclosure INPUT-domain leak closed on `feature/API-readiness-2` as a single commit. `make agent-check` clean (pyright + mypy: 0 errors); `make agent-test` full suite green.

  **Decision D1:** Option 1, implemented exactly as decided.

  **What landed:**

    - `pipelex/base_exceptions.py` — new `PipelexError._authors_caller_facing_message` `ClassVar` (default `False`) and new `ErrorReport.caller_facing_message: bool` field. `to_error_report()` sets the field from the class flag; `_enrich_error_report_from_cause` carries it **wrapper-wins** — never inherited from the `__cause__` chain, since it tracks the provenance of `report.message` (always the wrapper's own message). `to_dict(STRICT)` now gates the `message` passthrough on `caller_facing_message`, not on `error_domain == INPUT`.
    - **Gap 2:** new `_STRICT_PROVIDER_FIELDS` constant — `provider` / `model` / `provider_metadata` are stripped from the STRICT caller-facing passthrough branch too (already absent from the redacted branch). STRICT now never emits provider metadata for any `error_domain`.
    - `caller_facing_message` is serialized **only when `True`** (popped from `to_dict` output otherwise), so non-caller-facing reports — the common case — serialize identically to before; `from_dict` defaults it back to `False`, so the round-trip holds. `to_problem_document` never echoes it (new `_PROBLEM_DOCUMENT_OMITTED_FIELDS`) — it is internal redaction plumbing, not consumer classification.
    - `pipelex/core/interpreter/exceptions.py` (`PipelexInterpreterError`) and `pipelex/pipeline/validate_bundle.py` (`ValidateBundleError`) — the two INPUT-domain classes — set `_authors_caller_facing_message = True`. `BundleElaboratorError` inherits it (normal inheritance, unlike `_declared_title`). All other classes keep the safe `False` default.
    - `pipelex/cogt/exceptions.py` — `CogtError.to_error_report()` override threads `caller_facing_message` through too (resolves to `False`).
    - Docstrings: `DisclosureMode`, `ErrorReport.to_dict` / `to_problem_document`, `PipelexError._enrich_error_report_from_cause`, and the module constant comments rewritten to describe provenance-gated redaction.

  **Redaction behavior now in effect (STRICT):** `provider` / `model` / `provider_metadata` always dropped. If `caller_facing_message` — keep `message` + `user_action` + stable identifiers. Else — `message` → `INTERNAL_ERROR_PLACEHOLDER`, drop `user_action`, keep only the stable identifiers (`error_type` / `error_domain` / `error_category` / `retryable` / `title` / `type_uri`).

  **Tests:** `tests/unit/pipelex/test_error_report_disclosure_mode.py` rewritten for the new contract — includes the regression pin (`PipelexUnexpectedError` raised `from` a `PipelexInterpreterError` → report classified `error_domain=INPUT` but `caller_facing_message=False` → message redacted) and the Gap 2 pin (caller-facing passthrough strips provider fields). `test_error_report_problem_document.py` — old `INPUT`-passthrough test replaced; added STRICT-never-emits-provider-fields and `caller_facing_message`-never-an-extension-member tests. `test_class_level_metadata.py` — added a `caller_facing_message` class-level parametrized test.

  **Tracker:** `wip/error-handling/track-strict-disclosure-input-domain-gap.md` marked landed (banner + Acceptance checkboxes ticked).

  **Deferred / not done:** Only `PipelexInterpreterError` and `ValidateBundleError` are flagged caller-facing — the exact two INPUT-domain classes the tracker named. Classes like `MthdsDecodeError` (TOML decode) author arguably-caller-facing messages but are not flagged: the safe default redacts them, which is a usability nit, not a leak, and STRICT is not rendered for those surfaces today. Widening the flag set is a future follow-up if it proves needed.

  **Decisions:** D1 done. **D2 (Phase 2) still pending.**

  **Next action:** start **Phase 2** — finish wiring `request_id` into Temporal logs. Take **Decision D2** first (recommended: bound-adapter approach, rebuilt per activity/workflow invocation).

- **2026-05-22 — Phase 1 follow-up: `MthdsDecodeError` collapsed into `PipelexInterpreterError`.** Resolves the inconsistency flagged in the Checkpoint 1 "Deferred" note. `MthdsDecodeError` was a one-line `TomlError` subclass raised in a single place (`interpreter.py`) as a verbatim field-for-field re-wrap of `TomlError` — it added no context, sat in the wrong type family (`ToolError` lineage → no `error_domain`, so a caller's broken-TOML `.mthds` was classified as a 500 instead of a 422), and forced `agent_output.py` to carry a manual `"MthdsDecodeError": "input"` classification patch.

  Per the user's decision, deleted the class. `interpreter.py` now formats the TOML line/column into the message and raises `PipelexInterpreterError` directly (already `error_domain=INPUT` + `caller_facing_message=True`); the original `TomlError` stays on the `__cause__` chain. The four `except MthdsDecodeError` blocks in `validate_bundle.py` fold into the existing `except PipelexInterpreterError` clauses (identical resulting `ValidateBundleError`, same message); the three CLI `except (PipelexInterpreterError, MthdsDecodeError)` tuples collapse to `except PipelexInterpreterError`; the `agent_output.py` hint + domain patch entries are removed; the `invalid_mthds.py` test cases expect `PipelexInterpreterError`. `docs/errors/` regenerated via `pipelex-dev generate-error-pages` (orphan `mthds-decode-error.md` removed, `index.md` updated). `make agent-check` clean; `make agent-test` green. There is now one interpreter-input error class, correctly classified — no `agent_output.py` patch needed.

- **2026-05-22 — Phase 1 follow-up: `/code-review` pass.** An xhigh-effort `/code-review` of the Phase 1 + `MthdsDecodeError` commits found no runtime bug but flagged doc-coherence regressions: the Phase 1 STRICT-behavior change had updated only `track-strict-disclosure-input-domain-gap.md` and this file, leaving `CHANGELOG.md`, `wip/error-handling/api-companion-revisions.md`, and `wip/error-handling/README.md` still describing the old `error_domain == INPUT` passthrough. Fixed all three to describe the provenance-gated (`caller_facing_message`) rule; `README.md` "What's still open" no longer lists the now-landed STRICT gap (items renumbered). Also restored an `error_category`-retention assertion that the STRICT-redaction test rewrite had dropped. **Two findings left as judgment calls, not acted on:** (4) `bundle_elaborator.py:81` raises an internal "...this is a bug" invariant assertion as `BundleElaboratorError`, which inherits `caller_facing_message=True`, so STRICT would reflect that internal message — it is a defense-in-depth guard the code comments call "unreachable today"; the clean fix is to raise `PipelexUnexpectedError` there. (5) `to_dict(STRICT)` of a caller-facing report emits the internal `caller_facing_message: true` flag onto the lossy projection (harmless boolean; `to_problem_document` already scrubs it via `_PROBLEM_DOCUMENT_OMITTED_FIELDS`). `make agent-check` clean. Next action unchanged: start **Phase 2**.

- **2026-05-22 — Phase 1 follow-up: applied review findings 4 & 5.** The two `/code-review` findings previously left as judgment calls are now fixed. (4) `bundle_elaborator.py:81` — the internal "…this is a bug" nested-directive guard now raises `PipelexUnexpectedError` instead of `BundleElaboratorError`. It is a genuine internal-invariant violation, so it no longer rides the caller-facing `PipelexInterpreterError` path (`interpreter.py`'s `except BundleElaboratorError` no longer catches it — it surfaces as an unexpected error, 500, message redacted under STRICT, which is correct). The other `BundleElaboratorError` raises (caller-facing collision / invalid-bundle messages) are unchanged. (5) `to_dict(STRICT)` of a caller-facing report no longer emits the internal `caller_facing_message` flag — new `_STRICT_PASSTHROUGH_DROPPED_FIELDS` constant drops it alongside the provider fields; the flag rides only the VERBOSE round-trip format. The STRICT-passthrough test assertion was flipped to pin its absence. `make agent-check` clean; `make agent-test` green. Next action unchanged: start **Phase 2**.

- **2026-05-22 — Checkpoint 2 (Phase 2 complete).** `request_id` log wiring finished on `feature/API-readiness-2` as a single commit. `make agent-check` clean (pyright + mypy: 0 errors); `make agent-test` full suite green.

  **Decision D2:** bound adapter — implemented as decided (see the Decisions section).

  **What landed:**

    - `pipelex/temporal/log_temporal.py` — new `_RequestIdLog` base holds an instance-level `request_id`; `WorkflowLog` / `ActivityLog` subclass it. `_build_extra` is now an instance method reading the bound `request_id`. The per-method `request_id` kwarg — dead surface, no caller ever passed it — is **dropped** from every log method. The module-level `workflow_log` / `activity_log` singletons stay, unbound (`request_id is None`), for call sites with no `job_metadata` in scope.
    - `pipelex/temporal/tprl_pipe/wf_pipe_run.py` and `wf_pipe_router.py` — the workflow entry points that log. Each `run()` builds a per-invocation `workflow_log = WorkflowLog(request_id=<job_metadata>.request_id)` as its first statement; every existing `workflow_log.*` call in the function picks it up unchanged (the local shadows nothing — the import is now the `WorkflowLog` class). `WfPipeRun` reads `pipe_job.job_metadata.request_id`; `WfPipeRouter` reads `workflow_arg.job_metadata.request_id`.
    - Activities were checked: no Temporal activity logs via `activity_log` today (only `TemporalError._log_*` does, and it has no `job_metadata`), so there is no activity entry point to wire — `ActivityLog` keeps the symmetric bound capability for when one appears.

  **Wiring mechanism:** per-invocation bound `WorkflowLog`, rebuilt every workflow `run()` from that invocation's `JobMetadata` — no `ContextVar`, no module/process state. A new log call added inside a wired entry point carries `request_id` automatically.

  **Per-method kwargs:** dropped (not kept). `request_id` is held as instance state on the bound adapter; the kwargs were unused dead surface.

  **Tests:**

    - `tests/unit/pipelex/temporal/test_log_temporal_request_id.py` — pins the `_build_extra` path: a bound `WorkflowLog` / `ActivityLog` packs `extra={"request_id": ...}` into the log call, an unbound one passes `extra=None`.
    - `tests/integration/pipelex/temporal/test_wf_pipe_run_request_id_logging.py` — end-to-end: dispatches `WfPipeRun` (failing-router stub, modeled on `test_wf_pipe_run_failure_path.py`) with a `request_id` on `job_metadata`, captures the `temporalio.workflow` logger, asserts records carry `record.request_id`. Verified to have teeth — temporarily unbinding the logger made it fail (`request_ids seen: ['None']`), then reverted.

  **Docs:** `api-companion-revisions.md` §B Acceptance + the Stage 1 `WorkflowLog`/`ActivityLog` bullet + the "Net to the API team" post-review-follow-ups bullet rewritten to describe the landed wiring; `wip/error-handling/README.md` "What's still open" — the `request_id` log-wiring item removed, items renumbered; `log_temporal.py` docstrings state the wiring as fact.

  **Deferred / not done:** `TemporalError._log_critical` / `_log_error` (`temporal_error.py`) still log via the unbound singletons — they are error-bridge helpers, not entry points, and have no `job_metadata` in scope; threading `request_id` there is out of scope for Item B. The `wf_test_*` workflows likewise stay unbound (test infra, no inbound request id).

  **Decisions:** D1 + D2 done.

  **Next action:** start **Phase 3** — webhook payload reserved-key collision. Full analysis and options in [`wip/error-handling/track-webhook-payload-collision.md`](wip/error-handling/track-webhook-payload-collision.md); implement Option 1 (a `field_validator` on `WebhookTarget.payload` rejecting the reserved-key set at construction time).

- **2026-05-22 — Phase 2 follow-up: `/code-review` pass.** An xhigh-effort `/code-review` of the Phase 2 commit (5-angle + sweep) found **no correctness bugs** — the `request_id` wiring, the `WorkflowLog` / `ActivityLog` refactor, and both tests verified clean across line-by-line, removed-behavior, cross-file, language-pitfall, and wrapper-correctness angles (all 7 method bodies confirmed to route to the right logger at the right level; the dropped per-method kwarg confirmed dead surface with no caller). Two low-severity test-hygiene tweaks applied: the integration test's `addHandler` / `setLevel` moved inside the `try` so the `finally` restore is structurally airtight; the unit test (`test_log_temporal_request_id.py`) parametrized over all seven severity methods — was `.info()` only — so 28 cases now pin every method's level + `extra`. `make agent-check` clean; both test files green. Next action unchanged: start **Phase 3**.

- **2026-05-22 — Checkpoint 3 (Phases 3 & 4 complete).** The in-repo finalization of the error-handling overhaul is done on `feature/API-readiness-2`, landed as a single coherent commit. `make agent-check` clean (pyright + mypy: 0 errors); `make agent-test` full suite green.

  **Phase 3 — webhook payload reserved-key collision:**

    - `pipelex/pipe_run/delivery_assignment.py` — new `_RESERVED_WEBHOOK_PAYLOAD_KEYS` frozenset (`pipeline_run_id` / `status` / `result_url` / `error`) and a `field_validator` (`_reject_reserved_keys`, `mode="after"`) on `WebhookTarget.payload` that raises a `ValueError` naming the offending key(s) at construction time. A misconfigured webhook now fails when the `DeliveryAssignment` is built, not silently at delivery time. Option 1 from the tracker, implemented as planned.
    - `tests/unit/pipelex/pipe_run/test_delivery_assignment.py` — added to `TestDeliveryAssignment`: a parametrized reject test (one case per reserved key), a multi-collision test (the error names every offending key), and a clean-payload pass test.
    - Tracker `track-webhook-payload-collision.md` — marked landed (banner added).

  **Phase 4 — test coverage backfill:**

    - `recover_error_report` — `tests/unit/pipelex/temporal/test_recover_error_report.py` gained `test_found_but_invalid_report_dict_raises_validation_error`: a dict that `_find_error_report_dict` accepts (`error_type` + `message`) but that fails `ErrorReport` validation (missing required `title` / `type_uri`) raises `pydantic.ValidationError` — pins the current contract that a found-but-invalid report is an internal contract bug, not synthesized away. (The TODOS Phase 4 line names this file under `tests/integration/` — stale path; the file is and always was under `tests/unit/`. Harmless.)
    - `_message_from_exc` — new `tests/unit/pipelex/temporal/test_message_from_exc.py` (`TestMessageFromExc`): the `id()`-based cycle guard (a self-referential `__cause__` chain terminates) and the `repr(exc)` fallback (every message in the chain empty). Imports the private function with the codebase's established `# noqa: PLC2701  # pyright: ignore[reportPrivateUsage]` pattern.
    - `DeliveryActivityArg` — new `tests/unit/pipelex/temporal/test_delivery_activity_arg.py` (`TestDeliveryActivityArg`): a focused JSON round-trip (`model_validate_json(model_dump_json())`) with a populated nested `ErrorReport` (incl. a nested `UserAction`), catching a nested-model serialization regression without a live Temporal worker.
    - Logging `request_id` path — confirmed `tests/unit/pipelex/temporal/test_log_temporal_request_id.py` (from Phase 2) exists and is green (28 parametrized cases).

  **Doc coherence (beyond the strict checklist, for clean-slate consistency):** `wip/error-handling/README.md` "What's still open" + "Status at a glance" — Phases 3-4 removed from the open list, items renumbered (only webhook signing + the metadata-model long tail remain open); `api-companion-revisions.md` "Net to the API team" — the post-review follow-ups now all marked landed; `CHANGELOG.md` `[Unreleased]` — the delivery-webhook entry gained a sentence noting reserved keys are now rejected at construction (the webhook feature is unreleased, so this is a constraint on a new feature, not a breaking change to shipped software).

  **Deferred / not done:** Nothing from Phases 0-4. The two "Minor follow-ups" (`pascal_case_to_kebab` acronym collision; `error_module_registry` discovery fragility) are still open — TODOS marks them low-priority and batchable into any checkpoint; left for a future pass. Phase 5 (webhook signing) is the separate cross-repo track, untouched.

  **Decisions:** D1 + D2 done (Phases 1-2). No new decision in Phases 3-4.

  **Next action:** All in-repo follow-ups (Phases 0-4) are done — `feature/API-readiness-2` is shippable. **Decision (2026-05-22, with the user): stop here** — no PR opened and Phase 5 not started; both deferred to a later session. To resume, the open work is: (1) open a PR for `feature/API-readiness-2` — Phases 0-4 are a complete, reviewable unit; (2) **Phase 5** — webhook signing, the separate cross-repo track (pipelex + API in lockstep) per [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md); (3) the two low-priority "Minor follow-ups" (`pascal_case_to_kebab` acronym collision, `error_module_registry` discovery fragility), batchable into any future checkpoint.

- **2026-05-22 — Checkpoint 3 follow-up: `/code-review` pass.** An xhigh-effort `/code-review` of the Phases 3-4 commit (5 angles + sweep, three independent finders) found **no runtime bug** — the `WebhookTarget.payload` reserved-key validator verified correct across line-by-line, cross-file (the reserved set exactly matches the four keys `_notify_webhook` writes), language-pitfall, bypass-path, and doc-coherence angles. One real test-quality defect fixed: the reserved-key tests' message-quality assertions were vacuous — `str(ValidationError)` contains every payload key via pydantic's echoed `input_value={...}` (and "error" via boilerplate), so `match=reserved_key` and `assert "error" in message` passed regardless of the validator's own message. Both now pin the validator's distinctive `reserved keys: [...]` phrase, which the input echo and boilerplate cannot satisfy. The core "rejects reserved keys" contract (`pytest.raises(ValidationError)`) was already sound — only the message-naming check was hardened. `make agent-check` clean; reserved-key tests green. Committed as `bfa3cfba`. Next action unchanged: in-repo work (Phases 0-4) done; PR + Phase 5 deferred per the user.

- **2026-05-23 — Checkpoint 6 (Phase 6 complete).** Error-class location convention enforced and `error_module_registry.py` deleted on `feature/API-readiness-2`. `make agent-check` clean (ruff + pyright + mypy: 0 issues); `make agent-test` full suite green.

  **Decision D3:** `exceptions.py` (default — one per package directory) + `<topic>_exceptions.py` (for directories hosting multiple separate-concern error modules, matching the existing `pipelex/plugins/*/` convention). The `*_errors.py` synonym is dropped — it produced exactly the kind of drift the registry was papering over.

  **TDD path:** `tests/unit/pipelex/errors/test_error_class_location_convention.py` written first — two complementary checks. (1) An AST scan of every `.py` under `pipelex/` that resolves the transitive `PipelexError` descendant set by class-name graph traversal and asserts each one lives in a properly-named module. (2) A runtime backstop that walks `PipelexError.__subclasses__()` transitively after normal imports — catches dynamic / decorator-registered cases the AST scan would miss, and is the regression net once the registry was gone. Both tests failed on first run with **43 misplaced classes** (AST scan — the authoritative target) / **28 currently loaded** (runtime backstop), agreeing on the same offenders.

  **Refactor (Phase 6.2) — files moved or created:**

    - Appended to existing `exceptions.py`: `PipelineManagerNotFoundError` / `PipelineManagerAlreadyExistsError` / `ValidateBundleError` → `pipelex/pipeline/exceptions.py`; `BundleElaboratorError` → `pipelex/core/interpreter/exceptions.py`; `StuffSpecFactoryError` → `pipelex/core/pipes/stuff_spec/exceptions.py`; `KitIndexLoadingError` → `pipelex/kit/exceptions.py`; `EnvVarNotFoundError` → `pipelex/system/exceptions.py`; `DryRunError` → `pipelex/pipe_run/exceptions.py`; `BaseModelPayloadConverterError` → `pipelex/temporal/exceptions.py`; `AnthropicFactoryError` → `pipelex/plugins/anthropic/anthropic_exceptions.py`.
    - New `exceptions.py` modules: `pipelex/pipe_operators/shared/exceptions.py` (`WithImagesFilterError`, `UnusedInputError`); `pipelex/system/registries/exceptions.py` (`FuncRegistryError`); `pipelex/builder/concept/exceptions.py` (`ConceptSpecError`); `pipelex/cogt/models/exceptions.py` (`ModelReferenceParseError`); `pipelex/cogt/extract/exceptions.py` (`ExtractInputError`); `pipelex/cogt/img_gen/exceptions.py` (`FalCredentialsError`); `pipelex/tools/aws/exceptions.py` (`AwsCredentialsError`); `pipelex/tools/pdf/exceptions.py` (`PyPdfium2RendererError`); `pipelex/tools/typing/exceptions.py` (`ModuleFileError`); `pipelex/tools/misc/exceptions.py` (consolidates `TomlError` + `ContextProviderError` + `FileTypeError` + `ArgumentTypeError` + `JsonTypeError`); `pipelex/tools/secrets/exceptions.py` (consolidates `SecretNotFoundError` from the renamed `secrets_errors.py` + the three `secrets_utils.py` errors `VarNotFoundError` / `VarFallbackPatternError` / `UnknownVarPrefixError`).
    - Renames (drop `*_errors.py`): `pipelex/tools/jinja2/jinja2_errors.py` → `pipelex/tools/jinja2/exceptions.py`; `pipelex/cogt/templating/template_errors.py` → `pipelex/cogt/templating/exceptions.py`. `pipelex/tools/secrets/secrets_errors.py` deleted (content folded into the new `exceptions.py`).
    - New `<topic>_exceptions.py` modules (plugin-prefix pattern): `pipelex/plugins/bedrock/bedrock_exceptions.py` (`BedrockFactoryError` + `BedrockWorkerConfigurationError`); `pipelex/plugins/google/google_exceptions.py` (`GoogleLLMWorkerError` + `GoogleImgGenWorkerError`); `pipelex/plugins/openai/openai_exceptions.py` (`OpenAIClientFactoryError` + `VertexAIConfigError` + `VertexAICredentialsError`); `pipelex/plugins/azure_rest/azure_exceptions.py` (`AzureCredentialsError`).
    - **Adjacent cleanup, in scope:** the broken back-compat shim `pipelex/pipe_operators/llm/template_image_analyzer.py` (re-export aggregator referencing the no-longer-present `WithImagesFilterError` / `UnusedInputError` after the move) was deleted, its three callers migrated to the canonical paths. The sibling `pipelex/pipe_operators/llm/image_reference.py` shim was left alone — it pre-dates this refactor and is not error-class-related.
    - No back-compat shims or re-exports left behind anywhere. Every import site updated by class name across `pipelex/`, `tests/`, and `docs/` examples.

  **Registry deletion (Phase 6.3):** `pipelex/errors/error_module_registry.py` deleted. The `iter_pipelex_error_subclasses` helper now lives directly in `error_pages_generator.py` as a simple transitive `__subclasses__()` walk — no filesystem scan, no `_NON_STANDARD_ERROR_MODULES` allowlist, no force-import phase. The two callers (`error_pages_generator.generate_error_pages` + the URI-uniqueness test in `tests/unit/pipelex/test_pipelex_error_type_uri_uniqueness.py`) import from the new location. Normal production imports now reach every error class — the convention test guarantees it.

  **Docs regeneration:** `pipelex-dev generate-error-pages` ran cleanly — 209 total pages, 32 updated (their "Defined in" field changed to the new module), 177 unchanged, **1 new page** (`docs/errors/base-model-payload-converter-error.md` — `BaseModelPayloadConverterError` was previously silently missed by the registry's filename pattern scan). No orphan pages; the generator walks the current hierarchy.

  **Rule + kebab-slug collision defense (Phase 6.4):**

    - New "Error class location" section in `.claude/rules/python-standards.md` — states the convention, points at the convention test, calls out the `*_errors.py` ban and the topical-split escape hatch, and warns about acronym-casing kebab collisions.
    - `error_pages_generator.generate_error_pages` now asserts kebab-slug uniqueness across `target_classes` before writing pages — raises a loud `RuntimeError` naming the two colliding classes if e.g. both `LLMError` and `LlmError` resolve to `llm-error`. Today this is caught reactively by `test_pipelex_error_type_uri_uniqueness`; now it fails at generation time too.
    - Short note added near `PipelexError.type_uri()` describing the collision footgun and pointing at both defenses.
    - New unit test `test_kebab_slug_collision_raises` in `test_error_pages_generator.py` pins the new guard with a synthetic `LLMError` / `LlmError` pair.

  **Test count:** 9 in `tests/unit/pipelex/errors/` (2 convention, 7 generator), all green. Both convention tests verified to have teeth — they failed on first run with the misplaced list.

  **Deferred / not done:** Nothing from Phase 6 itself. The `_for_api/CLAUDE.md` "Reference it from `pipelex/CLAUDE.md`" sub-bullet is N/A — no such file exists; the workspace consults `.claude/rules/python-standards.md` (which now carries the rule) from the top-level CLAUDE.md.

  **Decisions:** D1 + D2 + D3 all done.

  **Next action:** Stop at this checkpoint per the project policy. Confirm with the user before opening a PR — Phase 6 is a large, file-touching refactor (173 changed files: 1 deletion, 16 new `exceptions.py`/`*_exceptions.py` modules, 1 renamed module, ~150 source/test/doc edits) that should be reviewed as a single coherent commit (or a small ordered series: test-first → moves → registry deletion → rule).

- **2026-05-23 — Phase 6 follow-up: `/code-review` pass at xhigh effort.** Five independent finder angles + Phase 2 verifiers + a sweep finder found a **shipped regression in the Phase 6 commit `0fa4440b`**: `docs/errors/index.md` dropped 23 entries (HEAD~1 = 230, HEAD = 208). The new `__subclasses__()`-based `iter_pipelex_error_subclasses` doesn't reach plugin/factory `*_exceptions.py` because plugin workers/factories use deferred imports (rightly — the SDKs are heavy/optional). Class names dropped: `AnthropicModelListingError`, `AnthropicSDKUnsupportedError`, `AnthropicWorkerConfigurationError`, the six gateway errors, the four mistral errors, the three portkey errors, `FalCredentialsError`, both graph errors, `PipeBatchFactoryError`, both pipe-search errors, `PipelexBundleSpecBlueprintError`. The OLD `error_module_registry._discover_standard_exception_modules()` filesystem-scan + force-import had been silently doing this work; Phase 6 deleted it on the premise that "natural imports reach every error module" — false premise.

  **Findings landed in this session (Fix #2 + Fix #3 + Fix #4 + orphan cleanup):**

    - **Fix #4 (`tomli` TYPE_CHECKING regression)**: `pipelex/tools/misc/exceptions.py` — moved `import tomli` out of `TYPE_CHECKING`. Pre-refactor `toml_utils.py` had it at module-top; the Phase 6 move demoted it. `typing.get_type_hints(TomlError.from_tomli_error)` now resolves cleanly; no current caller exercises that path, but the gap blocked any future autodoc / annotation-introspecting tool. Verified live: `python -c "import typing; from pipelex.tools.misc.exceptions import TomlError; typing.get_type_hints(TomlError.from_tomli_error)"` succeeds.
    - **Fix #2 (orphan-page deletion)**: `pipelex/errors/error_pages_generator.py` — added a fourth `removed` bucket to `ErrorPagesReport` and a `_remove_orphans()` helper. Generated pages whose slug is no longer in `target_classes` are deleted; pages with `<!-- pipelex:authored -->` are preserved verbatim; pages with neither marker (out-of-scope hand-files) are left untouched. The dev CLI command's success panel surfaces the new `Removed: N` count. Three new unit tests pin the behavior: orphan deletion, authored-marker preservation, unmarked-file isolation.
    - **Fix #3 (completeness assertion)**: `tests/unit/pipelex/errors/test_error_class_location_convention.py` — refactored the AST scan into a reusable `_ast_discover_pipelex_error_subclasses()` helper, then added `test_runtime_walk_discovers_every_ast_classified_subclass`. It compares the AST-discovered class-name set to the runtime-loaded class-name set after normal imports, fails loudly with the missing names if they diverge. Marked `@pytest.mark.xfail(strict=True, ...)` pending Phase 7 / Decision D4. When the discovery contract is fixed, the test passes and `strict=True` turns the unexpected pass into a CI failure that prompts the marker's removal.
    - **Orphan cleanup**: ran `pipelex-dev generate-error-pages` on the real `docs/errors/` — 23 stale per-class `.md` files (the ones dropped by the headline regression) deleted, `Written: 0 · Unchanged: 209 · Preserved: 0 · Removed: 23`. Disk now consistent with the production-imports discovery state, no orphan pages served by mkdocs.

  **Fix #1 deferred to Phase 7 — see the new section above.** The architectural decision (Option A explicit manifest vs Option B eager filesystem-walk import vs Option C build-time codegen) is Decision D4, pending. The xfail completeness test will start passing as soon as Phase 7 lands; remove its marker then.

  **What was NOT fixed (rejected as cosmetic or low-priority):**

    - DFS vs BFS docstring wording mismatch in `iter_pipelex_error_subclasses` — sorted output unaffected; deferred.
    - AST scan name-collision false positive risk — no current duplicate-short-name in the tree triggers it; would refactor when a real case arises.
    - `path.relative_to(_PIPELEX_ROOT.parent)` `ValueError` for non-pipelex subclasses — no downstream caller today; not a blocker.
    - Stale doc reference at `docs/under-the-hood/image-handling-in-llm-prompts.md:442` to the deleted shim — reader-facing only, batched into the next docs sweep.

  **Decisions:** D1 + D2 + D3 done; D4 pending (Phase 7).

  **Next action:** Phase 7 — close the discovery-contract gap per Decision D4. Cold-start context for a fresh session is in the Phase 7 section above. After Phase 7 lands and the `xfail` is removed, the in-repo error-handling work for `feature/API-readiness-2` is fully done (Phases 0-7).

- **2026-05-23 — Checkpoint 7 (Phase 7 complete).** Error-class discovery contract closed on `feature/API-readiness-2`. `make agent-check` clean (ruff + pyright + mypy: 0 issues); targeted tests (`tests/unit/pipelex/errors/` + `tests/unit/pipelex/test_pipelex_error_type_uri_uniqueness.py`) all green; production bootstrap (`Pipelex.make()`) verified unchanged — same 203 subclasses loaded, helper not triggered.

  **Decision D4:** Option B' — scoped rglob + force-import in dev/test consumers only. Rejected Option A (explicit manifest) because it re-introduces a hand-maintained list (the very drift target Phase 6 was attacking, just in disguise); rejected Option B (eager filesystem walk at `Pipelex.make()`) because production bootstrap shouldn't filesystem-touch; rejected Option C (build-time codegen) as unnecessary ceremony. Empirical verification underwrites B': every one of the 63 `exceptions.py` / `*_exceptions.py` files imports only base error classes (`PipelexError` / `CogtError` / `CredentialsError` / `ClickException`) — zero SDK pulls. Phase 6's filename convention guarantees the rglob is complete; no allowlist needed.

  **What landed:**

    - `pipelex/errors/error_pages_generator.py` — new `_force_load_all_error_modules()` helper (~17 lines incl. docstring), decorated with `@functools.cache` so the first call walks `pipelex/` for `exceptions.py` + `*_exceptions.py` and `importlib.import_module`s each, subsequent calls are no-ops. `iter_pipelex_error_subclasses()` calls it as its first statement. New `import functools` + `import importlib` + `import pipelex` (for `pipelex.__file__` resolution) added at the top.
    - `tests/unit/pipelex/errors/test_error_class_location_convention.py` — `@pytest.mark.xfail(strict=True, ...)` removed from `test_runtime_walk_discovers_every_ast_classified_subclass`; the test now passes positively. Docstring updated to describe the test as a regression net rather than a future-failure marker. Unused `import pytest` removed.
    - `.claude/rules/python-standards.md` (workspace level) — "Error class location" section gained a "Discovery contract" paragraph documenting the scoped force-import strategy and stating explicitly that adding a new error class is a one-step operation (no manifest to update).
    - `docs/errors/` regenerated via `.venv/bin/pipelex-dev generate-error-pages` — `Written: 35 · Unchanged: 208 · Preserved: 0 · Removed: 0`. 34 new per-class pages (anthropic family, azure_rest, bedrock family, gateway family × 6, google × 2, graph × 2, mistral × 4, openai × 3 incl. VertexAI, portkey × 3, pipe-batch, pipe-search × 2, plus `ConceptSpecError`, `FalCredentialsError`, `PipeBatchFactoryError`, `PipelexBundleSpecBlueprintError`, `PyPdfium2RendererError`) + `docs/errors/index.md` regenerated to list them.

  **Discovery set: before vs. after.**

    - AST scan: 241 PipelexError subclasses on disk (unchanged).
    - Runtime walk after naked `import pipelex`: 19 subclasses (unchanged).
    - Runtime walk after `Pipelex.make()`: 203 subclasses (unchanged — production path untouched).
    - Runtime walk after `iter_pipelex_error_subclasses()`: **241 → 241** (formerly 203, now equals AST set by construction). The 38-class gap is closed.
    - The 4-page gap between the AST set diff and the 34 new files is `KitError` / `KitIndexLoadingError` / `PipelexCLIError` / `ReadinessCheckError` — these were already loaded by the dev CLI command's own bootstrap path before the helper ran, so their pages were already present.

  **CHANGELOG:** `[Unreleased]` — one-line entry under the existing error-handling block noting `docs/errors/` is back to full coverage (34 previously-missing per-class pages restored).

  **Deferred / not done (record-only):**

    - AST-level "no SDK imports in `*_exceptions.py`" check on the convention test. Empirical verification suffices; revisit if the precondition is ever violated.
    - Folding `iter_pipelex_error_subclasses` into a dedicated `pipelex/errors/discovery.py` module. Marginal organizational gain; not worth the diff.

  **Decisions:** D1 + D2 + D3 + D4 all done. The in-repo error-handling work for `feature/API-readiness-2` is now fully complete (Phases 0-7).

  **Next action:** Open the PR for `feature/API-readiness-2` against `dev`. Phase 5 (webhook signing) is the remaining cross-repo track — independent, lands on its own schedule per [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md). Handoff drafts for the API team are at [`wip/api-readiness-2-handoff-drafts.md`](wip/api-readiness-2-handoff-drafts.md) — both human (Slack) and agent-prompt forms ready.

- **2026-05-24 — API-side adapt PR ready on `pipelex-api/feature/Adapt-to-pipelex-update-2`.** Phase A0 ("Adapt to post-#931/#933 pipelex") landed against the editable `_for_api/feature/post-pr933-followups` install. What the API team picked up from this body of work: Phase 6 import-path moves (`EnvVarNotFoundError` from `pipelex.system.exceptions`, two test imports updated; no production touches); Phase 3 `WebhookTarget` reserved-key validator (no-op — the API's single call site was already clean); Phase 1 STRICT-disclosure provenance keying (no-op — the API delegates wholesale to `report.to_problem_document(disclosure_mode=...)`, so the upstream flip flows through untouched; the two `error_domain == INPUT` sites in `api/exception_handlers.py` are log-level switches, not wire-disclosure ones, and remain correct); Phase 2 native `request_id` (the `start` route now reads its request-scoped contextvar and passes `request_id=` to `pipeline_run_setup(...)` — pipelex then carries it onto `JobMetadata.request_id` and every worker `WorkflowLog` record); Phase 7 acronym-casing (`InvalidJSON` title now `Invalid JSON`, one test assertion updated). Also added a **T6 cross-path consistency regression** (`tests/unit/test_webhook_recovery.py`) pinning that the same source `ErrorReport` renders identical classification fields across the sync RFC 7807 response and the webhook `error` payload. Test count: 188 → 193; `make fui && make c && make tp` clean. PR not yet opened pending user review of the commit shape. **Not adapted (deferred upstream):** structured `event=webhook_delivery` / `event=webhook_failure` logging at `pipelex/pipe_run/delivery_executor.py:270` — that's a pipelex change, not an API change. Should land as a separate pipelex PR. The API-team adapt PR documents this as a known follow-up.
