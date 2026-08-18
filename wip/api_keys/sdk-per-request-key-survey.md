# Per-request API keys: where the key is bound today, and what each SDK lets us override

Survey for `feature/API-key-per-request`. Two questions are in scope: **how do we decide to change the key, and how do we get it**, and **do the SDKs we ship let us override the key on the request rather than on the client**. Everything below about SDK behaviour was verified by reading and executing the versions actually pinned in `.venv` — versions are named at each claim, because several of these answers changed within the last few releases.

## 1. Where the key is bound today

The key travels through four stages, and every one of them happens exactly once, at boot.

1. **Declared as a placeholder in TOML.** Each backend in `pipelex/kit/configs/inference/backends.toml` declares `api_key = "${OPENAI_API_KEY}"` (or the `${env:…|secret:…}` fallback form).
2. **Substituted against the secrets provider.** `InferenceBackendLibrary.load()` binds a `substitute_vars` partial to the process-wide secrets provider (`backend_library.py:151`) and rewrites the whole blueprint dict. A backend whose variable will not resolve is *skipped* in lenient mode and *fatal* otherwise.
3. **Frozen onto the backend model.** `InferenceBackendFactory.make_inference_backend()` stores the resolved string on `InferenceBackend.api_key` (`backend.py:44`). That object lives on the models manager for the life of the process.
4. **Baked into an SDK client, which is then cached forever.** Each provider plugin calls `sdk_clients.get_or_create(handle=…, build=lambda: …Factory.make_…_client(backend=backend))`. The cache key is `ModelHandle.sdk_handle` — `"{sdk}@{backend}"` plus an optional variant (`model_handle.py:12`) — so it carries **no notion of who is asking**. `OpenAIClientFactory.make_openai_client` reads `backend.api_key` at construction (`openai_client_factory.py:45`) and never looks again.

There is a fifth cache on top: `InferenceManager` memoises workers by bare model handle (`inference_manager.py:66`), and each worker also builds an `instructor` wrapper around the client in its `__init__`. So a single `openai@openai` client, and a single `instructor` wrapper over it, serve every caller in the process.

**The consequence to design around:** three caches (`InferenceBackend`, `SdkClientRegistry`, `InferenceManager.*_workers`) are all keyed on *what model* is being called and none on *whose credentials*. Whatever mechanism we pick, either the key must ride on the request and bypass all three, or all three keys must grow a credential dimension.

Two smaller irregularities worth knowing before designing:

- **Linkup does not use `backend.api_key` at all.** Both Linkup workers call `get_secrets_provider().get_secret(secret_id="LINKUP_API_KEY")` directly in their own `__init__` (`linkup_extract_worker.py:44`, `linkup_search_worker.py:43`). Any backend-level design silently misses these two workers unless they are moved onto `backend.api_key` first.
- **Gateway and Portkey do not authenticate with `api_key` at all.** Both build a plain `openai.AsyncOpenAI` whose `api_key` is the literal placeholder `"unused-auth-via-portkey-headers"`, and put the real credential in `default_headers` via `createHeaders(api_key=…)` (`gateway_completions_factory.py:130`). The credential is the `x-portkey-api-key` header. This turns out to be the single most convenient path to convert — see §4.

## 2. How do we decide to change the key?

The codebase already has the vehicle, and it already reaches the exact place a per-request key would need to land.

Every worker call receives an `InferenceJobAbstract`, which carries `job_metadata: JobMetadata`. Both the Gateway and the Portkey factories already read that metadata per request and turn it into request headers: `make_extras(inference_model, inference_job=…, output_desc=…)` returns `(extra_headers, extra_body)`, which the worker passes straight into the SDK call (`openai_completions_llm_worker.py:149` for text, `:234` for the instructor path). That is a working, per-request, payload-carried header seam that exists today for tracing.

