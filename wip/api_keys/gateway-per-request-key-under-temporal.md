# Per-request Gateway key under Temporal — the narrow design

Companion to `sdk-per-request-key-survey.md`. That document surveys every SDK we ship. The hosted-plane half of what is designed here — the resolver plugin, the wire mapping, provisioning, IAM — is specified for `pipelex-server` in `pipelex-server-per-request-gateway-key-handoff.md`. This one deliberately narrows to a single scenario and does not look sideways: **only the SDKs that connect to the Pipelex Gateway**, and **only a solution that holds under distributed execution with our Temporal plugin**. Anything the survey says about other backends (Bedrock, HuggingFace, Linkup, Google structured output, endpoint overrides) is out of scope here and is not restated. Everything below about SDK behaviour was verified by executing the pinned versions in `.venv` (`openai` 2.34.0, `portkey-ai` 2.3.0, `instructor` as pinned) against an `httpx.MockTransport` that records the outbound headers.

## 1. What "the Gateway" is, concretely

The gateway plugin (`pipelex/providers/gateway/gateway_plugin.py`) registers six SDK handles, and every one of them authenticates the same way: the credential is the `x-portkey-api-key` header, and nothing else. There are exactly two client kinds behind those six handles.

| Registered sdk | Family | Client object built by `get_or_create` | Worker | Per-request header seam that exists today |
|---|---|---|---|---|
| `gateway_completions` | LLM | `openai.AsyncOpenAI` (`GatewayCompletionsFactory.make_portkey_openai_client_for_completions`) | `OpenAICompletionsLLMWorker` | `make_extras` → `extra_headers` on both the text call and the `instructor` call |
| `gateway_responses` | LLM | `openai.AsyncOpenAI` (`GatewayResponsesFactory.make_portkey_openai_client_for_responses`) | `OpenAIResponsesLLMWorker` | same, on both paths |
| `gateway_completions` | IMG_GEN | `openai.AsyncOpenAI` | `OpenAICompletionsImgGenWorker` | `make_extras` → `extra_headers` |
| `gateway_img_gen` | IMG_GEN | `AsyncPortkey` (`GatewayFactory.make_portkey_client`) | `GatewayImgGenWorker` | none — `with_options(config=…)` per call; the edits path goes through the vendored `portkey_client.openai_client.post(options={"headers": …})` |
| `gateway_extract` | EXTRACT | `AsyncPortkey` | `GatewayExtractWorker` | `with_options(config=…)` per call; the base64 path additionally passes `headers=extra_headers` from `make_extras` |
| `gateway_search` | SEARCH | `AsyncPortkey` | `GatewaySearchWorker` | none — `with_options(config=…)` per call |

For the `AsyncOpenAI` kind the boot key is baked into `default_headers=createHeaders(api_key=…)` and the OpenAI `api_key` is the literal placeholder `"unused-auth-via-portkey-headers"`. For the `AsyncPortkey` kind the boot key is the client's `api_key`. Both are built once per process and cached in `SdkClientRegistry` under `ModelHandle.sdk_handle`, which has no caller dimension.

In the hosted plane today there is **one gateway key per environment**: `PIPELEX_GATEWAY_API_KEY` is injected identically into the runner and the worker task definitions (`pipelex-server/infra/api/ecs/runner/ecs.tf`, `…/worker/ecs.tf`) and read through the backend's `api_key = "${PIPELEX_GATEWAY_API_KEY}"` placeholder. So "a different key per request" means: the same two client objects, the same Portkey endpoint, but the `x-portkey-api-key` value chosen per call from something the request carries.

## 2. Verified override mechanics, per client kind

The good news is that neither client kind needs a new client, a new `instructor` wrapper, or any change to the three model-keyed caches the survey worries about. The key can be swapped at the request. The details differ between the two kinds, and one of them has a trap.

### `openai.AsyncOpenAI` (completions, responses, completions-img-gen)

