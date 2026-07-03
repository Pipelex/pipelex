# Per-org inference configuration for the hosted API (BYOK) — design

Status: **DRAFT for discussion** — foundation decisions taken (see §2), binding recommendation proposed (§14), open questions at the end (§15).

Branch: `feature/BYOK-per-request` (worktree `_byok`). Scope spans `pipelex/` (core), `pipelex-api` / `pipelex-api-hosted` / `pipelex-worker` / `pipelex-temporal` (private), `pipelex-platform`, `pipelex-api-infra`, `infra-python-tools`.

## 1. Goal and non-goals

Clients of the hosted platform run their workflows on our runner. Today every run uses the server's inference configuration, loaded once at process boot. Some clients want to bring their own inference providers and keys. We want a stable, stored, **per-organization named inference configuration** — an *inference profile* — that a request references by ID (or that is bound as the org's default), so that the client's runs execute against **their** backends, credentials, routing, and deck instead of ours. Default behavior is unchanged: no profile → server configuration.

Non-goals for v1:

- **Request-inline inference config.** Passing the full backend/deck configuration in each request (the way `mthds_contents` carries the library) is explicitly rejected: it is heavy, puts secrets on the wire, and the configuration is stable per client — a lookup by ID is the right shape.
- **Self-serve OSS feature.** The profile concept, store, and request surface are hosted-only (D3). Core gains only generic, neutral mechanism.
- **Per-user profiles, profile sharing across orgs, marketplace of configs.**

## 2. Decisions taken so far

