# TODOs

## Refactor: Unify OpenAI img-gen onto `ImgGenArgsFactory.make_args_for_model()`

**Goal.** Make `OpenAIImgGenWorker` rule-driven the same way `AzureImgGenWorker` is, so all topics (not just `background`) are honored consistently across both backends. Behavior comes from per-model TOML rules; the worker only dispatches to the OpenAI SDK.

**Status.** The translation call site is in place — `pipelex/plugins/openai/openai_img_gen_worker.py:57-62` and `pipelex/plugins/azure_rest/azure_img_gen_worker.py:73-78` both call `ImgGenArgsFactory.make_args_for_model(...)`. The unification surfaced four follow-ups that must land before the refactor is complete: three default-behavior regressions (Phase A) and one edit-endpoint SDK incompatibility (Phase B).

### Phase A — Restore the implicit defaults the bespoke worker was holding

- [x] **A.1 — `quality` default = `medium` for the GPT inference taxonomy.** `pipelex/cogt/img_gen/img_gen_args_factory.py:402-404`.
  - Old worker forced `Quality.LOW` when `job_params.quality` was None; the new flow leaves `quality` unset and the OpenAI API picks its own default (medium/auto), making calls more expensive without test coverage of the change.
  - Change `case InferenceTaxonomy.GPT: if quality: args_dict["quality"] = quality.value` to `args_dict["quality"] = (quality or Quality.MEDIUM).value`. Use medium (not low) so all OpenAI img-gen models share a single explicit default.
  - Unit test in `tests/unit/pipelex/cogt/img_gen/test_img_gen_args_factory.py`: assert `args["quality"] == "medium"` when `quality is None` for `InferenceTaxonomy.GPT`.
  - CHANGELOG `[Unreleased]`: "OpenAI direct img-gen now defaults `quality` to `medium`; previously this path implicitly defaulted to `low`."

- [x] **A.2 — `output_format=None` no longer coerced to PNG.** `pipelex/cogt/img_gen/img_gen_args_factory.py:131-138` and `:436-477`.
  - Drop the `or ImageFormat.PNG` in the topic-loop call site.
  - Widen the signature: `make_args_from_output_format(output_format: ImageFormat | None)`. For each taxonomy arm (`SDXL`, `FLUX_1`, `FLUX_2`, `GPT`), when `output_format is None`, return `{}` so the provider applies its own default. `UNAVAILABLE` already returns `{}`.
  - Unit tests: parametrize each taxonomy with `output_format=None` and assert no `format`/`output_format` key in the result.

- [x] **A.3 — Add an `output_compression` topic.** `pipelex/plugins/openai/openai_img_gen_worker.py` previously hardcoded `output_compression=100`; the new flow drops it silently. PNG is unaffected (lossless), but JPEG/WEBP outputs from OpenAI will silently change quality.
  - `pipelex/cogt/img_gen/img_gen_model_rules.py`: add `ImgGenArgTopic.OUTPUT_COMPRESSION = "output_compression"` and a new `OutputCompressionTaxonomy(StrEnum)` with `GPT_IMAGE = "gpt_image"` (emits `100`) and `UNAVAILABLE = "unavailable"` (no-op).
  - `pipelex/cogt/img_gen/img_gen_args_factory.py`: add `make_args_from_output_compression(...)` and a dispatch arm in `make_args_for_model`'s topic loop. The constant `100` lives inside the new method (no need to keep `OpenAIImgGenFactory.output_compression_for_openai_image`).
  - TOML lockstep — every `gpt-image-1`, `gpt-image-1-mini`, `gpt-image-1.5` block in:
    - `.pipelex/inference/backends/openai.toml`
    - `.pipelex/inference/backends/azure_openai.toml`
    - `pipelex/kit/configs/inference/backends/openai.toml`
    - `pipelex/kit/configs/inference/backends/azure_openai.toml`

    gets `output_compression = "gpt_image"`. `gpt-image-2` and `gpt-image-2-2026-04-21` blocks get `output_compression = "unavailable"`.
  - Unit tests: assert `output_compression == 100` for legacy rules; assert key absent when taxonomy is `UNAVAILABLE`.
  - `make tb` after TOML changes.

