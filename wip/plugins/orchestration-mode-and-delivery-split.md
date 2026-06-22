# Plan — split `PipelexExecutionMode` into `orchestration_mode` (open token) + `DeliveryMode` (closed enum)

**Status:** design **locked** in discussion (2026-06-22); nothing coded yet. Ready-to-execute for a fresh session. This is **Direction A** — the real two-axis split across all three repos (`pipelex` core → `pipelex-temporal` → `pipelex-api`), not the API-edge-only reshape (Direction B, rejected: it relocates the smell to the boundary instead of removing it). It **supersedes** the dual-mode framing in the two follow-on plans `wip/plugins/execute-per-request-execution-mode.md` and `wip/plugins/orchestrator-dispatched-validate.md` — both shipped a working surface on top of the *flat* `PipelexExecutionMode`; this plan removes the flatness those plans worked around (`_async_start_mode`, the `/execute` fire-and-forget 400, the `ApiConfig` f&f field-validator, the `/validate` double-registration). Tracker: `_plugins/TODOS.md`. Parent effort: `wip/plugins/orchestrator-agnostic-runner-and-flavors.md`.

> **START HERE (cold start).** Read this whole doc. The change is conceptual, not big-mechanical-only: today one enum `PipelexExecutionMode {DIRECT, TEMPORAL_BLOCKING, TEMPORAL_FIRE_AND_FORGET, MISTRAL_NATIVE}` conflates **two orthogonal axes** — *which orchestrator runs the pipe* and *whether the caller waits*. We split them: an **open string token** `orchestration_mode` (core owns only `"direct"`; plugins own `"temporal"`, `"mistralai-workflows"`) and a **closed enum** `DeliveryMode {BLOCKING, FIRE_AND_FORGET}` that endpoints set themselves and never receive from a caller. Delivery becomes a parameter to `OrchestratorProtocol.run`, so the two Temporal orchestrators collapse into one and the `/validate` double-registration disappears. Lands core → temporal → api, one repo / branch / commit per phase, clean-context `/code-review` at each checkpoint — same discipline as the rest of the effort.

---

## 1. The ask + locked decisions

**The ask (user):** the API surface for choosing *how* a call to `/execute`, `/start`, `/validate` runs is wrong. `PipelexExecutionMode` carries two things at once — the backend and the wait-semantics — and that conflation forced three separate workarounds (`_async_start_mode`, the `/execute` f&f 400, the `/validate` collapse). Re-cut it into the right enum(s) passed as args.

**Why the conflation is the root cause.** The blocking-vs-fire-and-forget decision is **already expressed by which endpoint you call** — `/execute` and `/validate` are synchronous, `/start` is fire-and-forget. Encoding it a *second* time inside the mode enum is the duplication, and every smell is a workaround for it:

- `_async_start_mode` (`pipeline.py:109-134`) maps `temporal_blocking → temporal_fire_and_forget` because `/start` has to re-derive the delivery axis the enum shouldn't carry.
- `/execute` rejects `temporal_fire_and_forget` with a 400 (`ErrorType.FIRE_AND_FORGET_NOT_SUPPORTED`) — refusing a delivery value the caller should never have been able to express.
- `ApiConfig._reject_fire_and_forget_default` (`api_config.py:54-74`) rejects a *configured* f&f mode — same problem on the config side.
- `TemporalPlugin.register` registers the **same** bundle validator under **both** temporal modes (`temporal_plugin.py:136-138`, decision D of the validate plan) — collapsing the axis because validate doesn't have it either.

Three endpoints, three kludges, one root cause: a wait-semantics dimension the caller/deployment should never receive.

**Locked decisions (do not re-litigate; raise explicitly before deviating):**

