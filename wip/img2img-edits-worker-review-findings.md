# img2img /edits worker — code review findings

xhigh-effort workflow review (`/code-review`) of the staged changes adding GPT Image `/images/edits` (img2img) support across the Azure REST and Gateway workers. 9 findings survived independent verification (4 CONFIRMED, 5 PLAUSIBLE).

Reviewed diff: `git diff --cached` at the time of review, covering:
- `.pipelex/inference/backends/azure_openai.toml`
- `pipelex/cogt/img_gen/img_gen_args_factory.py`
- `pipelex/kit/configs/inference/backends/azure_openai.toml`
- `pipelex/plugins/azure_rest/azure_img_gen_worker.py`
- `pipelex/plugins/gateway/gateway_img_gen_worker.py`
- `pipelex/plugins/openai/openai_img_gen_worker.py`
- `tests/integration/pipelex/cogt/test_img2img.py`
- `tests/unit/pipelex/cogt/img_gen/test_img_gen_args_input_images.py`
- `tests/unit/pipelex/plugins/gateway/test_gateway_img_gen_worker_edit_routing.py` (new)

## Confirmed showstoppers

### 1. ✅ RESOLVED — `pipelex/plugins/gateway/gateway_img_gen_worker.py:91` — endpoint-path derivation raises for the standard model_id convention
The `/images/edits` route derivation assumes `endpoint_path` literally contains the substring `"/images/generations"`, but the worker's own fallback (and its sibling test file `test_gateway_img_gen_worker_semantic.py`) build `endpoint_path` as `f"/{model_id}"` (e.g. `"/gpt-image-1"`), which never contains that substring.

**Failure scenario:** With `extra_headers={}` and `model_id="gpt-image-1"` (the naming convention used by every other model spec and by this same worker's existing test suite), `endpoint_path="/gpt-image-1"`, then `edits_endpoint_path = endpoint_path.replace("/images/generations", "/images/edits", 1)` returns the identical string, tripping the `edits_endpoint_path == endpoint_path` guard and raising `ImgGenParameterError("Could not derive an /images/edits route from endpoint path '/gpt-image-1'")` for every img2img request through the Gateway.

**Resolution:** Fixed config-side, not code-side. The production gateway config never hit this (its `model_id` smuggled the full `/images/generations?...` route, so the derivation happened to work), but the trap was real for the standard bare-`model_id` convention. The remote config (`pipelex-back-office/pipelex_back_office/remote_config/gateway_models.toml`, per-env deploy) now sets the explicit `endpoint_path` key on `[gpt-image-1]` — the escape hatch the worker has honored since v0.18.0, already used by the Azure Flux entries — and `model_id` is back to the bare deployment name. Version-skew-safe: the new `endpoint_path` value is the old `f"/{model_id}"` value minus the leading slash (portkey delegates URL merging to httpx, whose `base_url.raw_path + url.lstrip("/")` merge makes the two forms equivalent), so clients ≥ 0.18.0 build identical requests. The GPT Image mini entry also gained the img2img config (`inputs = ["text", "images"]` + `input_images = "gpt_image"`), matching its Azure REST counterpart. The worker's derivation + loud `ImgGenParameterError` stays as the guard against misconfigured specs; no `edits_endpoint_path` override until a provider needs a non-derivable route.

### 2. ✅ RESOLVED — `pipelex/plugins/gateway/gateway_img_gen_worker.py:95` — wrong multipart field name drops multi-image input
The sync-client multipart fallback for GPT Image edits builds `("image", image_file)` parts instead of `("image[]", image_file)`, so multi-image edits routed through the Gateway will not carry more than one image to the provider.

**Failure scenario:** A caller supplies 2+ input images to a GPT Image model routed through the Gateway. `multipart_fields = [("image", image_file) for image_file in image_files]` sends every image under the bare `"image"` key. The downstream OpenAI-compatible endpoint (which expects `"image[]"` for arrays) receives several conflicting single-image fields; only the last one is honored (or the call is rejected), so earlier input image(s) are silently dropped.

**Resolution:** Confirmed against the openai SDK's own multipart serialization (`extract_files` with `array_format="brackets"`, paths `[["image"], ["image", "<array>"], ["mask"]]`): a single file is sent as the bare `image` field, every element of a list as `image[]`. The worker now picks the field name by count — `image[]` when 2+ images, bare `image` for a single image (kept for maximal compatibility with legacy single-image edit endpoints). Covered by a new multi-image case in `test_gateway_img_gen_worker_edit_routing.py` asserting the `image[]` parts and the absence of bare `image` keys. Finding 5 (same bug in the Azure REST worker) is fixed separately.

### 3. ✅ RESOLVED — `pipelex/plugins/gateway/gateway_img_gen_worker.py:100` — unclosed per-request Portkey client leaks connections
The throwaway sync `Portkey` client built for every img2img/edit call is never closed, leaking its underlying `httpx.Client` connection pool.

**Failure scenario:** `portkey_ai`'s `Portkey` class opens an `httpx.Client` internally and exposes `close()`/`is_closed` for callers to release it; the new code constructs `Portkey(base_url=..., api_key=..., debug=...)` and lets it go out of scope after the single `post()` call, with no `with`/try-finally. Under sustained img2img traffic, each request opens a fresh `httpx.Client` whose sockets are only reclaimed whenever GC happens to collect the object — under load this can exhaust file descriptors or leave many idle sockets open. (Source inspection showed it was actually two leaked pools per request: the throwaway `Portkey`'s own `httpx.Client` plus the internal one opened by the vendored sync `OpenAI` client it constructs at init.)