So the decision seam is: **the caller stamps a credential reference onto the job payload; the worker resolves it in `make_extras`-time and emits it as an auth header or a per-request client option.** This is payload-first and needs no ContextVars.

The one thing that must not happen: putting the secret *itself* on `JobMetadata`. `JobMetadata` is explicitly designed to cross the Temporal serialization boundary (its own comments say so), which means anything on it lands in workflow history in plaintext. Carry a **reference** (an org id, a profile id, a key id) and resolve it to a secret inside the worker process; never carry the material.

## 3. How do we get it?

`SecretsProviderAbstract` (`pipelex/tools/secrets/secrets_provider_abstract.py`) is already the right shape and is already pluggable through a registry. What it lacks is a *scope*: every method takes only `secret_id`, so "the OpenAI key" is a single global fact. A per-request design needs one of:

- a provider whose `get_secret` is given the caller scope alongside the secret id; or
- a per-request resolver object built once per request from the payload reference and handed to the workers.

Either way, the resolution result should be cached for the life of one run — the workers make several SDK calls per pipe, and a KMS/Secrets-Manager round trip per LLM call is not acceptable.

## 4. SDK survey — can the key be overridden per request?

| SDK (pinned version) | Per-request key override | Mechanism |
|---|---|---|
| `openai` 2.34.0 | **Yes, two ways** | `extra_headers={"Authorization": f"Bearer {key}"}` on the call; or `client.with_options(api_key=…)` which reuses the same httpx pool |
| `openai` Azure variant 2.34.0 | **Yes** | Same, but the header is `api-key`, not `Authorization` |
| `anthropic` 0.99.0 | **Yes, two ways** | `extra_headers={"X-Api-Key": key}`; or `client.with_options(api_key=…)`, also pool-reusing |
| `portkey-ai` 2.3.0 | **Yes** | `client.with_options(api_key=…)` — and the codebase already calls `with_options(config=…)` on this client |
| Gateway / Portkey via `openai` | **Yes, trivially** | The credential is already just the `x-portkey-api-key` header, and an `extra_headers` dict is already threaded per request |
| `mistralai` 1.12.0 | **Yes, two ways** | `http_headers={"Authorization": f"Bearer {key}"}` on every operation; or construct the client with a **callable** `api_key`, re-invoked per request |
| `google-genai` 1.75.0 | **Yes on the native path, no through `instructor`** | `config=GenerateContentConfig(http_options=HttpOptions(headers={"x-goog-api-key": key}))` — the structured path is blocked, see the note under the table |
| `fal-client` 1.0.0 | **Yes** | `submit`/`run`/`subscribe` all take `headers=`, and httpx request headers override the client's `Authorization` |
| `huggingface_hub` 1.16.1 | **No** | `token` is constructor-only; `text_to_image` exposes no header or token parameter |
| `linkup-sdk` 0.13.0 | **No** | `api_key` is constructor-only; no operation takes headers |
| `boto3` / `aioboto3` (Bedrock) | **No** | Credentials belong to the session/client; needs a fresh client per credential set |
| `azure_rest` img-gen (our own httpx code) | **Yes** | We build the `Api-Key` header ourselves (`azure_img_gen_worker.py:150`) |
| `docling`, `pypdfium2` | N/A | Local, no credential |

### Details worth knowing

**`openai` — `with_options` is cheap.** `AsyncOpenAI.copy()` (aliased as `with_options`) ends with `http_client = http_client or self._client`, so a per-key clone shares the connection pool and only re-wraps the options. This is the clean route for the instructor-wrapped paths, where `extra_headers` is available but a per-key `instructor` wrapper would still need rebuilding.

**`openai` also accepts a callable key provider — do not use it as-is.** Since 2.x, `api_key` may be a `Callable[[], Awaitable[str]]`, invoked from `_prepare_options` before every request. But `_refresh_api_key` assigns to `self.api_key` on the *shared* client, and the header is built afterwards in `_build_request`, with an `await` in between. Two concurrent requests wanting different keys on the same client instance will race, and the loser sends the wrong tenant's key. In a concurrent runtime this is a silent cross-tenant credential leak, not a flaky test. `with_options` has no such window because each clone owns its own `api_key` attribute.

