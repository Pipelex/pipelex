# BYOK per-org inference profiles — implementation tracker

Implements [`wip/byok-api/design.md`](wip/byok-api/design.md) (v1 = **Foundation §5 + Binding B §6**; Binding A deferred to Phase 4 per §14). Core branch: `feature/BYOK-per-request` in this worktree (`_byok`). This file is the live tracker: tick boxes as work lands, and update the **Cold-start state** section at every checkpoint so a fresh session can resume with zero re-exploration.

## Checkpoint protocol (mandatory — the agent MUST stop at each CHECKPOINT)

At every CHECKPOINT block below, before touching the next phase:

1. **Verify** — run the repo's gates listed in the checkpoint (e.g. `make agent-check` + `make agent-test`); fix failures first.
2. **Commit** — one commit for the checkpoint's work in that repo (changelog entry under `[Unreleased]`, no version-heading minting).
3. **Update this file** — tick boxes, and refresh **Cold-start state** with: decisions taken, surprises/deviations from plan, per-repo branch + commit SHA, and what's next. Update the BYOK memory file too.
4. **Fan out `/code-review`** — spawn a **Sonnet-5** sub-agent with **no inherited context**: hand it ONLY a pointer to the changes (repo path + commit SHA or an exact `git diff <base>..HEAD` command, or "unstaged working tree in <repo>"), never the plan, the design rationale, or your own conclusions. It runs the `/code-review` skill and reports findings. Triage: fix real defects; capture design-tradeoff findings as deferred-items docs under `wip/byok-api/` instead of reflexively applying them. We want clean solid software, not over-engineering.
5. **Stop for sign-off** where the checkpoint is marked ⚠️ — those decisions belong to the user.

## Decisions & v1 stances (design §15 open questions + new decisions from exploration)

- **Q1 version pinning:** v1 = no immutable versioned profile items. The `fingerprint` (SHA-256 over canonical overlay + `credentials_version`) rides the ref on every run — that gives audit-grade "which config produced this run". Placement makes mid-run consistency automatic (fleet restart is deliberate). Revisit for Binding A.
- **Q2 org default vs explicit-only:** storage + CRUD support the default binding from Phase 1 (design §5.5 requires the resolution order anyway). Runner-side resolution (Phase 2) honors explicit header → org default → server default, with an `allow_request_inference_profile`-style config gate so ops can freeze explicit selection. ⚠️ confirm at Checkpoint 5 whether org-default resolution is enabled at launch or explicit-header-only.
- **Q3 fleet economics:** v1 = one small always-on ECS service per placement-bound profile (dev-sized: 1 instance / 1 task, mirroring worker tfvars). Scale-to-zero deferred.
- **Q4 queue-wait policy:** v1 = CloudWatch alarms (fleet running-vs-desired, workflow schedule-to-start latency if observable) + runbook entry; no automatic run-fail timeout. Ticketed as a deferred item.
- **Q5 deck-only scoped view API-side:** deferred. `/v1/models` and deck-dependent validation see the server deck in v1.
- **Q6 where the hosted adapter lives:** ⚠️ **needs sign-off before Phase 2b.** Recommendation: `pipelex-api-hosted` grows a small Python package (ASGI wrap of `api.main:fastapi_app` + a `pipelex.plugins` entry point), changing that repo from config-only to config+thin-adapter. Alternative: a separate private plugin package. Exploration confirmed the OSS app exposes exactly one clean wrap point (`main.py:188`) and the Dockerfile CMD is the single entrypoint knob.
- **Q7 custom model-spec validation:** v1 = schema-level validation at platform save time (pydantic shapes in `pipelex_shared` mirroring the blueprint fields). Runner-side deep deck-build validation deferred + ticketed.
- **A1 hosted seam (new):** OSS `pipelex-api` stays untouched. `OrchestratorProtocol.run` has no queue param, so Binding B lands as: hosted ASGI middleware reads headers → resolves profile meta (fail-fast, fail-closed) → binds a request-scoped ContextVar (legal under R1: single process, payload stays the durable truth) → a BYOK-aware orchestrator registered under the `temporal` token stamps `pipe_job.pipe_run_params.inference_profile_ref` via `model_copy(update=...)` at submission and passes `task_queue=profile.task_queue` into `make_temporal_pipe_run`.
- **A2 pipelex-temporal seam (new):** give `TemporalOrchestrator` a constructor-injected optional `task_queue_resolver: Callable[[PipeJob], str | None]` (or equivalent) so the hosted plugin composes rather than forks. Decide exact shape in Phase 2a.
- **A3 org queue naming/validation (new):** org queues must satisfy `validate_task_queue_known` (`config_temporal.py`). v1: the worker boot-from-profile step materializes a temporal config overlay declaring the queue + `queue_options`; API-side, the hosted adapter must make the queue known to submission-side validation (same overlay mechanism or a relaxed prefix rule — decide in 2a/2b).
- **A4 identity propagation (corrected by exploration):** the API-Gateway authorizer **already injects `X-Org-Id`** (`overwrite:header.X-Org-Id = $context.authorizer.org_id`) on every ALB integration, for both JWT and API-key auth. Remaining work is only: platform→runner forward allowlist + hand-built header dicts, and the runner actually reading the header (hosted overlay, Phase 2).
- **A5 default-binding storage (new):** org default pointer = scalar `default_inference_profile_id` attribute on the `ORG#{org_id}/PROFILE` row (matches existing scalar-flag convention on Organization; no pointer-item precedent exists).
- **A6 credentials never in payloads/logs/responses:** enforced by construction — ciphertext-only in DDB, decrypt only in org-fleet boot (v1); `*Public` schemas exclude credential fields; redaction posture tested.