- **D-A — Two axes, two types.** Replace `PipelexExecutionMode` with `orchestration_mode` (the backend) + `DeliveryMode` (the wait-semantics). They are orthogonal: orchestration is per-call/config-chosen; delivery is endpoint-intrinsic.
- **D-B — `orchestration_mode` is an OPEN string token, not a closed enum.** Core defines only `"direct"` (its single built-in orchestrator). Each plugin defines and registers its own token *where its orchestrator lives* (`pipelex-temporal` owns `"temporal"`; `pipelex-mistralai-workflows` owns `"mistralai-workflows"`). The registry is keyed by `str`; validation is *"is a mode registered?"* — a lookup miss raises `MissingOrchestratorError` — never *"is it in an enum?"*. **This is the deliberate, justified exception to the repo's StrEnum-everywhere standard:** that standard exists to make the linter scream when a *closed* value is added and a branch forgotten; a plugin-contributed set is genuinely open, exhaustive matching is impossible, and the dict-lookup-or-raise *is* the correct unknown-handling. It is also the only choice faithful to the effort's north star (*the public base names no orchestrator*) — a closed `{DIRECT, TEMPORAL, MISTRAL}` enum would re-introduce the exact core→plugin coupling Phase C removed.
- **D-C — `DeliveryMode {BLOCKING, FIRE_AND_FORGET}` is a closed core StrEnum, endpoint-intrinsic, never on the wire or in config.** Endpoints set it: `/execute` → `BLOCKING`, `/validate` → `BLOCKING`, `/start` → `FIRE_AND_FORGET`. It stays a real StrEnum with exhaustive `match`/`case` (the standard applies — this axis is genuinely closed; a future `STREAMING` would be core's call, never a plugin's).
- **D-D — Delivery is a parameter to dispatch, not a registry key.** `OrchestratorProtocol.run(*, pipe_job, delivery_assignment, delivery: DeliveryMode)`. Each orchestrator honors `delivery` per its nature. This collapses the two Temporal orchestrators into one (`run` branches on `delivery`: `temporal_pipe_run.run(...)` for blocking vs `.start(...)` for f&f) registered **once** under `"temporal"`, and collapses the `/validate` double-registration to a single `"temporal"` validator.
- **D-E — `/start` is HONEST, not degrading.** An orchestrator advertises `supports_fire_and_forget: bool` (`direct`=False, `temporal`=True, `mistralai-workflows`=False). `/start` checks the *resolved* mode's orchestrator and, when it can't do genuine async, returns a 4xx — *"this deployment has no async-capable orchestration; use /execute"* — instead of silently running blocking and acking. (Replaces today's `_async_start_mode` identity-arm degrade.) **Consequence to verify (§8):** on the OSS base (`orchestration_mode = "direct"`) every `/start` now 4xxs — confirm the MTHDS-Protocol/conformance position on `/start` over a non-async backend before committing.
- **D-F — Generic `MissingOrchestratorError` / `MissingBundleValidatorError` message.** *"No orchestrator registered for mode '{mode}'; is its plugin installed?"* — fully decoupled. Drop the per-mode `match`-on-enum install hints (`requires_pipelex_temporal` etc.). Core no longer names `temporal`/`mistral` in its error text.
- **D-G — Rename the Mistral token `"mistral_native"` → `"mistralai-workflows"`** for consistency with the package name (`pipelex-mistralai-workflows`). Mistral is a deferred/secondary plugin; this is just the token string + any doc reference.
- **D-H — Rename the wire field + config key `execution_mode` → `orchestration_mode`** (and `allow_request_execution_mode_override` → `allow_request_orchestration_mode_override`). Breaking wire/config change — fine per the workspace "no backward compatibility" principle; note in changelogs.

---

## 2. Current state (anchors verified 2026-06-22)

**Core (`_plugins/pipelex/`):**

- `runtime_bridge/execution_mode.py` — `PipelexExecutionMode(StrEnum)`: the 4 members + three properties to delete: `requires_pipelex_temporal` (`30`), `requires_mistral_workflows_extra` (`38`), `is_fire_and_forget` (`46`).
- `plugins/orchestrator_registry.py` — `OrchestratorProtocol.run(self, *, pipe_job, delivery_assignment) -> PipelexPipeRunOutput` (`21`); `OrchestratorRegistry(orchestrators: dict[PipelexExecutionMode, OrchestratorProtocol])` with `get_optional(*, mode)` / `has(*, mode)` / `modes` (`24-42`).
- `plugins/bundle_validator_registry.py` — the `/validate` twin (`BundleValidatorProtocol`, `BundleValidatorRegistry`), same `dict[PipelexExecutionMode, …]` keying (per the validate plan's V0 as-built).
- `plugins/registrar.py` — stores `orchestrators` / `bundle_validators` typed `dict[PipelexExecutionMode, …]` (`111-112`) + the `_*_sources` mirrors (`122-123`); `add_orchestrator(*, mode, …)` (`167`) and `add_bundle_validator(*, mode, …)` (`179`).
- `runtime_bridge/exceptions.py` — `MissingOrchestratorError._build_message` (`27-40`) and `MissingBundleValidatorError._build_message` (`61-74`) both `match` on enum members for per-mode install hints (→ generic, D-F).
- `runtime_bridge/direct_orchestrator.py` — `DirectOrchestrator.run(*, pipe_job, delivery_assignment)` (`29`), returns `serialize_completed_output(pipe_output, workflow_id=None)` (`46-49`). Add `supports_fire_and_forget = False` + the `delivery` param (ignored — in-process always blocks).
- `plugins/direct/direct_plugin.py` — `register` calls `add_orchestrator(mode=DIRECT, …)` + `add_bundle_validator(mode=DIRECT, …)` (`20-22`). `DIRECT` becomes the `"direct"` string constant.
- `runtime_bridge/bridge.py` — `run_pipe_via_bridge` (`51`): `is_direct = input_payload.execution_mode is PipelexExecutionMode.DIRECT` (`85`); dispatch `get_orchestrator_registry().get_optional(mode=input_payload.execution_mode)` → `orchestrator.run(pipe_job, delivery_assignment)` (`92-95`); `_validate_input` checks `execution_mode is TEMPORAL_FIRE_AND_FORGET` for the delivery-target requirement (`164`). This is the **Tier-3 bridge** for *other* host runtimes (Mistral Workflows, raw Temporal) — pipelex-api's routes do **not** go through it (they hit the registry directly), but it must split consistently and pass `delivery`.
- `runtime_bridge/payloads.py` — `PipelexPipeRunInput.execution_mode: PipelexExecutionMode = DIRECT` (`30`). Splits into `orchestration_mode: str = "direct"` + `delivery: DeliveryMode = BLOCKING`. `PipelexPipeRunOutput` (`34-52`) already carries `workflow_id` / `is_completed` and needs no change.

**Temporal (`pipelex-temporal/pipelex_temporal/`):**

- `temporal_orchestrators.py` — `TemporalBlockingOrchestrator.run` calls `temporal_pipe_run.run(...)` (await completion, `58`) and reports `make_workflow_id(...)` (`69`); `TemporalFireAndForgetOrchestrator.run` calls `temporal_pipe_run.start(...)` (return immediately, `91`) and builds an `is_completed=False` output (`96-103`). **The only difference is `run` vs `start`** → one `TemporalOrchestrator` whose `run` branches on `delivery`. Both already guard the `pipelex[temporal]` extra via `_require_temporal_extra` (`32-40`).
- `temporal_plugin.py` — `register` (`127`): two `add_orchestrator` calls under the two temporal modes (`128-129`), two `add_bundle_validator` calls under both temporal modes (`136-138`), the F3 mapper (`145`, unchanged), and the `boot_orchestrator == self.name` slot-claims (`152-157`, unchanged — `boot_orchestrator` is the *separate* hub-slot gate, orthogonal to the orchestration token even though both read `"temporal"`).
- `temporal_bundle_validator.py` — `TemporalBundleValidator` (validate is inherently blocking; register once under `"temporal"`).

**API (`pipelex-api/api/`):**

- `api_config.py` — `ApiConfig.execution_mode: PipelexExecutionMode` + `allow_request_execution_mode_override: bool` (`51-52`); the `_reject_fire_and_forget_default` field-validator to **delete** (`54-74`); `resolve_execution_mode(requested, *, config)` (`103-121`) → rename `resolve_orchestration_mode`, logic unchanged (string compare; 403 on forbidden override); `api.toml` ships `execution_mode = "direct"`.
- `schemas/models.py` — `PipelineApiExtras.execution_mode: PipelexExecutionMode | None` (`153`); `PipelexApiExecuteRequest.execution_mode` (`204`); `_EXECUTION_MODE_DESCRIPTION` (`110-115`, lists the four enum values → open-token wording). Rename field → `orchestration_mode`.
- `routes/pipelex/pipeline.py` — `_async_start_mode` (`109-134`, **delete**); `ApiRunner.execute` resolves + rejects f&f (`208-214`, drop the rejection) and injects `_OrchestratorPipeRun` (`222`); `ApiRunner.start` calls `_async_start_mode(resolve_…(…))` (`283`, → resolve + capability-check); `_OrchestratorPipeRun` / `_pipe_output_from_run_output` (`73-153`, thread `delivery`); `validate_verdict` (`343-390`, rename the mode param). Routes `execute` (`530`) / `start` (`572`) thread the renamed extra.
- `error_types.py` — `EXECUTION_MODE_OVERRIDE_FORBIDDEN` (`23`, rename) and `FIRE_AND_FORGET_NOT_SUPPORTED` (`32`, **delete**); add the honest-`/start` rejection type (D-E).
- `routes/pipelex/validate.py` — threads `execution_mode` into `validate_verdict` (rename to `orchestration_mode`).
- The committed OpenAPI artifact (`docs/openapi/pipelex-api.openapi.yaml`) re-exports via `make openapi-export`; drift-gated by `make openapi-check`.

> **Mechanical-usage inventory** (every stray `PipelexExecutionMode` / `execution_mode` / mode-literal site across the three repos) is being swept and is appended in §9 — run that grep before declaring a phase done.

---

## 3. The design (locked)

### 3.1 Core types (`_plugins/pipelex/runtime_bridge/`)

- **`orchestration_mode.py`** (replaces `execution_mode.py`):
  - `OrchestrationMode: TypeAlias = str` — a *semantic* alias documenting intent at registry/protocol signatures (`dict[OrchestrationMode, …]`), assignment-compatible with plain `str` so plugins pass raw strings with no casts. (Chose the alias over `NewType` deliberately: a `NewType` forces `OrchestrationMode("temporal")` casts at every plugin boundary for zero validation benefit — the registry is the validator. See §8.)
  - `DIRECT_ORCHESTRATION_MODE: Final[str] = "direct"` — core's one built-in token, referenced by core code instead of the literal.
- **`delivery_mode.py`** — `class DeliveryMode(StrEnum): BLOCKING = "blocking"; FIRE_AND_FORGET = "fire_and_forget"`. Closed; exhaustive `match`/`case`; no default arm.
- **`OrchestratorProtocol`** (`plugins/orchestrator_registry.py`):
  - `async def run(self, *, pipe_job, delivery_assignment, delivery: DeliveryMode) -> PipelexPipeRunOutput`
  - `supports_fire_and_forget: bool` — capability the runner reads *before* dispatch (D-E). A `@property` or a plain class attribute; the protocol declares it as a read-only attribute.
- **`OrchestratorRegistry`** / **`BundleValidatorRegistry`** — re-key `dict[OrchestrationMode, …]` (i.e. `dict[str, …]`); `get_optional(*, mode: OrchestrationMode)` / `has`. `BundleValidatorProtocol.validate_bundles` stays blocking — pass no `delivery` (or `DeliveryMode.BLOCKING` if uniformity reads better; validate has no async variant).
- **`PluginRegistrar`** — `orchestrators` / `bundle_validators` + `_*_sources` become `dict[str, …]`; `add_orchestrator(*, mode: OrchestrationMode, …)` / `add_bundle_validator(*, mode: OrchestrationMode, …)`. The `_add` dup-guard is unchanged (works on any hashable key).
- **`Missing*Error`** — drop the `match`; generic message keyed on the string (D-F). Optionally keep a one-line special case for `"direct"` (*"DIRECT is core; this indicates a boot/discovery problem"*) via a plain `if mode == DIRECT_ORCHESTRATION_MODE:` — now a string compare, not an enum, so it does not offend the no-`==`-on-enums rule.
- **`payloads.py`** — `PipelexPipeRunInput`: `execution_mode` → `orchestration_mode: str = DIRECT_ORCHESTRATION_MODE` + `delivery: DeliveryMode = DeliveryMode.BLOCKING`.
- **`bridge.py`** — `is_direct = input_payload.orchestration_mode == DIRECT_ORCHESTRATION_MODE`; pass `delivery=input_payload.delivery` into `orchestrator.run(...)`; `_validate_input` checks `input_payload.delivery is DeliveryMode.FIRE_AND_FORGET` for the delivery-target requirement.
- **`DirectOrchestrator`** — `supports_fire_and_forget = False`; `run(*, pipe_job, delivery_assignment, delivery)` accepts `delivery` for protocol uniformity and ignores it (in-process always blocks; `/start` never reaches it because the capability check rejects first — the bridge/Tier-3 path that *could* pass f&f to direct simply blocks, see §8).

### 3.2 Temporal plugin (`pipelex-temporal`)

- **One `TemporalOrchestrator`** (`temporal_orchestrators.py`) — `supports_fire_and_forget = True`; `run` branches:
  - `DeliveryMode.BLOCKING` → `temporal_pipe_run.run(...)` then `make_workflow_id(...)` (today's `TemporalBlockingOrchestrator` body).
  - `DeliveryMode.FIRE_AND_FORGET` → `temporal_pipe_run.start(...)` → `is_completed=False` output (today's `TemporalFireAndForgetOrchestrator` body).
  - Keep the `_require_temporal_extra` guard and the `WorkflowExecutionError` wrapping in both arms.
- **`TEMPORAL_ORCHESTRATION_MODE: Final = "temporal"`** defined in `pipelex-temporal` (the token lives with the orchestrator). Distinct constant from the plugin's `name` / `boot_orchestrator` value even though both equal `"temporal"` — they are different concepts (registry key vs hub-slot gate).
- **Register once** — `add_orchestrator(mode=TEMPORAL_ORCHESTRATION_MODE, orchestrator=TemporalOrchestrator())`; `add_bundle_validator(mode=TEMPORAL_ORCHESTRATION_MODE, validator=TemporalBundleValidator())`. The two-mode duplication is gone. F3 mapper + boot-slot claims unchanged.

### 3.3 API (`pipelex-api`)

- **`ApiConfig`** — `orchestration_mode: str` + `allow_request_orchestration_mode_override: bool`; **delete** `_reject_fire_and_forget_default` (no f&f token can be configured anymore). `resolve_orchestration_mode(requested: str | None, *, config) -> str` — same default/override/403 logic. `api.toml`: `orchestration_mode = "direct"`, `allow_request_orchestration_mode_override = false`.
- **Wire** (`schemas/models.py`) — `PipelineApiExtras.orchestration_mode: str | None`; `PipelexApiExecuteRequest.orchestration_mode`; description reworded for the open token (*"e.g. `direct`, `temporal`; plugin-provided modes also accepted; an unregistered mode is refused at dispatch"*; drop the `temporal_fire_and_forget` value — no such token exists).
- **`/execute`** — resolve `orchestration_mode`; **no f&f rejection** (delete the `is_fire_and_forget` branch + `FIRE_AND_FORGET_NOT_SUPPORTED`); dispatch via `_OrchestratorPipeRun(orchestrator, delivery=DeliveryMode.BLOCKING)`.
- **`/start`** — resolve `orchestration_mode`; get orchestrator; **capability check (D-E):** `if not orchestrator.supports_fire_and_forget: raise_<4xx>(…, error_type=START_REQUIRES_ASYNC_ORCHESTRATION)`; dispatch with `delivery=DeliveryMode.FIRE_AND_FORGET`. **Delete `_async_start_mode`.**
- **`/validate`** — `validate_verdict(*, …, requested_orchestration_mode)`; resolve + dispatch through the validator registry (blocking). Verdict-as-value unchanged.
- **`error_types.py`** — rename `EXECUTION_MODE_OVERRIDE_FORBIDDEN` → `ORCHESTRATION_MODE_OVERRIDE_FORBIDDEN`; **delete** `FIRE_AND_FORGET_NOT_SUPPORTED`; **add** `START_REQUIRES_ASYNC_ORCHESTRATION` (D-E). Status code: §8.
- **OpenAPI** — `make openapi-export`; the request schemas now advertise `orchestration_mode`.

---

## 4. Phased implementation + checkpoints

Each phase: own repo, own branch, own commit, gates green, clean-context `/code-review` (hand the reviewer only the diff/SHA, never this plan). Ordering is load-bearing — core must land before its consumers.

### Phase 1 — core split (`pipelex`, `_plugins/`)

Add `OrchestrationMode` (open `str` alias + `DIRECT_ORCHESTRATION_MODE`) and `DeliveryMode`; re-key both registries + the registrar stores on `str`; add `delivery` + `supports_fire_and_forget` to `OrchestratorProtocol`; update `DirectOrchestrator`; generic `Missing*Error`; split `PipelexPipeRunInput`; update `bridge.py` dispatch + `_validate_input`; delete `PipelexExecutionMode` and its three properties. Sweep §9. Gates: `make agent-check`, `make tb` (boot builds the re-keyed registries), `make agent-test`.

> **🛑 Checkpoint 1** — core green; registries keyed by string; boot still builds them; no orchestrator named in core error text. Capture an as-built (final type names/locations, the `OrchestrationMode` alias decision, the `supports_fire_and_forget` shape). Clean-context `/code-review` on the core diff.

### Phase 2 — Temporal collapse (`pipelex-temporal`) · **MAJOR**

Collapse the two orchestrators into `TemporalOrchestrator` (delivery-branch + `supports_fire_and_forget=True`); define `TEMPORAL_ORCHESTRATION_MODE`; register orchestrator + validator **once** under `"temporal"`; F3 mapper + boot-slot claims unchanged. Update the in-memory integration tests to exercise both delivery values through the single orchestrator. Gates: `make agent-check`, `make agent-test` against the Phase 1 core.

> **🛑 Checkpoint 2** — the seam has a real consumer through the new shape: one `"temporal"` arm serving both deliveries; the base still has no idea Temporal exists. As-built + clean-context `/code-review` on both diffs.

### Phase 3 — API (`pipelex-api`) · **THE gate**

`ApiConfig` rename + drop the f&f validator + `resolve_orchestration_mode`; wire-model rename + open-token description; routes — delete `_async_start_mode`, `/execute` drop f&f-reject (delivery=BLOCKING), `/start` honest capability-reject (delivery=FIRE_AND_FORGET), `/validate` param rename; `error_types` changes; `make openapi-export`; docs + changelog. Sweep §9. Gates: `make agent-check`, `make agent-test`, `make openapi-check`.

> **🛑 Checkpoint 3** — `/execute`, `/start`, `/validate` all take `orchestration_mode`; delivery is endpoint-set; `/start` honestly rejects non-async modes; all the conflation workarounds are gone; OpenAPI in sync. **Verify the `/start`-honesty conformance question (§8) here.** As-built + clean-context `/code-review` on the API diff.

### Phase 4 — bookkeeping (deferred Mistral rename + trackers)

Rename the Mistral token `"mistral_native"` → `"mistralai-workflows"` when/where it exists (deferred plugin — token string + doc refs only). Update `_plugins/TODOS.md` (Phase C as-built + follow-on section), mark the two superseded sibling plans, `pipelex-api` `CHANGELOG.md`, and `docs/specs/` / `conformance/` if any heading or test asserts mode values (run `make check-spec-links`).

---

## 5. Cross-repo state, pins, gates

- **Verify state FIRST (cold start).** Before cutting any branch, run the effort's orientation ritual — [`wip/plugins/resume-and-verify-state.md`](resume-and-verify-state.md) — and confirm each repo's working tree is clean and sits on the tip `_plugins/TODOS.md` "Current branches" names. This plan was written against those tips; if they have moved, re-derive the §2 / §9 anchors against the new tip rather than trusting the line numbers.
- **Branches:** cut fresh per phase off the verified current tips (`_plugins` core worktree; `pipelex-temporal`; `pipelex-api` off the `feature/Execute-per-request-mode` tip — this work stacks on the landed follow-ons it supersedes).
- **Pins:** `pipelex-api` and `pipelex-temporal` both pin `pipelex = { path = "../_plugins", editable = true }`, so a core edit is live in both immediately. `pipelex-api` does **not** depend on `pipelex-temporal` (Phase C dropped it) — test the API split with a stub orchestrator/validator registered for a non-`direct` test token; never import `temporalio` in `pipelex-api`. For a `pipelex-api` PR, the editable pin breaks CI — pin core to a git+https SHA + relock, flip back at release (the PR #27 `c60be1f` gotcha).
- **Gates:** core → `make agent-check` / `make tb` / `make agent-test`; temporal + api → `make agent-check` / `make agent-test`; api also `make openapi-check`; conformance → `make check-spec-links` if a spec heading is touched.

---

## 6. Spec / conformance

- **No verdict/result wire contract changes** — `/validate`'s 200-always + `is_valid` discriminant + `validation_errors[]`, and the `/execute` / `/start` result shapes, are all backend-independent and untouched. The only wire change is the **request** field rename `execution_mode → orchestration_mode` (a pipelex-api extension field, not protocol-core).
- **The one real conformance question is D-E's `/start` honesty** (§8): if the MTHDS-Protocol conformance suite asserts `/start` returns a `202` on the reference implementation's default (direct) config, honest-reject breaks it. Resolve before Phase 3 lands.
- If any `docs/specs/` heading documents the mode values or the per-endpoint delivery behavior, update it + its `> Verified by:` link and run `make check-spec-links`.

---

## 7. Testing

- **Core (Phase 1):** registry/registrar keyed by string (register + get + dup under arbitrary tokens incl. a synthetic `"acme"`); `MissingOrchestratorError` generic message for an unregistered token + the `"direct"` boot-bug special case; `DeliveryMode` exhaustive; `OrchestratorProtocol` round-trip with `delivery` + `supports_fire_and_forget`; `DirectOrchestrator.supports_fire_and_forget is False`; `PipelexPipeRunInput` defaults (`orchestration_mode="direct"`, `delivery=BLOCKING`); bridge `_validate_input` requires a delivery target iff `delivery is FIRE_AND_FORGET`. `make tb` green (boot builds the re-keyed registries).
- **Temporal (Phase 2):** in-memory-Temporal integration — the single `TemporalOrchestrator` returns a completed output for `delivery=BLOCKING` and an `is_completed=False` + `workflow_id` for `delivery=FIRE_AND_FORGET`; one registration serves both; validator registered once.
- **API (Phase 3, no temporal import):** `/execute` dispatches blocking with no f&f branch; `/start` honestly 4xxs when the resolved mode's stub orchestrator has `supports_fire_and_forget=False`, and acks when it's `True`; override policy on string tokens (default honored, different+allowed honored, different+forbidden → 403); an unregistered requested token → `MissingOrchestratorError` at dispatch; `/validate` unchanged verdict mapping; OpenAPI advertises `orchestration_mode`.

---

## 8. Open sub-decisions / risks for the implementing session

- **[RISK — resolve first] `/start` honesty vs MTHDS-Protocol conformance.** D-E makes `/start` 4xx on a direct-only deployment (the OSS default). Confirm the protocol/conformance suite does not require `/start` to return `202` on a non-async backend. If it does: either the conformance env must configure a `temporal` backend, or `/start` keeps a documented degrade for `direct` only — but that re-opens the axis we just closed, so prefer fixing the conformance env. **Verify before Phase 3.**
- **Honest-`/start` status code.** `400` (symmetric with the deleted `FIRE_AND_FORGET_NOT_SUPPORTED`), `409 Conflict` (request conflicts with deployment capability), or `422`. Recommend `400` with a crisp message; flag `409` as the more semantically precise alternative.
- **`OrchestrationMode` shape.** Recommended: `TypeAlias = str` + a `Final` `"direct"` constant (open, cast-free for plugins). Alternative: a `NewType` (stronger signatures, but forces casts at every plugin boundary for no validation gain since the registry validates). Decide in Phase 1; record in the as-built.
- **`supports_fire_and_forget` location.** On the orchestrator (recommended — it owns its capability) vs registry-level metadata. Keep it on the protocol unless a second consumer needs it elsewhere.
- **Unknown requested token validation timing.** Let dispatch raise `MissingOrchestratorError` (recommended — single validation point, keeps `resolve_orchestration_mode` decoupled from the hub) vs an early `get_orchestrator_registry().has(...)` check in resolve (earlier 4xx but couples config to the hub). Default: dispatch-time.
- **Tier-3 bridge + incompatible (mode, delivery).** A raw bridge caller could pass `delivery=FIRE_AND_FORGET` to `direct`. The capability enforcement lives at the `/start` *endpoint*, not the bridge; `DirectOrchestrator` simply blocks regardless (in-process has no other option). Confirm that's acceptable for the bridge surface, or add a bridge-level capability guard if a Tier-3 consumer needs the same honesty.
- **`boot_orchestrator` vs the `"temporal"` token.** Both strings equal `"temporal"` but are distinct concepts (hub-slot boot gate vs orchestrator-registry key). Keep separate named constants; do not unify them just because the values coincide today.

---

## 9. Mechanical-usage inventory

> Swept across `_plugins/`, `pipelex-temporal/`, `pipelex-api/`. Actionable per-repo, keyed to the §3 decisions. **Re-run the grep at each phase boundary — do not trust a stale list:** `grep -rn 'PipelexExecutionMode\|execution_mode\|is_fire_and_forget\|requires_pipelex_temporal\|requires_mistral_workflows\|temporal_blocking\|temporal_fire_and_forget\|mistral_native' <repo>`.

### Core (`_plugins/pipelex/`)

**Source — split / rename / delete:**
- `runtime_bridge/execution_mode.py` → **replace** with `orchestration_mode.py` (`OrchestrationMode` alias + `DIRECT_ORCHESTRATION_MODE`) and `delivery_mode.py` (`DeliveryMode`). Delete the enum + its 3 properties.
- `runtime_bridge/payloads.py:16,30` — `PipelexPipeRunInput.execution_mode` → `orchestration_mode: str` + `delivery: DeliveryMode`.
- `runtime_bridge/bridge.py:36,85,92,94,164` — import; `is_direct` string-compare; registry dispatch; `MissingOrchestratorError`; `_validate_input` f&f-target check → `delivery is FIRE_AND_FORGET`; pass `delivery` to `run`.
- `runtime_bridge/exceptions.py:2,22-40,56-74` — `Missing{Orchestrator,BundleValidator}Error` — drop the per-mode `match`; generic message (D-F).
- `plugins/orchestrator_registry.py:3,21,31-42` — protocol `run(*, …, delivery)` + `supports_fire_and_forget`; registry `dict[str, …]`.
- `plugins/bundle_validator_registry.py:33,77-89` — registry `dict[str, …]` (validate stays blocking).
- `plugins/registrar.py:19,111-123,167-189` — `orchestrators`/`bundle_validators` + `_*_sources` → `dict[str, …]`; `add_orchestrator`/`add_bundle_validator` mode param typed `OrchestrationMode`.
- `runtime_bridge/direct_orchestrator.py:29,46-49` — `supports_fire_and_forget = False`; accept+ignore `delivery`.
- `plugins/direct/direct_plugin.py:5,20-22` — register under `DIRECT_ORCHESTRATION_MODE`.

**Tests — update/retarget:** `tests/unit/pipelex/runtime_bridge/test_execution_mode.py` (→ `test_orchestration_mode.py` + new `test_delivery_mode.py`; the property tests die with the properties), `test_input_models.py`, `test_dispatch.py`, `test_validation.py` (the f&f-target requirement now keys on `delivery`), `test_orchestrator_dispatch.py`, `test_direct_router_scoping.py`, `test_missing_bundle_validator_error.py` (parametrized over per-mode install hints → assert the generic message + the `"direct"` boot-bug case), `test_exceptions_disclosure.py`, `test_trace_context_contract.py`, `tests/unit/pipelex/plugins/test_bundle_validator_registry.py`, `test_plugin_discovery.py`, `tests/integration/pipelex/runtime_bridge/test_bridge_direct.py`.

**Docs:** the `execution_mode.py` module docstring (moves to the new modules); `TODOS.md` two-axis narrative (the `boot_orchestrator` vs `execution_mode` table, the f&f-derivation notes) — update at Phase 4 bookkeeping.

### Temporal (`pipelex-temporal/pipelex_temporal/`)

**Source:** `temporal_plugin.py:29,128-138` — collapse the two `add_orchestrator` + two `add_bundle_validator` calls to one each under `TEMPORAL_ORCHESTRATION_MODE`; `temporal_orchestrators.py` — merge `TemporalBlocking`/`TemporalFireAndForget` into one `TemporalOrchestrator` (`run` branches on `delivery`, `supports_fire_and_forget=True`); `temporal_bundle_validator.py` — unchanged impl, registered once; `temporal_cli.py` — docstring mention of `execution_mode`. `boot_orchestrator == self.name` gate (`:152`) is **unchanged** (separate concept — leave it).

**Tests:** `tests/unit/pipelex_temporal/test_bridge_temporal_dispatch.py` (both modes → one orchestrator + `delivery`), `test_trace_context_temporal.py`, `test_temporal_blocking_workflow_id.py`; the in-memory validator integration test (single registration).

### API (`pipelex-api/api/`)

**Source:** `api_config.py:27,51-74,103-122` — field rename + **delete** `_reject_fire_and_forget_default` + `.is_fire_and_forget` use; `resolve_execution_mode` → `resolve_orchestration_mode`. `schemas/models.py:19,110-115,153,204` — `PipelineApiExtras`/`PipelexApiExecuteRequest` field rename + open-token description. `routes/pipelex/pipeline.py:22,109-135,183,208,247,283,349,375` — **delete** `_async_start_mode`; `/execute` drop f&f-reject; `/start` capability-reject; `_OrchestratorPipeRun`/`_pipe_output_from_run_output` thread `delivery`; `validate_verdict` param rename. `routes/pipelex/validate.py:8,67-75,188` — `ValidateRequest.execution_mode` → `orchestration_mode` (confirm the model's home — route vs `models.py`). `error_types.py:13,23,32` — rename `EXECUTION_MODE_OVERRIDE_FORBIDDEN`; delete `FIRE_AND_FORGET_NOT_SUPPORTED`; add `START_REQUIRES_ASYNC_ORCHESTRATION`.

**Config:** `api/api.toml:15,19` — `execution_mode = "direct"` → `orchestration_mode = "direct"`; `allow_request_execution_mode_override` → `allow_request_orchestration_mode_override`; update the file comments.

**Tests:** `tests/unit/test_api_config.py` (drop the f&f-rejection test; rename), `test_execute_dispatch.py` (drop the 400-f&f case), `test_start_dispatch.py` (was "derives f&f variant" → now "honest-reject when not async-capable" + ack when capable), `test_validate_dispatch.py`, `test_protocol_conformance.py`.

**Docs + OpenAPI:** `api_config.py` / `api.toml` / `models.py` docstrings; `make openapi-export` regenerates `docs/openapi/pipelex-api.openapi.yaml`; `CHANGELOG.md`.

### Cross-cutting

- **`boot_orchestrator` is untouched** — it is the separate hub-slot boot gate (`registrar.config.plugins.boot_orchestrator`, the `temporal_plugin.py:152` claim guard), orthogonal to the orchestration token. Do not fold the two together even though both read `"temporal"`.
- **Fire-and-forget delivery-target validation** (`bridge.py:164-170`) moves from `execution_mode is TEMPORAL_FIRE_AND_FORGET` to `delivery is DeliveryMode.FIRE_AND_FORGET` — the only place that check should live post-split (the API config f&f-rejection and the `/execute` f&f-400 both delete).
