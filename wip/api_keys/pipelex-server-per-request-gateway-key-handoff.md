# Per-request Gateway key — handoff spec for `pipelex-server`

Companion to `gateway-per-request-key-under-temporal.md`, which is the design and the rationale. This document is the part of that design that has to be built **in the hosted plane** (`pipelex-server`, plus one small change in the public runner `pipelex-api`), written as a spec: what must exist, what contract it is built against, what it may assume, and what has to be decided before it starts. It does not restate the design's reasoning and it is not a phased plan. Where it disagrees with the design doc it is because the design doc assumed something about the hosted plane that turned out not to be true; those points are marked **(correction)**.

Everything below about the hosted plane was checked against `pipelex-server` `dev` at `f0fd3d4` (2026-08-18, after the credit top-up, method-deletion and Temporal-erasure merges) and against `pipelex-api`.

## 1. Scope

In: everything needed for a hosted run — whether it executes in the runner process or on any Temporal worker — to call the Pipelex Gateway with a Portkey key that belongs to the tenant who made the request, instead of the environment-wide `PIPELEX_GATEWAY_API_KEY`.

Out: the runtime seams themselves (they land in `pipelex` on `feature/API-key-per-request`, see §2), any non-gateway backend, per-request endpoints, and BYOK in the sense of tenant-supplied provider keys. The Portkey keys here are **ours**, provisioned per tenant in our Portkey workspace, exactly like the ones `POST /v1/gateway-api-key` already mints.

## 2. The contract the runtime will expose

The `pipelex` side of this feature adds three things. Names are the current proposal and the runtime owns them; the shapes are what the hosted plane must build against.

- **`JobMetadata.gateway_key_ref: str | None`** — an opaque reference, constrained like `request_id` (printable ASCII, bounded length). It rides on the workflow input, every child workflow and every activity payload; the hosted plane never touches it after it is stamped. It must carry a reference, never key material: `JobMetadata` is Temporal history in plaintext.
- **A `GatewayKeyResolver` with one method, `resolve(gateway_key_ref: str) -> str`**, contributed through the plugin registrar the same way a secrets provider is, and consulted only by the gateway plugin at request time (inside activity execution under Temporal). The default resolver returns the boot key, so an environment without the hosted plugin behaves as today.
- **A missing-reference policy switch** in runtime config: fall back to the boot key, or fail the inference call. OSS defaults to fallback; the hosted plane sets it (see §4.4).

Every gateway handle — completions, responses, completions-img-gen, img-gen, extract, search — honours the resolved key per request, and a Temporal retry re-resolves on whichever worker picks the attempt up. That is the runtime's guarantee; the hosted plane does not re-implement any of it.

The way the reference enters the runner (§4.1) also needs a `pipelex`/`pipelex-api` surface, and it is the same one the org-scoped storage plan (`pipelex-server/docs/plans/org-scoped-storage-20260817.md`, ready to implement) is about to use for `storage_scope`: a field on the runner's run-request body (`PipelexPipeRunInput` in `pipelex/runtime_bridge/payloads.py`) threaded into `pipeline_run_setup` and onto `JobMetadata`. The two fields should be added the same way, ideally in the same change.

## 3. What the hosted plane looks like today, and what that changes