### Phase B — Edit-endpoint kwarg compatibility

- [x] **B.1 — Strip `moderation` before `images.edit()`.** Verified via `inspect.signature(openai.AsyncOpenAI(...).images.edit)`: `moderation` is in the `images.generate()` signature but **not** in `images.edit()`. Today the legacy GPT image rules carry `safety_checker = "openai_moderation"`, so any call with `input_images=[...]` + `is_moderated=True` will raise `TypeError` from the SDK as soon as the worker routes to the edit branch (`pipelex/plugins/openai/openai_img_gen_worker.py:64-66`).
  - Fix in `openai_img_gen_worker._gen_image_list`: in the edit branch, `args_dict.pop("moderation", None)` before the `images.edit(**args_dict)` call, with a `log.warning("OpenAI images.edit does not accept 'moderation'; dropping the kwarg")` when it was set.
  - Rationale for keeping the fix in the worker (not in the rules / taxonomies): rules describe **model** capability; this is an **endpoint** quirk that should not leak into the taxonomy.
  - Unit test in `test_img_gen_args_factory.py` (or a new `test_openai_img_gen_worker.py`): build a job with `is_moderated=True` + `input_images=[...]` for `gpt-image-1`, mock both `images.edit` and `images.generate`, assert `images.edit` was awaited and that `moderation` is NOT in the kwargs.
  - `gpt-image-2*` already has `safety_checker = "unavailable"`, so the legacy family is the only affected one.

### Phase C — Verifications & cleanup

- [x] **C.1 — Boot + targeted tests after every step.** `make tb` for config-boot sanity, `make agent-check` for linting/typing, then targeted:

    ```bash
    .venv/bin/pytest -n auto \
      -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
      -o log_level=WARNING --tb=short -q \
      tests/unit/pipelex/cogt/ tests/unit/pipelex/plugins/ tests/integration/pipelex/cogt/
    ```

- [x] **C.2 — Live integration probe (`gha_disabled`).** Exercised OpenAI direct + Azure + edit paths against real APIs for `gpt-image-1`, `gpt-image-1-mini`, `gpt-image-1.5`, and `gpt-image-2`. Covered text-to-image opaque, text-to-image transparent (auto-skips on `UNAVAILABLE`), and image-edit. Aspect-ratio mismatches (legacy + landscape_4_3 / portrait_9_16) now skip gracefully via the new `ImgGenParamSupport` helper, replacing the previous noisy failures.

- [x] **C.3 — Delete orphaned helpers in `OpenAIImgGenFactory`** (`pipelex/plugins/openai/openai_img_gen_factory.py`). After the refactor these are unreferenced (verified by grep across the repo):
  - `output_format_for_openai_image` (line 121)
  - `quality_for_openai_image` (line 141)
  - `background_for_openai_image` (line 151)
  - `output_compression_for_openai_image` (line 169) — delete once Phase A.3 inlines the `100` constant in `make_args_from_output_compression`.

  Keep (still referenced by `ImgGenArgsFactory`): `size_for_legacy_openai_image`, `size_for_gpt_image_2`, `moderation_for_openai_image`, `input_fidelity_for_openai_image`.

  Re-run `make agent-check` to confirm no dangling imports.

### Phase D — Test ergonomics

- [x] **D.1 — `test_img_gen_single_transparent` auto-skip via rules, project-standard.** `tests/integration/pipelex/cogt/test_img_gen.py:67-69` already short-circuits when `BackgroundTaxonomy.UNAVAILABLE`, but uses raw enum-value equality (`rules.get(...) == BackgroundTaxonomy.UNAVAILABLE`) which violates the project Python standard ("Never test equality to an enum value: use match/case"). Convert to:

    ```python
    background_value = rules.get(ImgGenArgTopic.BACKGROUND) if rules else None
    if background_value is not None:
        match BackgroundTaxonomy(background_value):
            case BackgroundTaxonomy.UNAVAILABLE:
                pytest.skip(f"Model '{...}' does not support transparent background")
            case BackgroundTaxonomy.AVAILABLE:
                pass
    ```