**`mistralai`'s callable is safe, unlike openai's.** `Mistral(api_key=callable)` wraps it as `lambda: Security(api_key=api_key())` and the generated request builder calls it fresh per request into a local variable — no shared mutation (`sdk.py:115`, `basesdk.py:181`). Alternatively `http_headers` is applied *last* in the header merge (`basesdk.py:209`), so it cleanly overrides the security header.

**`fal` per-request headers really do win.** The client-level `Authorization` sits on the httpx client; httpx merges request headers over client headers with replacement semantics, verified empirically. So `headers={"Authorization": f"Key {key}"}` on `submit` overrides it. Our Fal worker does not currently pass `headers` (`fal_img_gen_worker.py:59`), so this is an added argument, not a redesign.

**`google-genai` — the native path can, the structured path cannot.** `generate_content(config=…)` accepts `http_options`, and per-call headers are merged over the client's defaults with the patch winning (`_api_client.patch_http_options`), so overriding `x-goog-api-key` per request works on `_gen_text`. The structured path goes through `instructor`'s genai adapter, whose kwarg mapping copies only a whitelist of OpenAI-named fields into the config it builds — `http_options` is not in it, and nothing outside the whitelist survives. So Gemini structured generation needs a per-credential `genai.Client` and therefore a per-credential `from_genai` wrapper. That same mapping is the subject of a separate defect: see `wip/google-structured-config-dropped-and-vertex-token-stale.md`.

**The three that cannot do it** — HuggingFace, Linkup, Bedrock — all need a **client per credential**, which means the `SdkClientRegistry` cache key has to grow a credential dimension for them regardless. Bedrock is the heaviest: `BedrockClientBoto3` builds a boto3 client in `__init__`, and `BedrockClientAioboto3` holds an `aioboto3.Session`. Neither is expensive enough to worry about at per-org granularity, but both are far too expensive per request, so the credential-scoped cache is mandatory rather than optional there.

## 5. What this suggests

Two mechanisms cover everything, and the split is not per-SDK, it is per-*capability*:

- **Header/option override on the request** for openai, Azure OpenAI, anthropic, mistral, portkey, gateway, fal, azure_rest. Nothing is cached per credential; the existing single client stays. For the Gateway path specifically this is close to a one-line change, since `make_extras` already returns the header dict that gets sent.
- **A credential-scoped client cache** for HuggingFace, Linkup, Bedrock, and the Google structured-output path. Concretely: extend `ModelHandle.sdk_handle` (or the registry key) with a credential fingerprint, so `get_or_create` builds one client per (model handle, credential) pair. Fingerprint, never the key itself, so the cache key is not a secret.

Whichever seam a given provider uses, the *decision* is the same and stays payload-first: reference on the job → resolved to material in-process → handed to the worker.

## 6. Open questions

1. **What is the reference we put on the payload?** An org id (server resolves to that org's stored key), a profile id (the BYOK inference-profile design), or a key id? This determines the shape of the secrets-provider scope change.
2. **Do we support per-request keys for all backends or only the Gateway?** Gateway-only is dramatically cheaper — one header, no cache changes, no per-SDK work — and covers the hosted product. All-backends is what BYOK-with-your-own-provider-keys requires.
3. **Where does resolution happen relative to Temporal?** If the worker resolves the reference, the secret never enters workflow history. If the dispatcher resolves it, it does. The first is the only safe answer, and it constrains where the secrets provider must be reachable.
4. **Does `InferenceBackend` stay a boot-time singleton?** If a per-request key can also imply a per-request *endpoint* (self-hosted, regional, Azure resource), then the override is a backend override, not a key override, and the design is meaningfully larger.