- **One key per environment.** `PIPELEX_GATEWAY_API_KEY` is injected identically into the runner and the worker task definitions (`infra/api/ecs/runner/ecs.tf`, `infra/api/ecs/worker/ecs.tf`) and read through `api_key = "${PIPELEX_GATEWAY_API_KEY}"` in `api-hosted/.pipelex/inference/backends.toml` and `worker/.pipelex/inference/backends.toml`. It stays as the boot key; after this work it is only what the fallback policy would use.
- **The platform fronts every `/v1/*` route, including run dispatch (correction).** The design doc traces the request as "authorizer stamps `X-Org-Id` → the runner receives it and builds `JobMetadata`". That is not the topology. API Gateway sends `ANY /v1/{proxy+}` to `platform/`; only the legacy `/runner/v1/*` prefix and the two time-boxed `upload` / `resolve-storage-url` exceptions reach the runner ALB directly. The platform then reaches the runner over the internal ALB in two ways: `routers/v1/execution.py` handles `POST /start` and `POST /execute` itself, records the Run row, and calls `services/pipeline_runner.py`, which builds an explicit JSON payload and forwards exactly one identity header, `X-User-Id`; and `routers/v1/tooling_proxy.py` relays `/validate`, `/models` and `/build/*` through `services/runner_proxy.py`, whose header allowlist is `content-type`, `accept`, `x-user-id`, `x-request-id`. In both cases the platform holds the authenticated identity (`OrgScopedUserDep`: `user_id` and membership-validated `org_id`), and the runner (`pipelex-api`, `TRUST_FORWARDED_IDENTITY_HEADERS=true`, `AUTH_MODE=none`) sees only `X-User-Id`. So the reference is stamped by the platform, and API Gateway needs no change. `api-hosted/` has no source of its own — it is a composition around the public runner — so nothing can be stamped there either.
- **Per-tenant Portkey keys already exist, per user, and now carry paid money.** `POST /v1/gateway-api-key` mints one Portkey key per user through `pipelex_shared.domain.gateway_key.provision_gateway_key` (extracted from the router in the credit top-up work so the LemonSqueezy order webhook can provision too) and stores `gateway_api_key_id`, `gateway_api_key_hash` and the plaintext `gateway_api_key` on the User row. Portkey holds that key's `credit_limit`; promo grants and, since `feat/credit-topup` merged, **paid top-ups** (`POST /v1/billing/credits/checkout` → order webhook → `apply_credit_grant`) are added to it under a per-key DynamoDB lock. Today those keys serve `pipelex login` clients calling the gateway directly; hosted runs do not use them. Subscriptions remain org-grain and plan-only, and the top-up plan states that credits are per user with `org_id` on the grant for reporting only. Portkey returns keys masked after creation, which is why the plaintext lives on our side.
- **The Portkey admin credential is platform-only.** `PORTKEY_API_KEY` and `PORTKEY_WORKSPACE_ID` are wired into the platform task definition (`infra/api/ecs/platform/ecs.tf`) and the order-webhook Lambda. Provisioning must stay on those two.
- **Neither the runner nor the worker installs `pipelex-shared`.** Both compose `pipelex[dynamodb,s3]` + `pipelex-temporal` + `pipelex-daytona-sandbox`. A resolver that reads a DynamoDB row cannot import the shared adapters without adding that dependency to both images; §4.2 asks for a small, dependency-light member instead.
- **The worker already has its own task role.** `worker_task_role` (`infra/api/iam.tf`) is distinct from `api_task_role`, and today holds only the events-table DynamoDB policy and the app S3 policy. The read grant this feature needs (§4.4) is an addition to that role, not the deferred split the BYOK track was waiting on — that split exists.

## 4. Deliverables

### 4.1 The reference on the wire — platform, `pipelex-api`, and the runner hop

The platform stamps the reference on every hop it makes to the runner, deriving it from the authenticated request context (`current_user.org_id` or `current_user.user_id`, per §6.1) and never from anything the client sent. Two hops, one mechanism each:

- **Run dispatch** (`services/pipeline_runner.py`, used by `/start` and `/execute`): the reference rides in the explicit JSON payload as `payload["gateway_key_ref"]`, exactly as the org-scoped storage plan carries `storage_scope` — data the runner threads onto `JobMetadata`, not identity. On the `pipelex-api` side `PipelexPipeRunInput` gains the field and `ApiRunner` passes it to `pipeline_run_setup(gateway_key_ref=…)`.
- **Tooling proxy** (`services/runner_proxy.py`, used by `/build/*`, `/validate`, `/models`): `/build/*` makes gateway calls through the kernel path, which builds its own `JobMetadata`. The reference reaches it as a trusted-proxy header, provisionally `X-Gateway-Key-Ref`, that the platform *sets* on the forwarded request (the allowlist must not merely pass a client-supplied one through), and that `pipelex-api` reads under the same `TRUST_FORWARDED_IDENTITY_HEADERS` gate as `X-User-Id` and threads into the kernel's metadata. Routes that never reach the gateway (`/validate`, `/models`) may carry it harmlessly.

Either way the runner treats the value as opaque and validates it with the same constraint as the `JobMetadata` field, which keeps this a generic runner feature and not a hosted one. `compose/edge` (the local API Gateway emulator) needs nothing: the platform derives the reference itself. Legacy direct-to-runner routes (`/runner/v1/*`) get no reference and therefore run under the policy in §4.4; they are slated for deletion and should not be extended.

### 4.2 The hosted resolver — a new plugin member