### Suggested commit order

1. [x] **A.1** (quality default + CHANGELOG) — small, isolated.
2. [x] **A.2** (output_format None propagation) — small, isolated.
3. [x] **B.1** (edit-endpoint moderation strip) — bug fix, lands quickly.
4. [x] **A.3** (output_compression topic) — bigger; taxonomy + factory + TOML + tests in lockstep.
5. [x] **C.3** (cleanup orphaned helpers) — once Phase A.3 lands and nothing else references them.
6. [x] **D.1** (test standards cleanup) — drive-by polish.

### Risks

- **Silent API behavior change for direct OpenAI callers.** Defaults shifted from `low` quality / forced PNG / `output_compression=100` to rule-driven. Mitigated by CHANGELOG `[Unreleased]` (A.1) and uniform `medium` default.
- **TOML / Python / kit configs drift.** Each new topic must move in lockstep across `.pipelex/`, `pipelex/kit/configs/`, and the Python enum. Mitigated by `make tb` after every TOML edit.
- **Edit-endpoint regressions are latent for users on `gpt-image-1*`.** The old bespoke worker never hit the edit branch (it only called `images.generate()`); the new code added the edit branch and exposed the `moderation` gap. The fix must precede any production rollout where input-image edits are enabled.

---

## Refactor: Unify `GoogleImgGenWorker` onto `ImgGenArgsFactory.make_args_for_model()`

**Goal.** Bring the Google nano-banana family inline with the rule-driven flow used by OpenAI / Azure / FAL / HuggingFace / Gateway. Today `pipelex/plugins/google/google_img_gen_worker.py` reads `inference_model.rules` zero times: it directly calls `GoogleImgGenFactory.aspect_ratio_literal()` and `dimensions_for_aspect_ratio_and_size()` and silently drops every other `ImgGenJobParams` field (`size`, `background`, `quality`, `output_format`, `seed`, `is_moderated`, `safety_tolerance`, `nb_steps`, `guidance_scale`, `is_raw`, `input_fidelity`, `input_images`).

**Scope.** Request-side only. The worker still owns the SDK-specific wrapping (`genai_types.GenerateContentConfig` / `ImageConfig`) and response-side dim lookup (since dims are response metadata, not request args).

### Phase G.A — Taxonomy & factory

- [ ] **G.A.1 — Add `AspectRatioTaxonomy.GOOGLE_NANO_BANANA = "google_nano_banana"`.** `pipelex/cogt/img_gen/img_gen_model_rules.py`. New arm in `ImgGenArgsFactory.make_args_from_aspect_ratio` returns `{"aspect_ratio": "<google_ratio_string>"}`, mapping the 8 supported Pipelex aspect ratios to Google's literal strings (`"1:1"`, `"4:3"`, `"3:2"`, `"16:9"`, `"21:9"`, `"3:4"`, `"2:3"`, `"9:16"`) and raising `ImgGenParameterError` for `PORTRAIT_9_21` (already enforced by `GoogleImgGenFactory.aspect_ratio_literal`).
- [ ] **G.A.2 — Decide on `size` handling.** Today the worker hardcodes `size="1K"`, dropping `job_params.size`. Choices:
  - (a) Keep hardcoded `1K` in the worker (status-quo behavior).
  - (b) Add a new `ImgGenArgTopic.SIZE_TIER` topic + `SizeTierTaxonomy.GOOGLE_NANO_BANANA` (values `1K` / `2K` / `4K`) so `nano-banana-pro` users can opt into 2K/4K — useful since `nano-banana-pro` already supports the higher tiers in `GoogleImgGenFactory`. **Recommend (b)** but flag for the user — `ImgGenJobParams.size` is `ImageSize | None`, not a tier; we'd derive the tier from a separate field or extend job params. Land (a) first to keep PR small.