- **D1 — Org-scoped ownership.** Profiles belong to an organization: `PK=ORG#{org_id}, SK=INFERENCE_PROFILE#{profile_id}` in the existing single-table design, mirroring how methods are stored. All workspace members share the org's profiles.
- **D2 — Full overlay.** A profile can override the entire inference configuration surface: enabled backends + credentials + endpoints, routing profile, and deck (aliases, choice defaults/overrides, presets, even custom model specs — e.g. a client's fine-tuned model or Azure deployment names). Conceptually, a profile ≈ a serialized `.pipelex/inference/` tree applied over the server's base.
- **D3 — Hosted-only product.** The profile store, CRUD, request surface, and resolution live in private repos. `pipelex/` gains only neutral mechanism (a ref field on the run payload, and — if/when Binding A ships — the scoped inference stack). Open-source `pipelex-api` stays untouched or gains at most an opaque pass-through.
- **R1 — Payload-first invariant (hard rule).** Any run-scoped fact that must survive a process boundary travels **in the serialized run payload** (`PipeJob` / `PipeRunParams` inside `PipeRunArg`), never in a ContextVar. ContextVars are permitted only as in-process plumbing *after* deserialization — exactly the way the worker calls `set_current_library(...)` after hydrating the `LibraryCrate` from the payload. The hosted API runs on Temporal; anything designed around ambient in-process state silently breaks in distributed execution. This invariant governs every mechanism in this document.
- **R2 — Placement is a first-class binding.** We already plan Temporal task queues matched to inference providers, and the routing machinery exists (§3). "Configure inference for an org" can therefore mean "route the org's run to workers that were *booted* with the org's configuration" — no per-request config resolution at all. This is Binding B (§6) and is the recommended v1 (§14).

## 3. Current state — what makes this non-trivial

**Boot-time, process-global inference stack (core).** `Pipelex.make()` → `ModelManager.setup()` (`pipelex/cogt/models/model_manager.py`) loads `.pipelex/inference/backends.toml` + `backends/<name>.toml` (model specs) + `routing_profiles.toml` + `deck/*.toml`, substitutes `${VAR}` credentials from the `SecretsProviderAbstract` (env by default) **into `InferenceBackend.api_key` at load time** (`backend_library.py`), and builds one `ModelDeck`. Everything downstream resolves through hub funnels: `get_model_deck()`, `get_models_manager()`, `get_inference_manager()`, `get_sdk_client_manager()` (`pipelex/hub.py`).

**Two caches with no tenant dimension.** `InferenceManager.llm_workers` (keyed by model handle) and `SdkClientRegistry` (keyed by `sdk@backend/variant`) cache workers and SDK clients process-wide. Any two requests using the same handle with *different credentials* would collide. This is why "just swap the key per request" is not a small change — it forces the scoped-stack work of Binding A.

**Inference runs in the workers, not the API.** Hosted prod is `orchestration_mode = "temporal"`. The API builds a `PipeJob` and enqueues; `pipelex-worker` executes workflow tasks and inference activities against **its own** boot-loaded config. Both API and worker currently enable only `pipelex_gateway` (one `PIPELEX_GATEWAY_API_KEY`) with routing `all_pipelex_gateway`; the per-provider spec files (`openai.toml`, `anthropic.toml`, …) are present but inert.

**Per-handle activity-queue routing already exists.** `pipelex-temporal/pipelex_temporal/config_temporal.py` defines `activity_queues[activity_name].by_handle[routing_key]` with documented `resolve_queue` fallback semantics, and `ContentGeneratorInWorkflow` routes every inference activity (LLM, img-gen, extract, search) by its model handle. The provider-matched-queues plan is implemented at the config level; BYOK-by-placement builds directly on it.

**The library-crate precedent.** The library went from boot-global to per-run: content travels as a serializable `LibraryCrate` on the `PipeJob`, the worker rehydrates it (`open_fresh_library` + `load_from_crate`), and only *then* sets an in-process ContextVar. Lessons carried over: payload is the source of truth; fingerprints give idempotent caching; the set/restore ceremony should be one context manager, not copy-pasted boilerplate.

**Identity and storage building blocks (hosted).** The runner receives only `X-User-Id` today — org identity is not propagated (platform→runner forward allowlist is `content-type, accept, x-user-id, x-request-id`). The DynamoDB single-table has the natural slot for org-scoped items (methods pattern). There is **no encrypted per-tenant secret storage yet**: the Portkey gateway key sits plaintext on the User row, and our provider keys are plaintext ECS env vars from one Secrets Manager blob. The per-request policy-gate pattern to copy exists in `pipelex-api/api/api_config.py` (`orchestration_mode` + `allow_request_orchestration_mode_override`).

## 4. Design overview

Two independent layers:

1. **Foundation (common, build once):** the profile itself — org-scoped storage with encrypted credentials, platform CRUD, org identity propagation, a profile *ref* carried in the run payload, and the resolution policy (explicit request → org default → server default, failing closed).
2. **Binding — how a run's execution actually acquires the profile's configuration.** Two bindings, which compose:
   - **Binding B — placement:** the run is routed to a dedicated Temporal task queue whose workers were booted with the profile's configuration. Credentials bind at worker boot; nothing per-request in core.
   - **Binding A — scoped stack:** shared workers resolve the profile per run/activity and build a request-scoped inference stack (the library-crate-style core refactor).

The profile schema is binding-agnostic from day one; a `binding` field on the profile says how it executes. We can ship B first and add A later without changing the client-facing contract.

Request flow (Binding B, hosted):

```
client → api.pipelex.com /v1/execute|start  (X-Inference-Profile-Id optional)
  → runner (pipelex-api-hosted): resolve org (X-Org-Id) → profile meta lookup (cached)
      - explicit id: verify org owns it, else 403/404 problem+json
      - none: org default binding, else server default (no BYOK)
  → stamp PipeRunParams.inference_profile_ref = {org_id, profile_id, fingerprint}
  → TemporalOrchestrator: start_workflow(task_queue = profile.task_queue)
  → org worker fleet (booted with the profile's .pipelex/inference tree + decrypted keys)
      - workflow tasks: deck resolution against the org's deck
      - inference activities: org's SDK clients/keys (per-handle sub-queues still available)
```

## 5. The foundation (common to both bindings)

### 5.1 The profile

A named, versioned, org-owned inference configuration. Content = the full overlay (D2), expressed with the **existing blueprint shapes** so no new config language is invented:

- `backends`: per-backend overlay — `enabled`, credential slots, `endpoint`, `extra_config`. Credentials are stored separately from the rest (encrypted at rest, see §5.2) and referenced from the backend entries the same way `${VAR}` placeholders work today, so the non-secret part of a profile is safe to log, diff, and ship to any process.
- `routing_profile`: a routing profile blueprint (or a named reference to a server-defined one).
- `deck`: deck overlay blueprints — aliases, choice defaults/overrides, presets, additional model specs. Deep-merged over the server's base deck blueprint using the same merge machinery as the multi-file deck loader.
- `binding`: how runs execute — `placement` (task queue name(s), Binding B) or `scoped` (Binding A), plus room for per-binding settings.
- `fingerprint`: SHA-256 over the canonical serialized overlay **plus a credential-version marker** (e.g. the ciphertext digest or a monotonically bumped `credentials_version`). Key rotation must change the fingerprint — that is what busts Binding A's scope cache and signals Binding B fleets to roll.

**Split that makes everything simpler: the overlay is not secret; only credentials are.** Deck, routing, backend topology can be read by any of our processes (API-side validation, dry-run, docs/UI). Credentials are decrypted only where they are used: org worker boot (Binding B) or scope build in a worker (Binding A). They never enter Temporal payloads, logs, traces, or API responses.

Naming: "inference profile" is a runtime/product concern → Pipelex-branded is fine per the brand-boundary rule; wire fields stay neutral (`inference_profile_ref`, no `pipelex_` prefix needed inside our own envelope).

### 5.2 Storage and secrets (hosted)

Item: `PK=ORG#{org_id}, SK=INFERENCE_PROFILE#{profile_id}` (adapter in `pipelex_shared`, modeled on `method.py`). Org default binding: an attribute on the org profile row (or a `DEFAULT` pointer item) naming the default profile id.

Credential storage options:

| Option | How | Pros | Cons |
|---|---|---|---|
| **(a) KMS envelope in DynamoDB (recommended)** | Credential map encrypted with a data key under a dedicated CMK; ciphertext stored as an attribute on the profile item | Single store, one read path, cheap, IAM-scoped decrypt (only worker/runner task roles get `kms:Decrypt`), easy per-env keys | Key usage audit is coarser than Secrets Manager; we own the envelope code |
| (b) Per-tenant Secrets Manager secret | Profile stores the secret ARN | First-class rotation hooks, fine-grained audit | ~$0.40/secret/month, extra API + latency on every resolution, secret sprawl, cross-account complexity later |
| (c) Portkey virtual keys | Client keys live in Portkey; profile references a Portkey config/virtual key | Almost no secret handling on our side; usage dashboards for free | Third-party custody of client keys (hard sell for exactly the clients who want BYOK), coupling to Portkey product surface, only gateway-routable providers |

Recommendation: **(a)**, with (c) kept as a possible additional backend *type* (a profile whose backends route through a client-scoped gateway config) rather than the storage foundation.

### 5.3 Identity propagation

The runner must know the org. Add `X-Org-Id` to the trusted forwarded-identity headers on both ingress paths: the API-Gateway authorizer context → header injection for direct API-key calls, and the platform→runner forward allowlist (`runner_proxy.py`, `execution.py`, `pipeline_runner.py`) for proxied calls. The header is trusted for the same reason `X-User-Id` is: the runner is only reachable through the gateway/platform. Reading it can live in the hosted overlay (keeping OSS `security.py` untouched) — see §9.

### 5.4 The ref in the run payload (R1)

`PipeRunParams` gains an optional `inference_profile_ref` — a small serializable model `{owner_id, profile_id, fingerprint}` (owner = org id; field names kept tenant-neutral in core). Carrier choice: `JobMetadata` down-passes *information* (identity, correlation, timestamps); **`PipeRunParams` is the object that passes directives**, and selecting an inference configuration is a directive, alongside `run_mode`. `PipeRunParams` is `extra="forbid"`, so this is an explicit, typed field addition. For Binding A the ref additionally propagates into `CogtRunParams` — the run-params slice already stamped on every assignment that crosses the wire into inference activities — which puts it exactly where per-activity scope resolution needs it. This is the **only** cross-boundary carrier. It serves:

- **Binding A:** the worker resolves the ref → builds/reuses the scoped stack.
- **Binding B:** audit + defense-in-depth — org workers *verify* the ref matches the profile they were booted with and refuse mismatched jobs (a mis-routed job must fail, not silently run on another tenant's keys).
- **Both:** usage/cost attribution (§12) and traceability (which config version produced this run).

This is a neutral core field addition and the main `pipelex/` change needed for v1.

### 5.5 Resolution policy

Order: explicit `X-Inference-Profile-Id` on the request (must belong to the caller's org) → org default binding → server default. **Fail closed**: if the store lookup errors, or the referenced profile is missing/disabled, the request is rejected (`problem+json` 4xx/503) — we never silently fall back to the server's keys for an org that has BYOK configured. Running a client's workload on *our* credentials when they asked for theirs is a billing and confidentiality bug, not a graceful degradation. Lookups are cached with a short TTL (the entitlements-overrides read-path pattern: cached, fail-closed).

## 6. Binding B — placement: route the run to pre-configured workers

**Idea (R2):** a profile maps to a dedicated Temporal task queue (or queue set). The whole workflow — workflow tasks *and* activities — is started on that queue: `start_workflow(task_queue=profile.task_queue)` at submission in `TemporalOrchestrator` (private code). The workers polling that queue are **our** ECS tasks, booted with the org's full `.pipelex/inference/` tree and decrypted credentials. Deck resolution (which happens in workflow tasks) and inference calls (activities) all see the org's configuration through the completely ordinary boot path. Within the fleet, the existing `activity_queues.by_handle` routing still applies if the org wants provider-matched sub-queues.

**Worker boot-from-profile.** The worker image gains an entrypoint mode: given `INFERENCE_PROFILE_REF` (env), fetch the profile from the store (task role: DDB read + `kms:Decrypt`), materialize `backends.toml` / `routing_profiles.toml` / `deck/*.toml` into the config dir, then exec `pipelex-temporal worker` as today. Zero core changes — the loader path is untouched; the profile is just another config source. (A later refinement can replace file materialization with a boot hook, but files are the honest v1.)

**Fleet lifecycle.** Provisioned per profile-with-placement-binding: an ECS service (module in `pipelex-api-infra`), sized small, tagged with the profile ref. Profile update / key rotation → bump `credentials_version` → rolling restart of the fleet (Temporal drains in-flight activities gracefully; sticky workflow tasks resume on fresh workers). Activation is not instant (minutes, first provision), which is acceptable for "stable per-client configuration".

**What's great about it:**

- **No core refactor.** The deck stays boot-time; the two tenant-blind caches are correct because each process serves exactly one tenant config.
- **Strongest isolation.** Client keys exist only in that fleet's process memory and its boot path — never in shared worker memory alongside other tenants, never in payloads. This is also the easiest story to *tell* a security-conscious client.
- **Aligned with the existing plan** for provider-matched queues; the placement mechanism (queue choice at submission) is a one-line concern in private code.
- **Blast-radius containment for free**: a client's misbehaving workload or a provider outage on their keys degrades their fleet, not the shared one.
- **Mixed configurations work**: the org fleet's config can enable both their backends *and* our `pipelex_gateway` (our key is just config on our own infra), with their routing profile deciding which models go where.

**Costs and limits:**

- **Infra per org-profile.** One (small) always-on service per placement-bound profile. Fine for the first N enterprise clients; a wall for self-serve scale. Scale-to-zero on queue depth is possible later but is real machinery.
- **Rotation = restart**, not instant. Update latency is minutes.
- **Only under Temporal orchestration.** Fine for hosted prod (temporal-only, override disabled). `/validate` can dispatch to the org queue too (dispatched validate already exists); anything the API serves in-process against the deck (`/v1/models`, deck-dependent dry-run details for profile-custom models) sees the server deck in v1 — solvable with a deck-only (non-secret) scoped view later, see §15.

## 7. Binding A — scoped inference stack in shared workers

The library-crate-style core refactor. Needed when self-serve BYOK volume makes per-org fleets uneconomical, or for instant activation/rotation.

**Core mechanism (`pipelex/`):**

- **`InferenceScope`** — one coherent, immutable-after-build bundle: backend set (with resolved credentials), routing profile, `ModelDeck`, plus *its own* `InferenceManager` worker cache and `SdkClientRegistry`. Scoping whole caches sidesteps re-keying every cache by tenant; teardown closes async SDK clients.
- **`InferenceScopeManager`** (hub-registered): holds the **default scope** (built at boot from files — today's behavior, unchanged) plus an LRU of profile scopes keyed by **fingerprint** (bounded via config; eviction = teardown). Profiles are stable per client, so scope reuse across requests is the common case; rotation changes the fingerprint and naturally builds a fresh scope.
- **Resolution flow (payload-first per R1):** the worker activity/workflow bootstrap reads `inference_profile_ref` from the deserialized run params (at activity granularity, from the `CogtRunParams` stamp on the assignment), calls a registered resolver (see below) to fetch overlay + decrypted credentials, `get_or_build`s the scope, and only then sets an in-process current-scope ContextVar for the duration of that activity — the exact `set_current_library`-after-hydration pattern, factored as **one** context manager from day one (the library ceremony's copy-paste is the anti-pattern to avoid). Hub funnels (`get_model_deck()`, `get_llm_worker()`, `get_sdk_client_manager()`) resolve current-scope-first, default-fallback.
- **Resolver seam:** a `pipelex.plugins` registrar slot (`add_inference_profile_resolver`) mapping ref → overlay + credentials. Core names no store; our private plugin registers the DDB+KMS resolver (installed in worker and API images). This keeps D3: OSS ships mechanism, not the feature.
- **Required cleanups surfaced by exploration:** (1) Bedrock/`bedrock_anthropic` credentials come from global `aws_config`, not `backend.api_key` — must move onto the backend so scoping captures them; (2) per-backend model-spec TOMLs are only loaded for boot-enabled backends — spec loading must become unconditional (a spec library) with enablement decided per scope.

**Costs:** real core surgery (the deck/backends/caches lifecycle), tenant keys transiting shared worker memory (weaker isolation story), careful cache lifecycle (eviction, client closing, rotation). **Benefits:** no per-org infra, instant activation and rotation, scales to thousands of orgs, and also works in direct (non-Temporal) mode.

## 8. How the bindings compose

The profile's `binding` field decides per profile: `placement` for clients who warrant a dedicated fleet (or need the isolation story), `scoped` for self-serve. The client-facing contract (profile CRUD, request header, resolution policy, ref in payload) is identical; only the execution machinery differs. Shipping B first does not paint us into a corner because the foundation (§5) — including the payload ref — is exactly what A consumes later.

## 9. Request surface

- **Header, not body extra:** `X-Inference-Profile-Id`, read by a thin hosted overlay in `pipelex-api-hosted` (which today is config-only and would grow a small adapter module wrapping the OSS app — an explicit change to that repo's character, called out for sign-off). A header works uniformly across `/execute`, `/start`, `/validate`, avoids body buffering in middleware, and keeps the OSS request schema untouched (D3).
- **Fail fast:** the API resolves and authorizes the profile at request time (meta only — no credential decrypt needed API-side under Binding B) so `/start`'s 202 isn't followed by an async failure for a bad profile id. Errors are RFC 7807 `problem+json`, consistent with the verdict-vs-transport rules.
- **Threading to the orchestrator:** the resolved ref must reach `PipeRunParams` construction and the `start_workflow` call. Primary design: explicit parameter threading through the (private) request path into the orchestrator. If a hop between the hosted middleware and private orchestrator code needs ambient state, a request-scoped ContextVar **within the single API process** is acceptable under R1 (it never crosses a process boundary; the payload still records the ref as the durable truth) — but explicit threading is preferred wherever signatures allow.
- **Policy gate:** feature enabled iff a resolver/store is configured (hosted); optionally an `allow_request_inference_profile` config mirroring the orchestration-mode gate, so ops can freeze explicit selection while keeping org defaults.

## 10. Security considerations

- Credentials never in: Temporal payloads/history, logs, traces, API responses, `/v1/models` output, error messages. `SecretStr`-style wrappers wherever they exist in memory; redaction tests.
- KMS decrypt permission only on the task roles that need it: org worker fleets (Binding B) and shared workers (Binding A). The platform gets encrypt+CRUD; the back-office/admin path is a separate decision (flag the admin-tooling gap per workspace rules — the back-office cannot see or manage profiles until `pipelex-admin-api` grows an endpoint).
- `X-Org-Id` / `X-Inference-Profile-Id` are trusted only because the runner is unreachable except through the gateway/platform; the profile-ownership check (profile's PK must equal the caller's org) is enforced at resolution regardless.
- Org workers verify `inference_profile_ref` against their boot identity (Binding B mis-route → hard fail).
- Profile create/update is a natural place for an optional "validate keys" ping (cheap provider call) — nice-to-have, not v1-blocking.

## 11. Failure semantics

- Unknown/foreign profile id → 404/403 `problem+json` at request time.
- Store/KMS outage during resolution → reject (503), fail closed (§5.5). Never fall back to server credentials for a BYOK-bound org.
- Client's provider rejects their key mid-run → normal inference error path, surfaced with backend context in the run failure; terminal-failure webhooks still fire (crash-loud must not trade away client notification).
- Binding B fleet down/unprovisioned → workflow tasks sit on the queue; surface a distinct operational alarm + a clear run-status story rather than silent queueing forever (open question on timeout policy, §15).

## 12. Billing and usage attribution

Runs under a client profile must not meter against our gateway credit. Usage/cost records (UsageRegistry → distributed cost reporting) should carry the `inference_profile_ref` so: (1) gateway-credit accounting skips BYOK inference, (2) we can still show clients token/cost telemetry computed from model specs (server specs, or the profile's specs for custom models), (3) margin analysis distinguishes BYOK from gateway traffic. Needs a pass over the reporting pipeline once a binding is chosen.

## 13. Alternatives considered and rejected

- **Request-inline configuration** (library-crate-style content in every request): rejected by the product requirement itself — stable per client, secrets on the wire, heavy.
- **ContextVar-carried scope as the primary mechanism**: rejected per R1. ContextVars don't cross Temporal boundaries; the payload is the source of truth, ContextVars at most re-expose it in-process after hydration.
- **Gateway-credential-swap only** (per-request Portkey virtual key on the single `pipelex_gateway` backend): still requires the cache-scoping fix (the SDK-client cache is credential-blind), puts client keys in a third party, and covers only gateway-routable providers. Kept only as a possible backend type inside a profile (§5.2c).
- **Per-request env mutation / re-running `ModelManager.setup()`**: process-global mutation under concurrency; not serious.
- **Per-tenant full deployments** (dedicated API + workers + domain per client): maximal isolation but duplicates the entire stack; Binding B achieves the isolation that matters (credentials + inference execution) while sharing the API tier.

## 14. Recommendation and phased rollout

**Recommendation: build the foundation (§5) + Binding B (§6) as v1; keep Binding A (§7) as the designed, scheduled follow-up triggered by self-serve demand.** Rationale: B reaches a sellable, strongly-isolated BYOK with near-zero core risk, exploits routing machinery that already exists, and matches the current client shape (few, named, stable orgs). A's core refactor is real surgery on the hottest path in the runtime; doing it later, against a proven profile contract and with B as the fallback, is strictly safer than doing it first. The payload ref (§5.4) — the piece both bindings share — lands in core in phase 1, so A never requires re-plumbing the wire format.

Phases (each ends at a natural checkpoint; update this doc with status/decisions at each):

- **Phase 1 — Foundation.** `pipelex_shared` adapter + DDB item + KMS envelope; platform CRUD routes (`/organizations/.../inference-profiles`) + org default binding; `X-Org-Id` propagation; core: `PipeRunParams.inference_profile_ref` (+ propagation into `CogtRunParams` and serialization through `PipeRunArg`). *Checkpoint: profiles can be created/listed/bound; refs travel end-to-end (observable in run records); nothing consumes them yet.*
- **Phase 2 — Binding B end-to-end.** Worker entrypoint boot-from-profile; terraform module for per-profile fleets; `TemporalOrchestrator` queue selection from the resolved profile; hosted overlay reading `X-Inference-Profile-Id` + fail-fast resolution; org-worker ref verification; fail-closed policy + problem+json errors. *Checkpoint: a pilot org runs real workflows on their own keys in staging; rotation drill executed.*
- **Phase 3 — Product surface.** Webapp UI for profile management + docs; usage attribution pass (§12); back-office/admin-api gap either closed or explicitly ticketed; dispatched `/validate` routed to org fleets. *Checkpoint: GA for hosted BYOK by placement.*
- **Phase 4 — Binding A (scale-triggered).** `InferenceScope` + manager + resolver seam in core; Bedrock-credential and spec-loading cleanups; shared-worker per-activity scope entry; scope-cache lifecycle + rotation tests; profile `binding` flip supported live. *Checkpoint: self-serve BYOK on shared fleets.*

## 15. Open questions (for discussion)

1. **Version pinning.** Should a run pin the profile *version* it started with (immutable versioned items + `CURRENT` pointer), or is "worker uses what it was booted with / fetched" enough? Placement makes mid-run consistency mostly automatic (a fleet restart is a deliberate act), but long workflows spanning a rotation deserve a defined answer.
2. **Org default vs explicit-only.** Is the org-default binding (run BYOK without any request opt-in) wanted from v1, or do we start explicit-header-only and add defaults once the UX exists in the webapp?
3. **Fleet economics.** Minimum fleet shape per org-profile (1 small always-on task? scale-to-zero later?), and who decides a client qualifies for a placement-bound profile.
4. **Queue-wait policy.** If an org's fleet is down, how long may a workflow wait on the queue before we fail the run loudly / page ops?
5. **Deck-only scoped view for the API tier.** Under Binding B, `/v1/models` and deck-dependent validation see the server deck. The non-secret overlay could power a deck-only scoped view API-side (a thin slice of Binding A without credentials). v1-defer or v1-include?
6. **`pipelex-api-hosted` grows code.** The hosted repo moves from config-only to config+thin adapter (header middleware, ref threading). Acceptable, or should that adapter live in the private plugin package instead?
7. **Custom model specs blast radius.** D2 allows profiles to define model specs. What validation runs at profile-save time (schema-only platform-side vs a runner-side deep validation endpoint that builds the deck overlay)?
