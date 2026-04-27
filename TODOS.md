# TODOs

## Refactor: Unify OpenAI img-gen onto `ImgGenArgsFactory.make_args_for_model()`

**Goal.** Make `OpenAIImgGenWorker` rule-driven the same way `AzureImgGenWorker` is, so all topics (not just `background`) are honored consistently across both backends. Behavior comes from per-model TOML rules; the worker only dispatches to the OpenAI SDK.

**Status.** The translation call site is in place — `pipelex/plugins/openai/openai_img_gen_worker.py:57-62` and `pipelex/plugins/azure_rest/azure_img_gen_worker.py:73-78` both call `ImgGenArgsFactory.make_args_for_model(...)`. The unification surfaced four follow-ups that must land before the refactor is complete: three default-behavior regressions (Phase A) and one edit-endpoint SDK incompatibility (Phase B).

### Phase A — Restore the implicit defaults the bespoke worker was holding

- **A.1 — `quality` default = `medium` for the GPT inference taxonomy.** `pipelex/cogt/img_gen/img_gen_args_factory.py:402-404`.
  - Old worker forced `Quality.LOW` when `job_params.quality` was None; the new flow leaves `quality` unset and the OpenAI API picks its own default (medium/auto), making calls more expensive without test coverage of the change.
  - Change `case InferenceTaxonomy.GPT: if quality: args_dict["quality"] = quality.value` to `args_dict["quality"] = (quality or Quality.MEDIUM).value`. Use medium (not low) so all OpenAI img-gen models share a single explicit default.
  - Unit test in `tests/unit/pipelex/cogt/img_gen/test_img_gen_args_factory.py`: assert `args["quality"] == "medium"` when `quality is None` for `InferenceTaxonomy.GPT`.
  - CHANGELOG `[Unreleased]`: "OpenAI direct img-gen now defaults `quality` to `medium`; previously this path implicitly defaulted to `low`."

- **A.2 — `output_format=None` no longer coerced to PNG.** `pipelex/cogt/img_gen/img_gen_args_factory.py:131-138` and `:436-477`.
  - Drop the `or ImageFormat.PNG` in the topic-loop call site.
  - Widen the signature: `make_args_from_output_format(output_format: ImageFormat | None)`. For each taxonomy arm (`SDXL`, `FLUX_1`, `FLUX_2`, `GPT`), when `output_format is None`, return `{}` so the provider applies its own default. `UNAVAILABLE` already returns `{}`.
  - Unit tests: parametrize each taxonomy with `output_format=None` and assert no `format`/`output_format` key in the result.

- **A.3 — Add an `output_compression` topic.** `pipelex/plugins/openai/openai_img_gen_worker.py` previously hardcoded `output_compression=100`; the new flow drops it silently. PNG is unaffected (lossless), but JPEG/WEBP outputs from OpenAI will silently change quality.
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

- **B.1 — Strip `moderation` before `images.edit()`.** Verified via `inspect.signature(openai.AsyncOpenAI(...).images.edit)`: `moderation` is in the `images.generate()` signature but **not** in `images.edit()`. Today the legacy GPT image rules carry `safety_checker = "openai_moderation"`, so any call with `input_images=[...]` + `is_moderated=True` will raise `TypeError` from the SDK as soon as the worker routes to the edit branch (`pipelex/plugins/openai/openai_img_gen_worker.py:64-66`).
  - Fix in `openai_img_gen_worker._gen_image_list`: in the edit branch, `args_dict.pop("moderation", None)` before the `images.edit(**args_dict)` call, with a `log.warning("OpenAI images.edit does not accept 'moderation'; dropping the kwarg")` when it was set.
  - Rationale for keeping the fix in the worker (not in the rules / taxonomies): rules describe **model** capability; this is an **endpoint** quirk that should not leak into the taxonomy.
  - Unit test in `test_img_gen_args_factory.py` (or a new `test_openai_img_gen_worker.py`): build a job with `is_moderated=True` + `input_images=[...]` for `gpt-image-1`, mock both `images.edit` and `images.generate`, assert `images.edit` was awaited and that `moderation` is NOT in the kwargs.
  - `gpt-image-2*` already has `safety_checker = "unavailable"`, so the legacy family is the only affected one.

### Phase C — Verifications & cleanup

- **C.1 — Boot + targeted tests after every step.** `make tb` for config-boot sanity, `make agent-check` for linting/typing, then targeted:

    ```bash
    .venv/bin/pytest -n auto \
      -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
      -o log_level=WARNING --tb=short -q \
      tests/unit/pipelex/cogt/ tests/unit/pipelex/plugins/ tests/integration/pipelex/cogt/
    ```

- **C.2 — Live integration probe (`gha_disabled`).** Once mocks pass, exercise the OpenAI direct + Azure + edit paths against real APIs for `gpt-image-1`, `gpt-image-1-mini`, `gpt-image-1.5`, and `gpt-image-2`. Cover text-to-image opaque, text-to-image transparent (skip on `UNAVAILABLE`), and image-edit with and without `is_moderated`.