**Resolution:** The throwaway sync client is gone entirely. Verified at source level that `AsyncPortkey.post(..., files=...)` is broken on every released portkey-ai (2.3.0 through 2.3.2: the async `AsyncAPIClient._build_request()` omits `files=options.files` while the sync one passes it) and on current GitHub main — so a version bump was no way out. The edit call now routes through the vendored `AsyncOpenAI` client the worker's `AsyncPortkey` already carries (`portkey_client.openai_client.post(...)`): fully async (no `asyncio.to_thread`), same base_url, Portkey auth headers baked in as `default_headers`, long-lived shared connection pool (no per-request client at all), custom edits endpoint path preserved, per-request `x-portkey-config` header passed via request options. Scalar args travel as `body` and are serialized to multipart form fields by the openai SDK. A `# TODO` in the worker tracks the upstream one-line fix (PR `files=options.files` into portkey's async `_build_request`) and restoring the plain `with_options(config=...).post(url=..., files=...)` call once it ships — commit `2d4ae4ecb71116e942c0adf2e6516de4b42f0614` holds the pre-change state and analysis.

### 4. `tests/integration/pipelex/cogt/test_img2img.py:35` — JPG single-image test silently commented out
The single-input-image JPG img2img test case was commented out (not fixed or deleted with explanation) rather than kept passing, silently dropping coverage for JPG input in the single-image edit path.

**Failure scenario:** A regression specific to JPG single-file input images in the new GPT_IMAGE edit flow (e.g. an extension/mime mismatch in the new `(filename, bytes, mime_type)` tuple construction in `img_gen_args_factory.py`, or a provider-side rejection of JPG on `/images/edits`) would no longer be caught by CI: the analogous multi-image JPG cases (`MULTIPLE_INPUT_IMAGES`) still run, but the single-JPG-file scenario silently stops being exercised.

## Plausible (latent / config-gated)