- [ ] **G.A.3 — `PromptTaxonomy.POSITIVE_ONLY` already fits.** No new arm needed; nano-banana doesn't support negative prompts.

### Phase G.B — TOML rules

- [ ] **G.B.1 — Add `[<model>.rules]` blocks** for `nano-banana`, `nano-banana-2`, `nano-banana-pro` in BOTH `.pipelex/inference/backends/google.toml` and `pipelex/kit/configs/inference/backends/google.toml`. Initial set: `model_name = "standard"`, `prompt = "positive_only"`, `aspect_ratio = "google_nano_banana"`. Explicitly omit topics the API doesn't accept (`background`, `output_format`, `quality`, `inference`, `safety_checker`, `input_fidelity`).
- [ ] **G.B.2 — `nano-banana-2` is referenced in TOML but missing from `GoogleImageGenModel` enum** (`google_img_gen_factory.py:14-16`). Add it once we know the actual SDK model id and dim table — or document in the rule that it falls through `dimensions_for_aspect_ratio_and_size` so the user gets a clear error if dims are queried.

### Phase G.C — Worker rewrite

- [ ] **G.C.1 — Read rules in `_gen_image`.** `pipelex/plugins/google/google_img_gen_worker.py:85-115`. Mirror the `OpenAIImgGenWorker` pattern: build `args_dict = await ImgGenArgsFactory.make_args_for_model(model_rules=...)` once, then translate flat kwargs to the nested `genai_types` structure (`ImageConfig(aspect_ratio=args_dict["aspect_ratio"])` → `GenerateContentConfig(image_config=..., response_modalities=["Image"])`). Worker becomes ~40 lines shorter.
- [ ] **G.C.2 — Keep dim lookup local to the worker.** `dimensions_for_aspect_ratio_and_size` still runs in `_gen_image` because the dims are needed for the *response* `ImageSize`, not the request. Source the size tier from job params if G.A.2(b) lands; else hardcoded `"1K"` like today.
- [ ] **G.C.3 — img2img scope decision.** The worker currently silently drops `input_images`. Either (a) enforce explicit error via `ImgGenParamSupport.check_input_images_topic` (rule omits `input_images` topic → helper raises) — **recommended**, parity with OpenAI; or (b) add `InputImagesTaxonomy.GOOGLE_NANO_BANANA` arm + `Part.from_bytes(...)` in the worker if Google nano-banana supports image inputs (pro variant likely does). Land (a) first to lock the contract; (b) is a follow-up enhancement.

### Phase G.D — Cleanup

- [ ] **G.D.1 — Inline / delete `GoogleImgGenFactory.aspect_ratio_literal`.** After G.C.1 lands, the literal mapping moves into `ImgGenArgsFactory.make_args_from_aspect_ratio`'s new `GOOGLE_NANO_BANANA` arm. Either delete `aspect_ratio_literal` or have it call into the new central place (single source of truth). The dim tables stay (still needed for response sizing).
- [ ] **G.D.2 — Update TODOS C.2 matrix** to add a `make tip PROF=test_google TEST=test_img_gen_single_opaque` probe row. The existing `test_google` profile already lists the nano-banana models.

### Verification

- [ ] **G.V.1 — `make agent-check`** + targeted unit suite (`tests/unit/pipelex/cogt/img_gen/`, `tests/unit/pipelex/plugins/`).
- [ ] **G.V.2 — Run `make tip PROF=test_google TEST=test_img_gen_single_opaque`** against the real API. Cover `nano-banana`, `nano-banana-2`, `nano-banana-pro`. The fixture's PORTRAIT_9_16 / LANDSCAPE_4_3 cases should now run (Google supports them) — no skip expected. Today these FAIL because the worker silently produces wrong dims for unsupported ratios (or works by accident).
- [ ] **G.V.3 — Add Google rules to `tests/integration/pipelex/cogt/test_img_gen_param_support.py`** so the "every img-gen model accepts at least one aspect ratio" sanity check exercises Google rules too.

---

## Refactor: Unify `OpenAICompletionsImgGenWorker` onto rule-driven flow