- `extra_headers={"x-portkey-api-key": key}` on the call **wins over** the boot `default_headers`. Verified: the boot key is sent when no extra header is given, the per-request key is sent when it is.
- The same holds **through `instructor`**: `create_with_completion(..., extra_headers=…)` forwards the header to the underlying client on both the chat-completions and the responses adapters. Verified on the completions path with a recorded header of the per-request value.
- `client.with_options(default_headers={...})` also works and the clone shares the same `httpx` pool (`clone._client is client._client` is `True`), but it is unnecessary here because the header seam already exists in `make_extras` on every `AsyncOpenAI` gateway path.
- The SDK's transport retries (`max_retries` from `transport_max_retries`) reuse the same request options, so a retried call keeps the per-request key.

Because `GatewayFactory.make_extras` is already called per request on all three of these workers and already reads `inference_job.job_metadata` to emit tracing headers, adding one more header there covers all three with no worker change.

### `AsyncPortkey` (img-gen, extract, search)

- `client.with_options(config=config_id, api_key=key)` sends the per-request key, and the clone **shares the connection pool** (`AsyncPortkey.copy` ends with `http_client=http_client or self._client`). The three workers already call `with_options(config=…)` on every request, so this is one added keyword argument at each call site.
- **Trap: `post(..., headers={"x-portkey-api-key": key})` does not override the key.** Verified: the boot key is still what goes out. The Portkey base client merges its own auth headers over the per-call `headers` mapping, the opposite precedence from `openai`. This matters because `GatewayExtractWorker._extract_base64_url` currently passes `headers=extra_headers` from `make_extras` — so if the key were only added inside `make_extras`, the extract path would *look* wired and silently send the boot key. The `AsyncPortkey` workers must use `with_options(api_key=…)`, not the headers argument.
- The image-edits path, which bypasses `AsyncPortkey.post` because of the upstream `files=` bug and calls the vendored `portkey_client.openai_client.post(..., options={"headers": {…}})`, **does** honour a per-request `x-portkey-api-key` in that `options["headers"]` mapping. Verified.

The `SdkClientRegistry`, the `InferenceManager` worker cache, and the boot-time `InferenceBackend` all stay exactly as they are. Nothing is cached per credential, because nothing needs to be.

## 3. The Temporal shape of the problem

The request context that knows *whose* call this is dies at the runner and has to be reborn in a worker process that never saw the HTTP request. Tracing the path fixes what the design is allowed to rely on.

1. The API Gateway authorizer stamps `X-Org-Id` from the token (`overwrite:header.X-Org-Id = $context.authorizer.org_id` in `apigateway_http.tf`) and the runner receives it.
2. The runner builds `JobMetadata(user_id=…, pipeline_run_id=…, request_id=…, …)` once, in `pipelex/pipeline/execution_seams.py`, and hangs it on the `PipeJob`.
3. Under the Temporal orchestrator the `PipeJob` **is the workflow input**, so `JobMetadata` is serialized by our pydantic data converter into workflow history. Child workflows carry it forward; `copy_with_update` is a deep `model_copy`, so any new field survives every hop unchanged.
4. The activity granularity is one inference call: `act_llm_gen_text(llm_assignment: LLMAssignment)` is the whole activity body, and `LLMAssignment.job_metadata` is the same object. Inside the activity it becomes `LLMJob.job_metadata`, that is `InferenceJobAbstract.job_metadata`, and that is what `make_extras` and every gateway worker hold when they build the request. The same is true of the img-gen, extract and search assignments.
5. Which worker executes a given activity is not knowable: the fleet polls one shared queue (`default_task_queue`, empty `activity_queues`), retries are `maximum_attempts = 3`, and a retry may land on a different process. Each worker boots Pipelex once (`worker_cmd.py`) and polls forever.

Five consequences follow, and they are the constraints of the design rather than choices:

- **The reference must ride on `JobMetadata`.** It is the only thing that provably arrives in the activity, on every attempt, on any worker. This is the payload-first rule applied; ContextVars, request-scoped globals and per-run singletons have no home in a process that hosts many runs of many tenants at once.
- **The material must never ride on it.** `JobMetadata` is workflow history in plaintext. `StoragePayloadCodec` does not soften this: it is a size-threshold offload (1 MB default, shipped disabled), and a Portkey key is a short string that passes through untouched even with the codec on. Carry an opaque reference; resolve it in the worker.
- **Resolution happens in the activity, never in workflow code.** Workflow code must be deterministic and side-effect-free on replay; a secrets lookup there is both a side effect and a replay hazard. Activities are exactly where I/O belongs, and the seam (`make_extras` / the `with_options` call) is already inside activity execution.
- **Resolution must be repeatable and reachable from every worker.** Attempt two may run somewhere else, so any worker in the fleet must be able to turn any tenant's reference into that tenant's key. That is a blast-radius statement about worker IAM, not just a code one.
- **Any cache is process-scoped, keyed on the reference, and needs a TTL.** A "per run" cache does not exist anywhere under Temporal: built per activity it is always empty, held per process it leaks across runs with no eviction signal. Keying on the reference gives a hit across every run of that tenant on that worker, and the TTL becomes the revocation latency, which then has to be a stated number.

## 4. Proposed design

Four small pieces, two of them in `pipelex` and two of them in the hosted plane. The OSS runtime gains a seam with a no-op default; the hosted plane gives the seam a real implementation.

### 4.1 A reference field on `JobMetadata`

Add one optional field, constrained at the wire boundary the same way `request_id` is (printable ASCII, bounded length), for example `gateway_key_ref: str | None = None`. It is opaque to `pipelex`: the runtime only carries it and hands it to the resolver. In the hosted plane the natural value for v1 is the org id the authorizer already injects, but the field should not be *named* org id, because the reference may later be a key id or a profile id (the BYOK inference-profile track) without touching the runtime.

The runner stamps it where `JobMetadata` is built (`execution_seams.py`) from a field on the run request. In the hosted plane that field is set by the platform, which fronts every `/v1/*` route and already holds the authenticated org and user when it dispatches to the runner — the runner itself never sees `X-Org-Id` (see the handoff doc, §3 and §4.1). Nothing downstream needs to know: the workflow input, the child workflows and every activity payload carry it for free.

### 4.2 A resolver protocol in `pipelex`, defaulting to today's behaviour

Add a small `GatewayKeyResolver` protocol with one method, `resolve(gateway_key_ref: str) -> str`, and register it on the runtime hub the same way the secrets provider is (a default set at boot, replaceable by a plugin). The default resolver returns `backend.api_key`, so `pipelex` alone behaves exactly as today. Whether an *absent* reference falls back to the boot key or fails closed is a policy the hosted plane must be able to choose (see §6); the runtime should expose that as a switch rather than hard-code either.

Put a single helper next to `make_extras`, say `GatewayFactory.resolve_request_key(inference_job=…) -> str | None`, that reads `inference_job.job_metadata.gateway_key_ref`, calls the resolver, and returns `None` when the boot key should be used. Both client kinds then consume that one helper.

### 4.3 The two per-request seams

- **`AsyncOpenAI` paths** (`gateway_completions` LLM and img-gen, `gateway_responses`): `GatewayFactory.make_extras` adds `extra_headers["x-portkey-api-key"] = key` when the helper returns a key. No worker changes; the header already flows into the text call and into `instructor` on both the completions and the responses workers.
- **`AsyncPortkey` paths** (`gateway_img_gen`, `gateway_extract`, `gateway_search`): each `with_options(config=config_id)` becomes `with_options(config=config_id, api_key=key)` when a key is resolved, and the image-edits path adds the header to its `options["headers"]` mapping. Because of the trap in §2, the extract worker must **not** rely on the `headers=extra_headers` argument for the key even though it will now contain one; the header there is harmless but inert.

Under Temporal each activity attempt re-runs the helper, so a retry on another worker resolves the same reference on that worker and gets the same key.

### 4.4 The hosted resolver

Lives in the hosted plane (`pipelex-server`), not in `pipelex`. It maps a reference to that tenant's Portkey key from wherever those keys are provisioned and stored, and wraps the lookup in a **process-scoped, bounded, TTL cache keyed on the reference**. That is the only cache this design introduces, it holds strings rather than clients, and it is one dictionary per worker process. It must not cache a failed lookup for long, so a freshly provisioned tenant is not locked out for a full TTL by a race between provisioning and first use.

## 5. What this design does not touch