## Repo state hazards (checked 2026-07-03)

- `pipelex-temporal` — checkout has **uncommitted work on `refactor/Finish-plugin-extraction`** (plugins track). Do NOT touch that checkout's working tree; Phase 2a work must branch from its mainline once the plugins track lands, or use a separate git worktree.
- `pipelex-worker` — on `feature/Plugins`, pins `pipelex`/`pipelex-temporal`/`pipelex-transport` by git SHA in `[tool.uv.sources]`. Phase 2c branches from its mainline; coordinate pin bumps with the plugins track.
- `pipelex-api-hosted` — on `refactor/Sdk-mthds-vs-pipelex`. Phase 2b branches from its mainline.
- `pipelex-api-infra` and `pipelex-platform` — were hundreds/dozens of commits stale locally; **fast-forwarded 2026-07-03** to `main@9caf63a` / `dev@08f22bf`. Re-fetch before each phase that touches them.
- `infra-python-tools` — on `dev`, clean.

---

## Phase 1 — Foundation

### 1a. Core: the ref in the run payload (`_byok`, branch `feature/BYOK-per-request`)

The only `pipelex/` change for v1 (design §5.4). Neutral names (`owner_id`, not org), no store, no resolver.

- [x] `InferenceProfileRef` model — new `pipelex/pipe_run/inference_profile_ref.py`: `owner_id`/`profile_id`/`fingerprint` (all `min_length=1`); `ConfigDict(frozen=True, extra="forbid")`; `ref_str` property for logs.
- [x] `PipeRunParams.inference_profile_ref: InferenceProfileRef | None = Field(default=None, frozen=True)`.
- [x] Mirror into `CogtRunParams` (optional with default) and thread it in the `cogt_run_params` property so the ref reaches every inference assignment.
- [x] Optional keyword `inference_profile_ref=None` on `PipeRunParamsFactory.make_run_params`.
- [x] Update the `cogt_run_params.py` module docstring.
- [x] Tests — new `tests/unit/pipelex/pipe_run/test_inference_profile_ref.py` (one class per module rule; covers default-None, old-writer payload validation, carrier derivation, JSON round-trips, frozen-field mutation rejection, `model_copy(update=...)` stamping, copy preservation, factory pass-through, forbid-extras, empty-field rejection).
- [x] Docs: `docs/under-the-hood/pipe-routing-and-execution.md` PipeJob table + `CHANGELOG.md` `[Unreleased]` entry.

**CHECKPOINT 1 — DONE (2026-07-03).** Gates green (`make agent-check`, full `make agent-test`). Committed as `4921a031d` on `feature/BYOK-per-request`. Fresh-context Sonnet `/code-review` fan-out ran on the commit: one low-severity doc-consistency finding (cogt_run_params docstring "single writer" claim vs the orchestrator-seam stamp path) — fixed and amended in; everything else survived scrutiny explicitly (wire compat, frozen contracts, propagation, tests, changelog). Q6 recommendation reported to user: hosted adapter as a thin Python package inside `pipelex-api-hosted`.

### 1b. `pipelex_shared`: profile schema, adapter, KMS envelope (`infra-python-tools`, new branch off `dev`)