**Goal.** Push the per-backend hardcoded branches in `pipelex/plugins/openai/openai_completions_img_gen_worker.py` (`if backend_name == "pipelex_gateway"` → PNG-only; `if backend_name == "blackboxai"` → JPEG-only) into rules. This worker handles ~15 OpenRouter img-gen models (`flux.2-*`, `gemini-image-*`, `seedream`, `gpt-5-image`, etc.) plus the gateway-completions and blackboxai paths. **Today none of those models have `[model.rules]`.**

**Constraint.** This worker uses `chat.completions.create(messages=...)` — fundamentally different request shape from `images.generate / images.edit`. The current `make_args_for_model` returns flat kwargs (`{"prompt": ..., "aspect_ratio": ...}`); the chat path needs `{"messages": [{"role": "user", "content": [...]}]}`. We won't force the chat shape into the existing factory.

**Approach (recommended: pragmatic Option C — request constraints in rules, message-building stays in worker).** Introduce only the rule pieces that meaningfully eliminate hardcoded branches:

### Phase OCC.A — Output-format constraints in rules

- [ ] **OCC.A.1 — Add `OutputFormatTaxonomy.FORCED_PNG` and `OutputFormatTaxonomy.FORCED_JPEG`.** `pipelex/cogt/img_gen/img_gen_model_rules.py:135-149`. New arms in `ImgGenArgsFactory.make_args_from_output_format`: when `output_format` is None or matches the forced format → return `{}`; otherwise raise `ImgGenParameterError` ("Model X only emits PNG; requested format is WEBP"). The worker reads the resolved format off `job_params.output_format` (defaulted by the rule) for response decoding.
- [ ] **OCC.A.2 — Worker uses the helper.** Replace lines 51-66 of `openai_completions_img_gen_worker.py` with a single `ImgGenArgsFactory.make_args_for_model(...)` call that already validates the format constraint via the new taxonomy. The worker still derives `image_format` for the response-shape branch, but the *enforcement* happens in the factory (uniform error path).

### Phase OCC.B — Models, rules, worker glue

- [ ] **OCC.B.1 — Add `[<model>.rules]` to every `sdk = "openrouter_img_gen"` entry** in `.pipelex/inference/backends/openrouter.toml` and `pipelex/kit/configs/inference/backends/openrouter.toml`. Minimal initial set per model: `model_name = "standard"`, `prompt = "positive_only"`. Per-family additions (Flux 2 vs Gemini-via-router vs GPT-5-image) get their existing taxonomy arms (`OutputFormatTaxonomy.FLUX_2` / `OutputFormatTaxonomy.GPT` etc.) where the chat-completions endpoint actually honors them — verify case-by-case.
- [ ] **OCC.B.2 — Gateway-completions and blackboxai entries (when un-commented) get `output_format = "forced_png"` / `"forced_jpeg"` respectively.** Documents the constraint in TOML and removes both `if backend_name == ...` branches from the worker.
- [ ] **OCC.B.3 — Worker wires the rule call without changing message construction.** `_build_messages_with_images` stays in the worker (chat-message shape doesn't fit the factory's flat-kwargs return type). Worker reads `args_dict["prompt"]` from the rule output for the user-message text content. `extra_body` / `extra_headers` continue to flow through `OpenAICompletionsFactory.make_extras` — that subclass-driven hook (BlackboxaiCompletionsFactory adds `seed`, OpenRouterCompletionsFactory adds `modalities`) is orthogonal to rules and stays as-is.

### Phase OCC.C — Response shape (deferred)

- [ ] **OCC.C.1 — Document but do NOT implement a `ResponseShapeTaxonomy`.** The worker's three response branches (`openai_message.images` / `content as URL` / `content_blocks`) aren't strictly per-backend — they're per-model-version. A rule-system extension that controls *response parsing* (not request building) is genuinely new ground and out of scope for this pass. Note the deferral in the TODOS Later section so we revisit if a fourth response shape lands.

### Phase OCC.D — img2img alignment