A new workspace member, provisionally `pipelex-server/gateway-keys/` (distribution `pipelex-gateway-keys`), in the same class as `temporal/`, `transport/` and `daytona-sandbox/`: it states the exact `pipelex==X.Y.Z` it is built against, it is installed by **both** `api-hosted/` and `worker/` (the runner still executes gateway calls in-process for build and non-Temporal paths), and it contributes the resolver through a `pipelex.plugins.*` entry point.

Behaviour:

- `resolve(gateway_key_ref)` maps the reference to the tenant's Portkey key plaintext read from the store chosen in §6.2, using `boto3` directly rather than `pipelex-shared` (see §3). It never provisions: an unknown reference is a lookup failure, not a trigger to mint a key.
- It wraps the lookup in one process-scoped cache, keyed on the reference, holding strings only: positive entries with a TTL, negative entries with a much shorter TTL, an entry cap with least-recently-used eviction. The TTL is the revocation latency and must be stated in the member's `docs/`. Proposed starting values, to be confirmed in §6.3: positive TTL of a few minutes, negative TTL of a few seconds, cap in the low thousands of entries.
- Failure semantics: a store error or a missing row raises, and the runtime turns that into a failed inference call; the resolver never falls back to the boot key on its own — that decision belongs to the runtime's policy switch, not to the plugin.
- Logging: the reference may be logged; the resolved key never is, in any log line, error message or exception field. Errors that quote the reference use the same printable-ASCII assumption the runtime enforces.
- The lookup is synchronous or async to match what the runtime's protocol ends up requiring; the seam sits inside `make_extras` / the `with_options` calls, which are on the async request path.

### 4.3 Per-tenant keys — store and provisioning

Provisioning happens in `platform/` (and the order-webhook Lambda, which already shares `provision_gateway_key`) and nowhere else, because that is where `PortkeyService` and the Portkey admin credential live. Because the platform now fronts dispatch, it can also guarantee a key exists **before** forwarding a run — provision-on-dispatch through the shared, race-safe `provision_gateway_key` — so the worker never meets an unprovisioned tenant and fail-closed cannot fire on a fresh account. Depending on §6.1:

- **User-grain reference.** The reference is the user id and the resolver reads the User row's existing `gateway_api_key`. Nothing new to provision beyond provision-on-dispatch for users who never opened the developer page. Hosted runs then draw down the same Portkey `credit_limit` that `pipelex login` usage, promo grants and paid top-ups land on — which is coherent if purchased credit is meant to pay for hosted usage, and a surprise otherwise. A user whose gateway key was revoked through the admin flow (`clear_gateway_api_key`) becomes unable to run hosted methods.
- **Org-grain reference (the design doc's recommendation).** A new per-organization Portkey key, minted through the same `PortkeyService.create_api_key` at organization creation plus provision-on-dispatch as the backstop, stored on the Organization row with the same three fields the User row uses. Attribution then matches the org-grain subscription, but purchased per-user credit is not what hosted runs consume, and the two Portkey keys per person have to be explained on the developer page.

Either way the plaintext must remain retrievable server-side. That conflicts with the standing intent to stop persisting the gateway key plaintext on the User row (the "masked preview only" direction recorded around the `GET /gateway-api-key` throttle work). The two must be reconciled explicitly: if the plaintext moves under envelope encryption, the resolver's read grant becomes a KMS decrypt grant on every worker, which is the reachability cost the design's §6 describes.

### 4.4 Configuration, IAM and deploy

- **Policy switch.** `api-hosted/.pipelex/pipelex_{dev,staging,prod}.toml` and `worker/.pipelex/pipelex_{dev,staging,prod}.toml` set the runtime's missing-reference policy to fail-closed. Every hosted call path that reaches the gateway goes through the platform after §4.1, so this closes the "ran on the shared key by accident" hole at no cost — but only once both hops in §4.1 stamp, and only once the legacy direct-to-runner routes are gone or accepted as failing.
- **Read grant.** `worker_task_role` and `api_task_role` gain read access to the table and item class holding the per-tenant key (the users table named by `DYNAMODB_USERS_TABLE`, or the org rows if §6.1 goes org-grain), plus `kms:Decrypt` if §4.3 lands the plaintext under envelope encryption. Every worker in the fleet needs it; the shared task queue gives no way to route a tenant to a subset of workers.
- **Environment.** Whatever the resolver reads to find its table (a `DYNAMODB_USERS_TABLE`-style variable, which the platform already receives) is added to both the runner and the worker task definitions, next to `PIPELEX_GATEWAY_API_KEY`, and to `compose/` and the `.env.example` files so the local stack keeps working. The local stack must keep working with the fallback policy too, so a developer without per-tenant keys is not blocked.
- **Versions.** The new member is a shared library, so it bumps `api-hosted/` and `worker/` and itself, and the platform bumps for §4.1; `make deploy-plan ENV=<env> BASELINE=<sha>` must select all three deployables. The member's `pipelex==X.Y.Z` pin joins the multi-site edit that moving `pipelex` already requires (workspace `CLAUDE.md`, "Moving `pipelex`"), and its `docs/` say so.

### 4.5 Tests owned by the hosted plane

The per-handle header tests, the concurrent two-reference test and the wire-boundary round-trip live in `pipelex`. The hosted plane owns:

- resolver unit tests: cache hit within TTL, miss after TTL, negative entry expiring faster than a positive one, eviction at the cap, and a store error raising rather than returning the boot key;
- platform tests on both runner hops: the dispatch payload and the proxied `/build/*` request carry a reference derived from the authenticated context, and a client-supplied `gateway_key_ref` field or `X-Gateway-Key-Ref` header is ignored — the sibling of the existing rule that `X-Org-Id` is overwrite-only at the gateway;
- an integration test in the local stack: two tenants, one worker process, one run each, and the outbound `x-portkey-api-key` observed per run at the gateway boundary (a recording transport or a stub gateway) — the assertion is attribution, not success;
- a fail-closed test through the runner: a run request without a reference fails at the inference call with the runtime's policy error, on the execute path and on the build path.

## 5. Non-goals

- No change to `SdkClientRegistry`, `InferenceManager`, `ModelHandle`, `InferenceBackend`, the `instructor` wrappers, or any Temporal workflow, activity or converter. If the implementation finds it needs one, stop and reread the design.
- No per-request endpoint, no per-request Portkey config; the key is the whole mechanism.
- No tenant-supplied keys. That is the BYOK inference-profile track; this work is what it will later plug into, by changing what the reference points at.
- No provisioning from the worker or the runner. The Portkey admin credential stays on the platform and the order-webhook Lambda.
- No API Gateway change. The reference is minted one hop later, in the platform.

## 6. Decisions to confirm before starting

1. **Reference identity in v1: user or organization?** This is now a product question before it is a technical one: **is hosted usage meant to consume the credit a user buys through the new top-up flow?** If yes, the reference is the user id, the resolver reads the User row's existing key, provisioning is already race-safe and shared, and Portkey attribution lands where the money is. If hosted usage is instead covered by the org's plan, the reference is the org id and a per-org key has to be provisioned and explained beside the per-user one. The design doc recommends org-grain, written before the top-up work merged; the resolver is indifferent (opaque reference, different row), so the choice costs nothing on the runtime side and everything on the product side.
2. **Store for the plaintext.** On the tenant's DynamoDB row as today, or moved behind envelope encryption now, given the standing intent to stop persisting it. Recommendation: keep it on the row for v1 with the read grant scoped to that item class, and take the envelope-encryption move as its own change with the KMS grant it implies.
3. **Cache numbers.** Positive TTL, negative TTL and entry cap — proposals in §4.2; the positive TTL is the revocation SLA and should be written down as such.
4. **Fail-closed in the hosted plane.** Recommended yes; confirm, and confirm that both platform hops (dispatch payload and tooling-proxy header) are in scope — fail-closed cannot ship with only one of them.
5. **Coordination with the org-scoped storage plan.** That plan is threading `storage_scope` from the platform payload through `PipelexPipeRunInput` into `JobMetadata` and touches the same `pipelex`, `pipelex-api`, `platform`, `transport` and `temporal` sites. Decide whether `gateway_key_ref` rides in that change or follows it; doing them together avoids two runner/worker rebuilds and two `pipelex` version moves.

## 7. Acceptance

The work is done when, in a deployed environment, two tenants running the same method on the same worker fleet produce two distinct Portkey usage attributions with no run touching `PIPELEX_GATEWAY_API_KEY`; a run that reaches the runner without a reference fails at the inference call rather than running on the shared key; revoking a tenant's key stops that tenant's runs within the stated TTL on every worker; and the local stack still runs end to end for a developer holding only the shared key.