- [x] Schema `src/pipelex_shared/schemas/inference_profile.py` — three-model split (`InferenceProfileSaveBody` with write-only `credentials`, `InferenceProfile` storage shape with `to_public()`, `InferenceProfilePublic`) + `InferenceProfileBinding` (placement requires `task_queue`; `scoped` reserved). Overlay fields = plain dicts mirroring the `.pipelex/inference/` tree (Q7: schema-level validation only).
- [x] Fingerprint: `InferenceProfile.compute_fingerprint()` — SHA-256 over canonical JSON of binding + overlay + `credentials_version` (ciphertext deliberately excluded: re-encryption ≠ rotation).
- [x] KMS envelope `adapters/kms_envelope.py`: `GenerateDataKey` + AES-256-GCM, versioned base64 blob, `EncryptionContext={org_id, profile_id}`, everything fails closed via new `KmsEnvelopeError` (`exceptions/kms_exceptions.py`).
- [x] Adapter `adapters/dynamodb/inference_profile.py` — method.py clone; `get_profile` returns storage shape (worker boot), `list_profiles` public-only.
- [x] Org default pointer (A5): `Organization.default_inference_profile_id` + dedicated `set_default_inference_profile` setter (None = REMOVE; distinct from `update_profile`'s None-means-skip convention).
- [x] `IDPrefix.INFERENCE_PROFILE = "iprof"` + `new_inference_profile_id()` (deviation: `iprof` not `ip` — avoids reading as an IP address).
- [x] Tests: adapter moto tests incl. cross-org isolation; schema tests (Public never carries ciphertext; fingerprint semantics); KMS envelope round-trip + wrong-context + tamper + malformed + version drills; org-pointer set/clear/missing-org/legacy-row tests.

**CHECKPOINT 2 — DONE (2026-07-03).** Gates green (`make agent-check`, `make agent-test`). Final commit `725875c` on `feature/inference-profiles` — note: infra-python-tools' mainline is **`main`** (local `dev` was a stale v0.29-era branch); the branch was rebased onto `origin/main` (v0.33.0, billing-era organization schema/adapter — one conflict resolved in `organization.py`, keeping the new billing block + our setter). Fresh-context Sonnet `/code-review` ran with a dedicated crypto sub-review; triage outcome — **fixed:** KMS `Decrypt` now pins `KeyId` (confused-deputy), out-of-range-nonce tampering now surfaces as `KmsEnvelopeError` (was raw `ValueError`), fingerprint canonicalized against DDB `Decimal` rehydration (was unstable across round-trip), ciphertext read split into opt-in `get_profile_with_ciphertext` with `get_profile` public-by-default (was docstring-guarded), log scrubber hardened (whole `credentials` objects + `sk-`/`sk-ant-` prefixes), pre-existing `save_method`/`save_profile` stale `updated_at` fixed; **deferred to `wip/byok-api/deferred-review-findings.md`:** CMK-replacement/re-encrypt story, SaveBody credential echo in 422s (SecretStr decision at Phase 1c), Decimal normalization in the Phase 2c materializer, list pagination.

### 1c. Platform: CRUD routes + org-id forwarding (`pipelex-platform`, new branch off `dev`)

- [x] Bump `pipelex-shared` pin (commit `bea820c`): editable override dropped; now pins the pushed BYOK SHA `git+ssh://…@7e32c8cef…` + `uv lock` (`uv sync --frozen` clean). ⚠️ **TEMPORARY SHA pin — flip to `@v0.34.0` + `uv lock` before the platform PR merges** (after the shared PR merges to `main` and tags v0.34.0).
- [x] Router `routers/v1/inference_profiles.py`: list/get/create/update/delete + `GET/PUT /organizations/{org_id}/default-inference-profile` (separate path — avoids `{profile_id}`/"default" route ambiguity). methods.py CRUD shape + organizations.py path-guard + admin-role gate on mutations; wired in `main.py`.
- [x] Credential handling: write-only plaintext in → KMS envelope at save (encryption context = org+profile); rotation semantics None-keep / map-rotate / `{}`-clear, each rotation bumps `credentials_version` + recomputes `fingerprint`; responses only ever `InferenceProfilePublic`; KMS trouble → 503 fail-closed; delete clears a pointing org default; disabled profile as default → 409.
- [x] `X-Org-Id` forwarding: `runner_proxy` allowlist + `/execute` hand-built headers + `start_pipeline(org_id=...)` + trust-model docstrings updated.
- [x] Settings: `inference_profiles_kms_key_arn` (env `INFERENCE_PROFILES_KMS_KEY_ARN`).
- [x] Tests: `test_inference_profiles.py` (security contract: cross-org 403 incl. reads, member-mutation 403, missing-org 400, never-echoed credentials, KMS-503, rotation semantics, default-binding rules) + forwarding assertions added to `test_execute.py` / `test_tooling_proxy.py` / `test_pipeline_runner.py`.

**CHECKPOINT 3 — DONE (2026-07-03).** Gates green in both repos. Final commits: platform `1fbec2649` (off `dev` @ `08f22bf`), shared `7e32c8cef` (amended). Fresh-context Sonnet `/code-review` verified the pointed-at areas clean (authz, credential leak paths incl. 422 echo — the platform's validation handler drops pydantic `input`, idempotency body-hash storage, rotation semantics, header forwarding) and raised three findings, **all fixed**: F1 — disabling the org-default profile now 409s (auto-clear would silently flip runs onto server keys, the §5.5 violation); F2 — delete's default-clear is now an atomic conditional REMOVE (`clear_default_inference_profile_if_equals` in shared) instead of read-then-clear TOCTOU; F3 — `InferenceProfileSaveBody` structurally rejects prefix-shaped secret literals in plaintext overlay fields (residual documented in `wip/byok-api/deferred-review-findings.md` §4–5). **Phase 1 exit criteria met:** profiles can be created/listed/bound; the ref field exists in core; nothing consumes them yet.

### 1d. Infra: KMS CMK + platform encrypt grant (`pipelex-api-infra`, new branch off `main`)

Code in 1b/1c can land first; this must deploy before the platform routes are exercised in a real env.

- [x] New `infra/api/kms.tf`: per-env CMK + alias for inference-profile credentials; key policy admin-scoped (root-delegation → usage granted only via IAM); `enable_key_rotation=true`, 30-day deletion window, `prevent_destroy`. Reverses the repo's standing "no CMK" default (called out in the commit + docs).
- [x] Platform-side IAM: `api_inference_profiles_kms_policy` grants **`kms:GenerateDataKey` only** (deviation: the envelope's encrypt path never calls `kms:Encrypt`, so least-privilege drops it), scoped to the CMK ARN, attached to the shared `api_task_role`. **Decision taken (SIGNED OFF): attach narrowly, keep the role split as the standing follow-up** (documented at `iam.tf` `api_ses_policy` note). Decrypt deliberately not granted (Phase 2d worker-fleet concern).
- [x] Platform ECS env var: CMK ARN as `INFERENCE_PROFILES_KMS_KEY_ARN` (module var `inference_profiles_kms_key_arn` on `ecs/platform`, wired from `aws_kms_key.inference_profiles.arn` in `main.tf`; empty ⇒ envelope adapter fails closed).
- [x] Gates: `terraform fmt`/`validate`/`tflint` clean, `tfsec` HIGH/CRITICAL clean. PR-triggered plan is the real gate (never `apply` manually — repo rule).
- [x] Docs: new `docs/inference-profiles-kms.md` (CMK, admin-scoped key policy, two independent rotations, deploy ordering). No CHANGELOG in this repo.

**CHECKPOINT 4 — DONE (2026-07-03).** Local gates green (`fmt`/`validate`/`tflint`/`tfsec` — tflint+tfsec run from pinned release binaries since they aren't on the local box; validate confirms module-variable plumbing). Committed as `c28d211` on `pipelex-api-infra` branch `feature/inference-profiles` (off `main` @ `9caf63a`); nothing pushed. Fresh-context Sonnet `/code-review` fan-out ran on the commit — see Cold-start state for triage outcome. **Sign-off GRANTED (2026-07-03):** ① CMK key policy → keep the AWS-baseline root-delegation (admin-scoped) policy; ② task-role split → keep encrypt-only narrowly on the shared `api_task_role`, split deferred. Both confirm the committed code as-is (no changes). Remaining gate = CI `terraform plan` on the PR (after push approval).

---

## Phase 2 — Binding B end-to-end

Prereqs: Phase 1 merged/deployable; ⚠️ Q6 sign-off (adapter location); pipelex-temporal plugins track landed (hazards above).

### 2a. `pipelex-temporal`: queue-selection seam + ref verification (new branch off its mainline)

- [ ] Seam per A2: optional constructor-injected task-queue resolver on `TemporalOrchestrator` (`temporal_orchestrators.py:57-107`), forwarded as `make_temporal_pipe_run(task_queue=...)` (`temporal_pipe_run.py:143-159`). Keep `activity_queues` empty on org queues so the whole tree (child `WfPipeRouter` + activities) inherits the workflow queue.
- [ ] Queue-known validation strategy per A3 (`validate_task_queue_known`, `config_temporal.py:737-767`; orphan validation `:673-735`): materialized overlay declares `[queue_options.<org_queue>]`, or a sanctioned dynamic-queue mechanism. Decide + test.
- [ ] Worker-side ref verification (design §5.4/§10): on the worker, compare `pipe_run_params.inference_profile_ref` (payload) against the boot identity (env `INFERENCE_PROFILE_REF`); mismatch → hard fail the workflow task with a distinct error (mis-routed job must never run on another tenant's keys). Likely an interceptor or a check at workflow/activity bootstrap — pick the single-ceremony shape (one context manager / one interceptor, no copy-paste).
- [ ] Tests: resolver seam unit tests; queue validation; ref-mismatch hard-fail (in-process Temporal test server).

**CHECKPOINT 5** — gates: `make agent-check` + `make agent-test` in `pipelex-temporal`. Commit, update Cold-start state, fan out `/code-review`. ⚠️ sign-off: Q2 launch posture (org-default resolution on/off at launch).

### 2b. Hosted adapter: header → resolve → stamp → route (location per Q6 sign-off)

- [ ] Python package (in `pipelex-api-hosted` if signed off): ASGI middleware wrapping `api.main:fastapi_app` — reads `X-Org-Id` + `X-Inference-Profile-Id`, fail-closed validation mirroring `security.py:197-228` posture, binds a request-scoped ContextVar (mirror `RequestIdMiddleware`/`logging_context` pattern).
- [ ] Resolution: profile **meta** lookup (DDB read via `pipelex_shared` adapter — no decrypt API-side), short-TTL cache modeled on the platform entitlements read path (warm-cache last-known-good on store outage, cold-cache → 503; unknown/foreign profile → 404/403 `problem+json` via `api/errors.py` helpers; never fall back to server keys for a BYOK-bound org). Fail-fast so `/start`'s 202 can't be followed by an async bad-profile failure.
- [ ] Policy gate: `allow_request_inference_profile` config in the hosted config family (pattern: `api_config.py:89-110`).
- [ ] `pipelex.plugins` entry point registering the BYOK orchestrator under the `temporal` token: reads the ContextVar, stamps `inference_profile_ref` onto `pipe_job.pipe_run_params` via `model_copy(update=...)`, supplies `task_queue` from the profile's placement binding via the 2a seam.
- [ ] Dockerfile: install the package, flip the uvicorn CMD target (`Dockerfile:78`); runner task role gains scoped DDB read for profile items (infra follow-up in 2d).
- [ ] Tests: middleware + resolution unit tests (moto DDB), policy-gate tests, orchestrator stamping/queue tests. (Repo currently has no test rig — stand up the minimal pytest setup that fits its character.)

**CHECKPOINT 6** — gates: repo checks + `make build-check` (image builds). Commit, update Cold-start state, fan out `/code-review`.

### 2c. Worker boot-from-profile (`pipelex-worker`, new branch off its mainline)

- [ ] Entrypoint mode: when `INFERENCE_PROFILE_REF` is set → fetch profile (DDB) + decrypt credentials (KMS envelope, task-role IAM) → materialize `/app/.pipelex/inference/{backends.toml,routing_profiles.toml,deck/*.toml}` + temporal overlay declaring the org queue → `exec pipelex-temporal worker --task-queue <org_queue>`. Project-first config resolution makes the materialized tree override the baked one — zero core changes.
- [ ] Bootstrap implementation: small Python entry script in the image using `pipelex_shared` (adapter + envelope helper) — keeps one implementation of the envelope format.
- [ ] Credentials hygiene: decrypted keys go into the rendered TOML via `${VAR}` env indirection or directly with 0600 perms; never logged; document the posture.
- [ ] Config-health tests extended (`tests/test_temporal_config_health.py` guard stays green; add materialization round-trip test with a fixture profile).

**CHECKPOINT 7** — gates: `make t` + `make docker-test` in `pipelex-worker`. Commit, update Cold-start state, fan out `/code-review`.

### 2d. Infra: per-profile fleets + IAM decrypt + alarms (`pipelex-api-infra`)

- [ ] Reusable module `infra/api/ecs/org_worker/` cloned from `ecs/worker/` and parameterized: name/family/log-group/SG/ASG suffixed by profile key, `INFERENCE_PROFILE_REF` + task-queue env vars, image tag as a variable, per-fleet task role with `kms:Decrypt` (encryption-context-conditioned) + scoped DDB read; instantiated `for_each` over a profile map in tfvars.
- [ ] Runner task role: scoped DDB read for profile meta (2b dependency).
- [ ] Alarms per Q4: fleet running-vs-desired + queue backlog signal; runbook doc.
- [ ] `make tf-check` + CI plan review.

**CHECKPOINT 8** — gates: `make tf-check` + plan reviewed. Commit, update Cold-start state, fan out `/code-review`. ⚠️ sign-off before apply.

### 2e. Staging pilot + rotation drill

- [ ] Create a pilot org profile in staging (real provider key), provision its fleet, run a real workflow end-to-end on their keys; verify: ref recorded on the run, inference hit their backend (not our gateway), credentials absent from Temporal history/logs/responses.
- [ ] Mis-route drill: submit a job with a mismatched ref to the org queue → hard fail verified.
- [ ] Rotation drill: rotate key → `credentials_version` bump → fingerprint change → fleet roll → in-flight workflows drain gracefully; document timings.
- [ ] Fail-closed drills: unknown profile id (404/403), disabled profile, store outage (503, no silent server-key fallback).

**CHECKPOINT 9** — Phase 2 exit: pilot org runs real workflows on their own keys in staging; drills executed and documented. Update design doc §14 status + this file; fan out `/code-review` over any fixups made during the pilot. ⚠️ sign-off: GA gate.

---

## Phase 3 — Product surface (plan in detail after Phase 2)

- [ ] Webapp UI for profile management (`pipelex-app`) + user docs.
- [ ] Usage/cost attribution pass (§12): `inference_profile_ref` on usage records; gateway-credit accounting skips BYOK inference; margin analysis distinguishes BYOK vs gateway.
- [ ] Back-office/admin gap: `pipelex-admin-api` + `pipelex-back-office` profile visibility — close or explicitly ticket (workspace rule: flag the admin gap).
- [ ] Dispatched `/validate` routed to org fleets.
- [ ] Public-facing docs + problem-type error pages for the new failure modes.

## Phase 4 — Binding A (deferred, scale-triggered — design §7)

Not planned in detail here. Trigger: self-serve BYOK demand. Scope: `InferenceScope` + `InferenceScopeManager` + resolver seam in core, Bedrock-credential and spec-loading cleanups, per-activity scope entry, cache lifecycle + rotation tests, live `binding` flip.

---

## Key codebase facts (from 2026-07-03 exploration — trust but re-verify line numbers)

**Core (`_byok`):** `PipeRunParams` `pipelex/pipe_run/pipe_run_params.py:140` (`extra="forbid"`; single writer `PipeRunParamsFactory.make_run_params` `pipe_run_params_factory.py:13`; copy sites: `make_deep_copy` `:203`, `copy_by_injecting_multiplicity` `:215`, controllers `pipe_sequence.py:192`, `pipe_batch.py:162`, `pipe_parallel.py:156,255`, in-place mutation in `sub_pipe.py:44,50,130`). `CogtRunParams` `pipelex/cogt/content_generation/cogt_run_params.py:41` (frozen+forbid), derived at `pipe_run_params.py:177-184`, stamped on every assignment (`assignment_models.py`; operator call sites in `pipe_llm.py:244,353,372`, `pipe_img_gen.py:253,271`, `pipe_extract.py:158`, `pipe_structure.py:156,171`, `pipe_search.py:119`). `PipeJob` `pipelex/pipe_run/pipe_job.py:13` carries `pipe_run_params` + `library_crate` (the fingerprinted-payload precedent, `libraries/library_crate.py:11`). Ref-style models to mirror: `ModelHandle` `pipelex/plugins/model_handle.py:6`, `QualifiedRef` `pipelex/core/qualified_ref.py:17`. Tests to extend: `tests/unit/pipelex/pipe_run/test_cogt_run_params_carrier.py`, `test_assignment_models_schema.py`.

**pipelex-transport / pipelex-temporal:** `PipeRunArg` = `pipelex_transport/primitives/pipe_run_arg.py:8` (wraps `PipeJob`; pure pass-through — kajson converter `temporal_data_converter.py:50` is field-agnostic, new optional fields round-trip automatically). Queue selection: `TemporalOrchestrator.run` `temporal_orchestrators.py:57` → `make_temporal_pipe_run(task_queue=None)` `tprl_pipe/temporal_pipe_run.py:143-159` (falls back to `worker_config.default_task_queue`) → `workflow_caller.py:113,163`. Child workflow inherits parent queue (`wf_pipe_run.py:59-65`); activities ride the workflow queue while `activity_queues` is empty (`config_temporal.py:498-499`). Worker CLI `worker_cmd.py:24` (`--task-queue`), queue guard `validate_task_queue_known` `config_temporal.py:737`.

**pipelex-api (OSS — do not modify):** app wrap point `api/main.py:188` (`app = RequestIdMiddleware(fastapi_app)`); trusted-header read pattern `api/security.py:197-228` (`TRUST_FORWARDED_IDENTITY_HEADERS`); policy-gate pattern `api/api_config.py:89-110`; orchestrator dispatch `api/routes/pipelex/pipeline.py:184,259` via `get_orchestrator_registry().get_optional(mode=...)`; `OrchestratorProtocol.run` has **no queue param** (`pipelex/plugins/orchestrator_registry.py:34-40`); problem+json helpers `api/errors.py`, `api/problem_document.py`; routes hard-instantiate `ApiRunner` (`pipeline.py:523,577`).

**pipelex-api-hosted:** config-only today; Dockerfile `FROM pipelex/pipelex-api` + git+ssh installs of `pipelex-temporal`/`pipelex-transport` (`Dockerfile:58-74`), CMD uvicorn target `Dockerfile:78`; env overlays `.pipelex/api_{env}.toml` (`orchestration_mode="temporal"`, override disabled), `.pipelex/temporal_{env}.toml` (`default_task_queue="pipelex_{env}"`); deploy via `make ecr_push`/`deploy-{env}` gated on version/changelog checks.

**pipelex-worker:** Dockerfile bakes `.pipelex/` → `/app/.pipelex` (`Dockerfile:22`), CMD `pipelex-temporal worker --no-sandbox` (no `--task-queue`); config-loader is project-first (`pipelex/system/configuration/config_loader.py:94-141`) so a materialized `/app/.pipelex/inference/` overrides baked files; pins via `[tool.uv.sources]` git SHAs; deploy `make deploy-worker-{env}` → ECR `pipelex-worker-{env}:$(VERSION)`.

**infra-python-tools (`pipelex_shared` 0.30.0, consumed by SHA pin):** adapter template `adapters/dynamodb/method.py` (PK/SK helpers, CRUD, org isolation); base `adapters/dynamodb/__init__.py` (`remove_specific_keys`, `convert_floats_to_decimal`, table from `DYNAMODB_USERS_TABLE`); schema 3-model split `schemas/method.py`; id minting `core/id_minter.py:22-67`; **no KMS/encryption code exists** (`cryptography` dep available); no org-default pointer precedent (Organization scalar attrs `organization.py:103-110`, `update_profile` `:278-359`); moto fixture `tests/conftest.py:97-199` (`mocked_adapter`, single `test-table`, all GSIs).

**pipelex-platform:** CRUD template `routers/v1/methods.py:52-160`; path-guard + role gate `routers/v1/organizations.py:361-402`; identity `deps.py:62-201` (`OrgScopedUserDep`; gateway-injected `X-User-Id`/`X-Org-Id`/`X-Auth-Method`); entitlements cached fail-closed read path `deps.py:399-565`; forward allowlist `services/runner_proxy.py:56-61`; hand-built header dicts `routers/v1/execution.py:491-497`, `services/pipeline_runner.py:145` (trust docstring `:106-112`); errors = `ApiError` subclasses → RFC 9457 middleware; version in `pyproject.toml` IS the ECR tag.

**pipelex-api-infra (fresh main@9caf63a):** roots `infra/{shared,api,admin,relay}`; env = workspace + `terraform.{env}.tfvars`; image tags roll via `runner_image_tag`/`platform_image_tag`/`worker_image_tag` tfvars. Worker module `infra/api/ecs/worker/` (EC2, env vars only `PIPELEX_ENV`/`PIPELEX_GATEWAY_API_KEY`/`TEMPORAL_API_KEY`/`EVENTS_TABLE_NAME`/`RESULTS_BUCKET_NAME` — no queue param; narrow `worker_task_role` `iam.tf:578-595` to clone). Platform shares `api_task_role` with runner (`iam.tf:556-568`, split-me caveat `:762-768`). **No CMKs anywhere** (standing "no CMK" notes at `s3_app.tf:18-19`, `ecr_platform.tf:50`). Single-table `pipelex-users-{env}` `infra/api/dynamodb/table.tf` (+ entitlements table `dynamodb_entitlements.tf`). Gateway: `ANY /v1/{proxy+}` → platform ALB; runner explicit routes `apigateway_http.tf:371-473`; **`X-Org-Id` already injected** via `overwrite:header.*` on all integrations (`:432-439,:466-473,:522-529`), sourced from the authorizer Lambda (`src/pipelex_lambdas/authorizer/handler.py:415-521` JWT, `:713-895` API-key). Checks: `make tf-check`; never apply manually.

---

## Cold-start state (update at every checkpoint)

**Last updated:** 2026-07-04 — Checkpoints 1–4 ALL CLEARED + signed off. Phase 1 (Foundation) code-complete across core + shared + platform + infra, all pushed, **4 PRs open** (Option B: platform pinned to the shared SHA for green CI).

**Open PRs / merge order (Phase 1 Foundation):**

1. **pipelex-shared** [infra-python-tools#35](https://github.com/Pipelex/infra-python-tools/pull/35) → `main`, from branch **`release/v0.34.0`** (v0.34.0). Merge first, then **tag v0.34.0**. (Branch-flow guard: this repo has NO `dev` branch and rejects `feature/* → main` — releases must come from `release/vX.Y.Z`. The original `feature/inference-profiles` PR #34 was closed + superseded; the code commit `7e32c8c` the platform pins is reachable on `release/v0.34.0`.)
2. **platform** [pipelex-platform#76](https://github.com/Pipelex/pipelex-platform/pull/76) → `dev` (v0.2.5). ⚠️ Before merging, **flip its `pipelex-shared` pin `@7e32c8c` → `@v0.34.0` + `uv lock`** (currently a temporary SHA pin so CI is green).
3. **core** [pipelex#1019](https://github.com/Pipelex/pipelex/pull/1019) → `dev` (independent; core is 3 behind dev — rebase if GitHub flags conflicts).
4. **infra** [pipelex-api-infra#185](https://github.com/Pipelex/pipelex-api-infra/pull/185) → `main` (independent; **`apply` before the platform KMS routes run in an env**).

Version/changelog CI note: platform + infra-python-tools gate every PR on a version bump + `## [v<ver>] -` changelog entry (CI-only, not covered by `make agent-check`) — handled (shared v0.34.0 `e4c45f7`, platform v0.2.5 `f674eaa`). Core's version/changelog gates only fire on PRs to `main`, so the PR-to-`dev` needs neither; pipelex-api-infra has no such gate.

- **Where we are:** Phase 1a (core ref) DONE — `4921a031d` on core `feature/BYOK-per-request`. Phase 1b (pipelex_shared foundation) DONE — `7e32c8cef` on infra-python-tools `feature/inference-profiles`. Phase 1c (platform CRUD + X-Org-Id forwarding) DONE — `1fbec2649` on platform `feature/inference-profiles`. Phase 1d (infra KMS CMK + platform encrypt grant + ECS wiring) DONE — `c28d211` on pipelex-api-infra `feature/inference-profiles` (off `main` @ `9caf63a`). All gates green everywhere. No branch pushed anywhere.
- **Deviations from plan so far:** ID prefix `iprof` (not `ip`); ciphertext read is opt-in `get_profile_with_ciphertext` (public-by-default reads); default binding on its own path `/organizations/{org_id}/default-inference-profile`; SaveBody rejects prefix-shaped secret literals in overlay fields; scrubber hardening + `save_method` timestamp fix rode along as flag-and-fix in pipelex_shared. **Phase 1d:** IAM grant is `kms:GenerateDataKey` only (plan said `Encrypt`/`GenerateDataKey`; envelope's encrypt path never calls `kms:Encrypt`, so least-privilege drops it); task-role split NOT done — took the documented recommendation (encrypt-only narrowly on shared `api_task_role`, split deferred); CMK carries `prevent_destroy` + `enable_key_rotation`; admin-scoped key policy = AWS-baseline root delegation.
- **Phase 1d review triage:** fresh-context Sonnet `/code-review` ran on `c28d211` (cross-checked the IAM grant against the real `kms_envelope.py` + platform `inference_profiles.py`/`settings.py`, ran `terraform validate`). **No high/critical defects; nothing to fix — `c28d211` stands as-is.** Verified least-privilege-correct (`GenerateDataKey`-only matches the encrypt path exactly; `Decrypt` correctly absent since the platform never decrypts → no runtime `AccessDenied`), key policy standard-safe (no lockout), env-var name matches the platform `Settings` field, fail-closed confirmed. Two findings, both **deferred not fixed**: (a) low/hardening — an encryption-context IAM condition on the grant → `wip/byok-api/deferred-review-findings.md` §7 (the reviewer's exact `ForAllValues` form is imprecise; do it correctly alongside the Phase 2d decrypt grant); (b) the shared-`api_task_role` over-grant note — already documented in-code + docs, the acknowledged tradeoff with the role-split follow-up.
- **Branches:** core `_byok` = `feature/BYOK-per-request` (feature commit `4921a031d` + tracker commits). `infra-python-tools` = `feature/inference-profiles` @ `7e32c8cef` (single commit off `origin/main`). `pipelex-platform` = `feature/inference-profiles` @ `1fbec2649` (single commit off `dev` @ `08f22bf`); **uncommitted editable-pin override in `pyproject.toml`/`uv.lock`** (deliberate — restore the git+ssh pin to the pushed shared ref + `uv lock` before landing). `pipelex-api-infra` = `feature/inference-profiles` @ `c28d211` (single commit off `main` @ `9caf63a`).
- **Pending sign-offs / merge-time actions:** ① ~~push approval~~ + ~~open PRs~~ — DONE 2026-07-04 (4 PRs open); ② ~~Checkpoint 4 CMK key policy + task-role split~~ — **SIGNED OFF** (committed code unchanged); ③ **at merge:** merge shared #34 → tag v0.34.0 → flip platform #76 pin to `@v0.34.0` + `uv lock` → merge platform; ④ Q6 hosted-adapter location — before Phase 2b; ⑤ Q2 launch posture — Checkpoint 5.
- **Next:** watch CI on the four PRs; merge in the order above once green + reviewed. Then Phase 2 (Binding B end-to-end) — prereqs: Phase 1 merged/deployable + Q6 sign-off + the pipelex-temporal plugins track landing (repo hazard note).