- [ ] **OCC.D.1 — Add `input_images = "<chat_msg_arm>"` topic to model rules where the chat endpoint accepts image inputs** (Gemini-via-OpenRouter supports it; verify per-model). The rule presence/absence is what `ImgGenParamSupport.check_input_images_topic` reads — so once rules carry the topic correctly, `skip_if_img_gen_params_unsupported(has_input_images=True)` skips img2img tests on models that lack the capability, just like the unified path does. *Note: no new `InputImagesTaxonomy` value is needed* because the chat-message construction stays in the worker (it doesn't need taxonomy dispatch). The taxonomy presence is purely a capability flag here.

### Phase OCC.E — Verification

- [ ] **OCC.E.1 — `make agent-check`** + targeted tests under `tests/unit/pipelex/plugins/`.
- [ ] **OCC.E.2 — `make tip` over OpenRouter img-gen profiles** (need new profiles in `.pipelex-dev/test_profiles_override.toml`: e.g. `verify_flux_2_pro_openrouter`, `verify_gemini_image_openrouter`). Cover `test_img_gen_single_opaque` and `test_img2img_single_input_image` for each new family.
- [ ] **OCC.E.3 — Confirm no regressions on `nano-banana` via gateway** (if any model still routes through `gateway_completions` after the migration; verify .pipelex/inference/backends/pipelex_gateway.toml comments aren't actually live).

### Out-of-scope alternatives (record only)

- [ ] **OCC.X — Aggressive: parallel `make_messages_for_model()` factory method.** Fully rule-driven message construction, including taxonomy dispatch for img2img message format (data URL vs HTTP URL etc.). Touches `ImgGenArgsFactory` API surface and adds a new entry point. Strictly more powerful than the recommended approach but ~3× the diff and breaks the "factory returns flat kwargs" invariant. Revisit only if a third worker (beyond `OpenAICompletionsImgGenWorker`) starts using the chat-completions image path.

---

## Independent cleanup (not blocked by the refactor)

- [x] **`AspectRatioTaxonomy.GPT` removed** — was used only by the gateway's remote config (which the original TODO author missed); gateway updated in lockstep, enum value dropped, match arm collapsed.

### Naming convention — DONE

Final rule: `gpt_image` = shared by all OpenAI GPT Image models (legacy + gpt-image-2); `gpt_image_legacy` = legacy-only (gpt-image-2 uses `unavailable`).

Renames:
- [x] `AspectRatioTaxonomy.OPENAI_GPT_IMAGE_LEGACY` → `GPT_IMAGE_LEGACY = "gpt_image_legacy"`
- [x] `AspectRatioTaxonomy.OPENAI_GPT_IMAGE_2` → `GPT_IMAGE_2 = "gpt_image_2"`
- [x] `OutputFormatTaxonomy.GPT` → `GPT_IMAGE_LEGACY = "gpt_image_legacy"`
- [x] `OutputCompressionTaxonomy.GPT_IMAGE` → `GPT_IMAGE_LEGACY = "gpt_image_legacy"` (legacy-only)
- [x] `InputFidelityTaxonomy.OPENAI_IMAGE` → `GPT_IMAGE_LEGACY = "gpt_image_legacy"` (legacy-only)
- [x] `NumImagesTaxonomy.GPT` → `GPT_IMAGE = "gpt_image"` (shared)
- [x] `InferenceTaxonomy.GPT` → `GPT_IMAGE = "gpt_image"` (shared)
- [x] `InputImagesTaxonomy.GPT_IMAGE` unchanged (already correct, shared)
- [x] Local backend TOMLs and the remote Pipelex Gateway config (`pipelex-back-office/.../gateway_models.toml`) updated in lockstep.

---

## TODO Later — out of scope for now

- [ ] Azure deployment for `gpt-image-2` is not available yet so we can't test it.
- [ ] `safety_checker` failures on OpenAI direct: the `nude`-tier tests reject; investigate whether the model needs a different `safety_checker` rule (or whether the test fixtures should skip this tier for gpt-image-2).
- [ ] Add `gpt-image-2` to the remote Pipelex Gateway config (cannot be done from this repo).