### 5. ✅ RESOLVED — `pipelex/plugins/azure_rest/azure_img_gen_worker.py:147` — same field-naming bug on the Azure REST worker
Multipart image-edit request always uses the field name `"image"` for every file, but the OpenAI/Azure `/images/edits` API requires the array field name `"image[]"` when more than one image is submitted (confirmed against OpenAI's official API reference and Azure OpenAI REST examples).

**Failure scenario:** A user runs img2img with two input images (exercised by the still-active `MULTIPLE_INPUT_IMAGES` cases in `tests/integration/pipelex/cogt/test_img2img.py`, e.g. "Two JPG files"). `files=[("image", image_file) for image_file in image_files]` posts two multipart parts both named `"image"` instead of `"image[]"`. Azure's REST endpoint either rejects the request or (more likely, since most multipart parsers keep only the last value for a repeated non-array key) silently drops all but the last image.

**Resolution:** Same fix as finding 2 — the field name is picked by count (`image[]` when 2+ images, bare `image` for a single image, matching the openai SDK's `extract_files` serialization). Covered by the new `tests/unit/pipelex/plugins/azure_rest/test_azure_img_gen_worker_edit_routing.py`, which asserts the edits/generations routing, the multipart field naming for both single and multiple images, and the scalar-args `data` payload.

### 6. `pipelex/plugins/azure_rest/azure_img_gen_worker.py:146` — 'moderation' arg not stripped before Azure edits call
New Azure `/images/edits` multipart path forwards every scalar arg (including `moderation`) without dropping it, unlike the parallel OpenAI-direct worker which explicitly strips `moderation` before calling `images.edit`.

**Failure scenario:** `openai_img_gen_worker.py` (unchanged in this diff) pops `moderation` before calling `images.edit` because "OpenAI images.edit does not accept moderation" (its own comment) — that guard exists precisely because `gpt-image-1`/`1-mini`/`1.5` on the OpenAI backend already ship with `safety_checker="openai_moderation"` + `input_images="gpt_image"`. This diff adds an equivalent img2img (edits) code path to `azure_img_gen_worker.py` and `gateway_img_gen_worker.py` for the same GPT_IMAGE taxonomy/args_dict shape, but neither strips `moderation`. Today the Azure entries this diff enables all have `safety_checker="unavailable"`, so `moderation` never lands in `args_dict` for them yet — but the moment any GPT_IMAGE Azure/gateway model rule reuses `safety_checker="openai_moderation"` (the same taxonomy already active on the OpenAI backend for these very model names), every img2img request sent through the Azure REST or Gateway worker will include an unexpected `moderation` field in the multipart body and the provider will reject it with a 400.

### 7. `pipelex/plugins/azure_rest/azure_img_gen_worker.py:146` (+ duplicated at `pipelex/plugins/gateway/gateway_img_gen_worker.py:96`) — blanket `str(value)` mis-serializes bools
Blanket `str(value)` over every remaining `args_dict` entry for the multipart `/images/edits` request silently mis-serializes non-string scalars (notably Python bools stringify to `"True"`/`"False"`, not the lowercase `"true"`/`"false"` an HTTP API expects). Same root cause duplicated in the Gateway worker.

**Gateway half resolved as a side effect of the finding-3 fix:** the Gateway edit path no longer stringifies scalars at all — they travel as `body` through the vendored openai SDK's multipart serializer, which lowercases bools and brackets arrays. The Azure REST worker's `str(value)` remains open.

**Failure scenario:** The moment a GPT Image model's `safety_checker` rule is anything other than today's hardcoded `"unavailable"` (e.g. `available`, which yields `args_dict["enable_safety_checker"] = True/False`) while `input_images = "gpt_image"` is also set, the img2img/edit request sends the multipart field as `("enable_safety_checker", (None, "True"))` — capitalized, non-JSON-boolean — so Azure's/the Gateway's `/images/edits` endpoint either rejects the request with a 400 or silently ignores/misreads the flag, breaking image editing for that model after only a one-line TOML rule flip.

### 8. ✅ RESOLVED — `pipelex/plugins/gateway/gateway_img_gen_worker.py:102` — hand-duplicated Portkey client construction
The image-edit code path builds a brand-new sync `Portkey` client from only 3 hand-picked fields (`base_url`, `api_key`, `debug`) instead of delegating through the already-configured `self.portkey_client`, so any other client-level configuration silently doesn't apply to edit requests.

**Failure scenario:** `self.portkey_client` is currently built by `GatewayFactory.make_portkey_client()`, which only sets `base_url`/`api_key`/`debug`, so today the two clients happen to match. But the moment any of Portkey's other constructor parameters is added to the async client's construction (e.g. the tracing/metadata support flagged by an adjacent `# TODO: add portkey tracing headers when enabled` comment, or a future virtual-key/provider override), plain image-generation calls (which reuse `self.portkey_client`) will carry it while every img2img/edit call (routed through this freshly-built sync client) silently drops it — producing wrong-provider routing, missing trace correlation, or an auth failure that only reproduces when an input image is supplied.

**Resolution:** Resolved by the finding-3 fix. The hand-built sync client is gone; the edit path now goes through `self.portkey_client.openai_client`, which portkey constructs from the async client's own `allHeaders` at init — so client-level configuration added to the async client's construction flows to edit requests automatically.

## Priority fix order

Finding 1 (Gateway endpoint-path bug) is RESOLVED via the remote gateway config (explicit `endpoint_path` key). Findings 2 and 5 (`image[]` field naming on the Gateway and Azure REST workers) are RESOLVED in code. Findings 3 and 8 (throwaway sync Portkey client: leak + hand-duplicated construction) are RESOLVED in code — the edit path now routes through the vendored `AsyncOpenAI` client the worker's `AsyncPortkey` carries, with a `# TODO` tracking the upstream portkey fix that would let us restore the plain async portkey call. Finding 7's Gateway half is resolved as a side effect (SDK-serialized multipart scalars); its Azure half remains. Finding 4 (commented-out test) should be un-commented or explained now that #2/#5 are fixed, since it likely exists to sidestep a currently-broken path. Finding 6 and the Azure half of 7 are latent/config-gated — worth fixing but not urgent until the relevant TOML config combination is introduced.