- No credential dimension on `SdkClientRegistry`, `InferenceManager` or `ModelHandle`. One `AsyncOpenAI` and one `AsyncPortkey` per gateway model handle per process, as today.
- No per-credential `instructor` wrappers.
- `InferenceBackend` stays the boot-time singleton; the endpoint does not change per request. If a per-request *endpoint* is ever needed the survey's open question 5 applies and this document is the wrong one.
- Non-gateway backends are untouched; the resolver is only consulted from the gateway plugin.
- The Temporal plugin itself does not change: no new activity, no workflow edit, no data-converter change. The reference travels inside a model that already crosses the boundary.

## 6. Cache, revocation and reachability under the worker fleet

The process-scoped cache from §4.4 has three parameters that must be decided, not defaulted, because the worker outlives every run.

- **TTL is the revocation SLA.** A rotated or revoked tenant key remains usable on a given worker until its entry expires or the process restarts. A short TTL costs one key-store round trip per (tenant, worker, TTL window), which is negligible at any realistic fleet size; a long TTL trades that for a longer window in which a revoked key still works. This needs a number.
- **Bound the cache.** Key it on the reference, cap the entry count, evict least-recently-used. The material is small, but an unbounded map of tenant secrets in worker memory is still not something to ship.
- **Every worker must be able to read every tenant's key.** With one shared queue there is no way to route a tenant to a subset of workers, so the read grant is fleet-wide. In the BYOK track the worker's decrypt path was explicitly *not* granted yet (deferred as a Phase 2d concern); this design needs it before it can run in the hosted plane. If a per-tenant Portkey key is provisioned server-side rather than supplied by the tenant, the store and the grant are simpler than BYOK's envelope scheme, but the reachability requirement is the same.

Missing reference policy: in OSS and local development, no reference means the boot key, and the behaviour is unchanged. In the hosted plane a request that reaches the runner without an org id is already an authorizer failure upstream, so failing closed on a missing reference is cheap there and closes the "runs on the shared key by accident" hole. Recommend making it a hosted-side switch that defaults to fail-closed.

## 7. Side benefits and a caution

Portkey attributes usage to the API key that made the call, so per-tenant keys give per-tenant usage, budgets and rate limits at the gateway with no work on our side. That is a reason to prefer per-tenant Portkey *keys* over per-tenant Portkey *configs* or metadata headers as the mechanism.

The caution is the same one the survey raises about `openai`'s callable `api_key`: do not be tempted to make the shared `AsyncOpenAI` refresh its own key from a callable, because `_refresh_api_key` writes to the shared client between two awaits and concurrent activities on the same worker would race. The header seam has no shared mutable state, which is why it is the right one under a worker that runs many tenants' activities concurrently.

## 8. Tests worth writing before the code

- For each of the six handles, a `MockTransport` test asserting the outbound `x-portkey-api-key` equals the per-request key when a reference is present and the boot key when it is not. The `AsyncPortkey` extract path needs its own test precisely because `post(headers=…)` would pass a naive review while sending the boot key.
- One test that resolves two different references through the same cached client objects concurrently and asserts each request carried its own key, since the whole point of the design is that the shared client is safe.
- A Temporal-level test with two activities carrying two references executing on one worker, asserting header attribution, and a resolver spy asserting a retry re-resolves rather than assuming.
- A wire-boundary test that a `JobMetadata` with the new field round-trips through the pydantic data converter unchanged, and a guard that the field's constraint rejects a value that looks like key material (length and character-class are the cheap proxies).

## 9. Open questions, narrowed to this scope

1. **What is the reference in v1?** The org id is already available on every hosted request; a key id or profile id would need a second lookup. Recommendation: org id, under an opaque field name.
2. **Where are per-tenant Portkey keys provisioned and stored?** Provisioned through the Portkey admin API on org creation, or on first use by the resolver? Stored beside the org record with envelope encryption, or in the secrets manager? This is a hosted-plane decision; only the resolver interface is fixed by this document.
3. **TTL and bound for the worker cache.** Needs numbers, not defaults.
4. **Fail-closed on a missing reference in the hosted plane?** Recommended yes; confirm.
5. **Worker read access.** Which role gets the read grant and whether it is the shared task role or a worker-specific one, in line with the deferred task-role split from the BYOK track.