- **C.3 — Delete orphaned helpers in `OpenAIImgGenFactory`** (`pipelex/plugins/openai/openai_img_gen_factory.py`). After the refactor these are unreferenced (verified by grep across the repo):
  - `output_format_for_openai_image` (line 121)
  - `quality_for_openai_image` (line 141)
  - `background_for_openai_image` (line 151)
  - `output_compression_for_openai_image` (line 169) — delete once Phase A.3 inlines the `100` constant in `make_args_from_output_compression`.

  Keep (still referenced by `ImgGenArgsFactory`): `size_for_legacy_openai_image`, `size_for_gpt_image_2`, `moderation_for_openai_image`, `input_fidelity_for_openai_image`.

  Re-run `make agent-check` to confirm no dangling imports.

### Phase D — Test ergonomics

- **D.1 — `test_img_gen_single_transparent` auto-skip via rules, project-standard.** `tests/integration/pipelex/cogt/test_img_gen.py:67-69` already short-circuits when `BackgroundTaxonomy.UNAVAILABLE`, but uses raw enum-value equality (`rules.get(...) == BackgroundTaxonomy.UNAVAILABLE`) which violates the project Python standard ("Never test equality to an enum value: use match/case"). Convert to:

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

1. **A.1** (quality default + CHANGELOG) — small, isolated.
2. **A.2** (output_format None propagation) — small, isolated.
3. **B.1** (edit-endpoint moderation strip) — bug fix, lands quickly.
4. **A.3** (output_compression topic) — bigger; taxonomy + factory + TOML + tests in lockstep.
5. **C.3** (cleanup orphaned helpers) — once Phase A.3 lands and nothing else references them.
6. **D.1** (test standards cleanup) — drive-by polish.

### Risks

- **Silent API behavior change for direct OpenAI callers.** Defaults shifted from `low` quality / forced PNG / `output_compression=100` to rule-driven. Mitigated by CHANGELOG `[Unreleased]` (A.1) and uniform `medium` default.
- **TOML / Python / kit configs drift.** Each new topic must move in lockstep across `.pipelex/`, `pipelex/kit/configs/`, and the Python enum. Mitigated by `make tb` after every TOML edit.
- **Edit-endpoint regressions are latent for users on `gpt-image-1*`.** The old bespoke worker never hit the edit branch (it only called `images.generate()`); the new code added the edit branch and exposed the `moderation` gap. The fix must precede any production rollout where input-image edits are enabled.

---

## Independent cleanup (not blocked by the refactor)

- **`AspectRatioTaxonomy.GPT` is dead.** `pipelex/cogt/img_gen/img_gen_model_rules.py:86` and `pipelex/cogt/img_gen/img_gen_args_factory.py:309`. No TOML in `.pipelex/` or `pipelex/kit/configs/` uses `aspect_ratio = "gpt"` anymore — all migrated to `openai_gpt_image_legacy` or `openai_gpt_image_2`. Remove the `GPT` enum value and drop `GPT |` from the `case AspectRatioTaxonomy.GPT | AspectRatioTaxonomy.OPENAI_GPT_IMAGE_LEGACY:` match arm.

### Naming consistency — rename `gpt` → `gpt_image_legacy` where it refers only to the legacy gpt-image models

The `"gpt"` taxonomy value is ambiguous now that gpt-image-2 has its own taxonomies. Where the rule is **legacy-only**, rename to the shorter `gpt_image_legacy` (not `openai_gpt_image_legacy`). Where the rule is **shared** between legacy and gpt-image-2, leave it alone.

- **Rename:**
  - `OutputFormatTaxonomy.GPT = "gpt"` (`pipelex/cogt/img_gen/img_gen_model_rules.py:148-149`) → `GPT_IMAGE_LEGACY = "gpt_image_legacy"` (gpt-image-2 uses `OutputFormatTaxonomy.UNAVAILABLE`, so `GPT` here is legacy-only).
  - `AspectRatioTaxonomy.GPT = "gpt"` (`pipelex/cogt/img_gen/img_gen_model_rules.py:86`) — already flagged for removal as dead code; if kept for any reason, rename to `GPT_IMAGE_LEGACY` for consistency.
  - Optional: rename `AspectRatioTaxonomy.OPENAI_GPT_IMAGE_LEGACY` → `GPT_IMAGE_LEGACY` and `AspectRatioTaxonomy.OPENAI_GPT_IMAGE_2` → `GPT_IMAGE_2` (drop the `OPENAI_` prefix, since the file/class context already implies OpenAI).

- **Do NOT rename** (these taxonomies are shared by gpt-image-1, -1.5, AND gpt-image-2):
  - `NumImagesTaxonomy.GPT` — both legacy and gpt-image-2 use `num_images = "gpt"` (param `n`).
  - `InferenceTaxonomy.GPT` — both legacy and gpt-image-2 use `inference = "gpt"` (param `quality`).

- **TOML updates required (if renaming):** every `output_format = "gpt"` in `.pipelex/inference/backends/*.toml` and `pipelex/kit/configs/inference/backends/*.toml` must be updated in lockstep with the enum rename.

---

## TODO Later — out of scope for now

- Azure deployment for `gpt-image-2` is not available yet so we can't test it.
- `safety_checker` failures on OpenAI direct: the `nude`-tier tests reject; investigate whether the model needs a different `safety_checker` rule (or whether the test fixtures should skip this tier for gpt-image-2).
- Add `gpt-image-2` to the remote Pipelex Gateway config (cannot be done from this repo).
