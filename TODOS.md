# Remove the `ImgGenPrompt` native concept

**Goal:** Delete `NativeConceptCode.IMG_GEN_PROMPT` (`"ImgGenPrompt"`) — the native *concept* `native.ImgGenPrompt`. It has no business being a native concept: it is structurally identical to `Text` (just a renamed alias), and nothing in the runtime requires it.

**Status:** Not started (plan approved, awaiting go-ahead to execute). Single-session task, low risk, bounded blast radius.

**Branch:** create a feature branch off `dev` (e.g. `refactor/drop-imggenprompt-native-concept`) — do not work directly on `dev`.

**Decisions confirmed (settled — do not re-litigate):**

- Test fixture `multiplicity.mthds` outputs migrate to `Text` (not a locally-redefined `ImgGenPrompt` concept).
- `PipeImgGen.md` doc examples migrate their input concept from `ImgGenPrompt` → `Text` (full doc cleanup, not minimal).

---

## Cold-start context (read this first)

### What `native.ImgGenPrompt` actually is

It's a native concept that carries **zero structural distinction** from `Text`:

- `NativeConceptCode.structure_class` returns `None` for it — no dedicated content class (`pipelex/core/concepts/native/concept_native.py:72-74`).
- `ConceptFactory.make_native_concept` maps it to **`TextContent`** with the description "A prompt for an image generator" (`pipelex/core/concepts/concept_factory.py:150-156`, the structure class name is literally `NativeConceptCode.TEXT.structure_class_name`).

So `native.ImgGenPrompt` is a semantic alias for `Text`. That's exactly why it doesn't belong as a built-in native concept — a user concept refining `Text` does the same job. **Migration for any consumer = replace `ImgGenPrompt` with `Text`.**

### The name-collision trap (critical — do NOT over-scope)

Three unrelated things share the name "ImgGenPrompt". **Only the first is being removed.** A naive grep audit conflates them and wildly overstates the blast radius ("requires refactoring the image-gen architecture" — this is FALSE).

| Thing | What it is | Action |
|---|---|---|
| `NativeConceptCode.IMG_GEN_PROMPT` | the native **concept** `native.ImgGenPrompt` | **REMOVE — the target** |
| `ImgGenPrompt` (BaseModel, `pipelex/cogt/img_gen/img_gen_prompt.py`) | runtime payload (positive/negative text + input images) that `PipeImgGen` builds and sends to the image generator | **LEAVE UNTOUCHED** |
| `TemplateCategory.IMG_GEN_PROMPT` (`pipelex/cogt/templating/template_category.py`) | Jinja2 template category for prompt rendering | **LEAVE UNTOUCHED — different enum** |

Also leave untouched: `ImgGenPromptError` (`pipelex/cogt/exceptions.py`) and its docs — that's the exception class for the runtime model, unrelated to the native concept.

### How `PipeImgGen` actually consumes inputs (corrected mental model — the docs got this wrong)

**`PipeImgGen` does NOT take an "`ImgGenPrompt` concept" as input.** The old docs implied you load a prompt into an `ImgGenPrompt`-typed stuff and feed it in. That framing is wrong and is a big reason this concept looked load-bearing when it isn't.

What actually happens:

- `PipeImgGenBlueprint` (`pipelex/pipe_operators/img_gen/pipe_img_gen_blueprint.py`) has a **required `prompt: str`** field (a Jinja2/sigil **template**) and an optional `negative_prompt: str`. There is no prompt-concept input.
- Declared `inputs = { ... }` are the variables the template may reference, and they get **injected into the template** at run time (`PipeImgGenFactory.make` → `pipe_img_gen_factory.py:41-93`, then `ImgGenPromptBlueprint.make_img_gen_prompt` → `img_gen_prompt_blueprint.py:65-196`):
  - **Text inputs** are interpolated into the prompt string via `$var` / Jinja.
  - **Image inputs** are detected by `TemplateImageAnalyzer.analyze_template_for_images` (`pipelex/pipe_operators/shared/template_image_analyzer.py`), classified as `DIRECT` (one image), `DIRECT_LIST` (a list/tuple of images), or `NESTED` (a dotted path like `page.page_view`). At run time each referenced `ImageContent` is pulled from working memory, registered in an `ImageRegistry`, the reference in the text is replaced with an `[Image N]` placeholder token, and every image is collected into `ImgGenPrompt.input_images`.
- This is **exactly the vision pattern** used for image inputs to `PipeLLM`: images declared as inputs and referenced in the prompt are extracted and passed alongside the rendered text. It enables image-to-image, reference-image, and image-editing generation (e.g. Flux / GPT-Image with reference images), bounded by the model's `max_prompt_images`.
- The resulting runtime `ImgGenPrompt` model (`positive_text`, `negative_text`, `input_images`) is what's sent to the generator.

So `PipeImgGen`'s only concept constraints are: declared image inputs must be `Image`-compatible (enforced at extraction time by the `ImageContent` type check), and its **output** must be `native.Image`-compatible (`pipe_img_gen.py:116-134`). It has **no** input-concept tie to `ImgGenPrompt`. The `IMG_GEN_PROMPT` symbols inside `pipe_img_gen_factory.py` / `pipe_img_gen_blueprint.py` are all `TemplateCategory.IMG_GEN_PROMPT` (the Jinja2 category), not the native concept. **Removing the native concept does not touch image generation behavior.**

Reference example to base accurate docs on: `tests/integration/pipelex/pipes/img_gen_prompt_inputs/test_img_gen_prompt_image_extraction.py` (exercises image injection into the prompt).

### Why removal is allowed

Per workspace `CLAUDE.md`: "No backward compatibility … Breaking changes must be noted in changelogs but there is no deprecation transition period." Removing a native concept is a breaking change for any out-in-the-wild `.mthds` using `native.ImgGenPrompt` or `refines = "ImgGenPrompt"`, but that's acceptable with a CHANGELOG note. Migration is trivial (`→ Text`).

### Scope facts already verified (so you don't re-check)

- **Not** present in `derived/mthds_schema.json` → **no `pipelex-dev generate-mthds-schema` regen needed.**
- No shipped/library/kit/cookbook/methods/test-bed `.mthds` uses it as a concept. The **only** `.mthds` usage anywhere is one test fixture (see step 3).
- `tests/unit/pipelex/core/concepts/test_concept.py:101` iterates `NativeConceptCode.values_list()` dynamically → adapts automatically, no edit needed.
- No test hardcodes the native-concept count or the `IMG_GEN_PROMPT` member by name.

---

## Implementation checklist

### 1. Code — `pipelex/core/concepts/native/concept_native.py`

These three `match`/`case` blocks are **exhaustive with no `case _:` allowed** (project rule), so the member must be removed from the enum *and* from every arm in lockstep, or linting fails.

- [ ] Remove the enum member: line 26 `IMG_GEN_PROMPT = "ImgGenPrompt"`
- [ ] `structure_class` property: collapse `case NativeConceptCode.IMG_GEN_PROMPT | NativeConceptCode.ANYTHING:` (line ~72) → `case NativeConceptCode.ANYTHING:` (still returns `None`)
- [ ] `is_text_concept` classmethod: drop `| NativeConceptCode.IMG_GEN_PROMPT` from the `False` alternation (line ~123)
- [ ] `is_dynamic_concept` classmethod: drop `| NativeConceptCode.IMG_GEN_PROMPT` from the `False` alternation (line ~146)

### 2. Code — `pipelex/core/concepts/concept_factory.py`

- [ ] Delete the `case NativeConceptCode.IMG_GEN_PROMPT:` arm at lines ~150-156 (otherwise `make_native_concept`'s match is non-exhaustive and references a dead member)

### 3. Test fixture — the only real runtime break

`tests/integration/pipelex/pipes/pipelines/multiplicity.mthds` outputs `ImgGenPrompt` in three pipes; after removal the bundle fails to resolve the concept at test load time.

- [ ] Change `output = "ImgGenPrompt"` → `output = "Text"` at lines 44, 56, 66 (it was structurally `Text` anyway; the prompts produce a sentence of text)

### 4. Spec authoring metadata — `pipelex/builder/concept/concept_spec.py`

Not enforced and won't break linting, but leaving it advertises a concept that no longer exists to the spec/builder agent.

- [ ] Remove `ImgGenPrompt` from the `refines` field description string (line ~250) and from the `examples=[...]` list (line ~253)

### 5. Docs (this repo) — update `docs/`

This step has two parts: (a) the mechanical removal of the native concept from concept reference docs, and (b) a **substantive rewrite** of the PipeImgGen docs to teach the correct prompt-template + input-injection model (see "How `PipeImgGen` actually consumes inputs" above).

**(a) Concept-reference removal (mechanical):**

- [ ] `docs/building-methods/concepts/native-concepts.md` — remove the table row at line 37 (`| `ImgGenPrompt` | … |`) AND the `### ImgGenPrompt` section (lines 186-190)
- [ ] `docs/building-methods/concepts/define_your_concepts.md:150` — remove `ImgGenPrompt` from the inline list; also **drop the hardcoded "12"** count (project writing rule: no hardcoded counts) — rephrase to "Pipelex includes these built-in native concepts: …"
- [ ] `docs/features/concepts.md:25` — remove the `**ImgGenPrompt** — …` bullet

**(b) PipeImgGen rewrite (substantive — fix the misleading "feed it an ImgGenPrompt concept" framing):**

- [ ] `docs/building-methods/pipes/pipe-operators/PipeImgGen.md`:
  - "How it works" (lines 9-13) — rewrite to state the truth: `PipeImgGen` takes a **`prompt` string template** (+ optional `negative_prompt`); declared `inputs` are **injected into the template** — text via `$var` interpolation, images via reference-and-inject (the vision pattern). It does not consume a dedicated prompt concept.
  - Example inputs currently typed `"ImgGenPrompt"` (lines 28, 39, 101, 115, 129) → `"Text"`. These show *text* prompt inputs, so `Text` is the correct concept.
  - **Add a new example: image inputs (image-to-image / reference image).** Show `inputs = { ref = "Image" }` (and a list variant, e.g. `refs = "Image[]"`), reference the image(s) in the `prompt` template, and explain that each referenced image is injected as an `[Image N]` token and passed to the generator — bounded by the model's `max_prompt_images`. Base it on `tests/integration/pipelex/pipes/img_gen_prompt_inputs/test_img_gen_prompt_image_extraction.py` so it's accurate.
  - Line 138 prose ("you would first load a text prompt … into the input stuff (`ImgGenPrompt` concept)") — rewrite: the input is an ordinary `Text` stuff referenced by the `prompt` template; there is no `ImgGenPrompt` concept.
- [ ] `docs/features/image-generation.md:40` — reword "(or an ImgGenPrompt concept)". Replace with the correct model: PipeImgGen takes a prompt template and can inject both text and image inputs (reference images for image-to-image). Do not imply a prompt-concept input.
- [ ] **Do NOT touch** `docs/errors/img-gen-prompt-error.md` or `docs/errors/inference-and-providers.md:34` — those document `ImgGenPromptError` (the runtime exception), which stays.

### 6. CHANGELOG

- [ ] Add a `### Removed` bullet under `## [Unreleased]` in `CHANGELOG.md` (there is already a `### Removed` section there — append to it). Draft:

  > **Native concept `ImgGenPrompt` (pre-1.0 breaking):** Removed `native.ImgGenPrompt`. It was structurally identical to `Text` (no dedicated content class; the factory mapped it to `TextContent`), so it added a brand-new built-in concept with no semantic payload. `PipeImgGen` never depended on it — its inputs are ordinary `Text`-compatible variables and its only concept guard is an `Image`-compatible output. Migration: replace `ImgGenPrompt` / `refines = "ImgGenPrompt"` with `Text` in any `.mthds`. Unrelated and unchanged: the `ImgGenPrompt` runtime model, the `TemplateCategory.IMG_GEN_PROMPT` template category, and `ImgGenPromptError`.

### 7. Verify

- [ ] `make agent-check` (lint/format/pyright/mypy/plxt — catches any non-exhaustive match)
- [ ] `make tb` (boot/config sanity; cheap)
- [ ] Targeted tests for the touched areas (core + pipes + builder), e.g.:
      `.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/core/ tests/integration/pipelex/core/ tests/integration/pipelex/pipes/ tests/unit/pipelex/builder/ tests/integration/pipelex/builder/`
- [ ] If broad/uncertain, fall back to full `make agent-test`
- [ ] Final grep sanity: `rg -n '\bImgGenPrompt\b' pipelex/ tests/ docs/` should return ONLY runtime-model / `TemplateCategory` / `ImgGenPromptError` hits — no `native.ImgGenPrompt` concept refs and no `NativeConceptCode.IMG_GEN_PROMPT`.

### 8. Land

- [ ] Commit on the feature branch, push, open PR to `dev`
- [ ] Hand off the recap below to downstream repos (see next section)

---

## Handoff recap (paste into ../mthds-plugins and other repos)

> **Heads-up: `ImgGenPrompt` is no longer a Pipelex native concept (breaking, pre-1.0).**
>
> As of pipelex `<next version>`, `native.ImgGenPrompt` has been removed from `NativeConceptCode`. It was a structural duplicate of `Text` (no dedicated content class — the factory mapped it to `TextContent`), so it was a built-in concept with no semantic payload beyond its name.
>
> **What this means for you:** any `.mthds` that uses `ImgGenPrompt` as an input/output concept, or `refines = "ImgGenPrompt"`, will fail validation against the new pipelex. **Fix = replace `ImgGenPrompt` with `Text`.**
>
> **What did NOT change** (do not "fix" these — they are unrelated things that happen to share the name):
> - the `ImgGenPrompt` runtime model (`pipelex.cogt.img_gen.img_gen_prompt.ImgGenPrompt`) — still how `PipeImgGen` builds the generator payload;
> - the `TemplateCategory.IMG_GEN_PROMPT` Jinja2 template category;
> - the `ImgGenPromptError` exception class.
>
> **Corrected mental model for `PipeImgGen` (the old docs were misleading — please fix yours too):** `PipeImgGen` does **not** consume a dedicated "prompt concept". It has a required **`prompt` string template** (+ optional `negative_prompt`), and its declared `inputs` are **injected into that template**:
> - **text inputs** (concept `Text`) are interpolated via `$var` / Jinja;
> - **image inputs** (concept `Image`, single or list) are referenced in the prompt and injected — each referenced image becomes an `[Image N]` token and is passed to the generator alongside the rendered text (this is the **same vision pattern** as image inputs to `PipeLLM`, and is what enables image-to-image / reference-image / editing, bounded by the model's `max_prompt_images`).
>
> So the right way to teach/author `PipeImgGen` is: write a `prompt` template, declare `Text` and/or `Image` inputs, reference them in the template. There is no `ImgGenPrompt` concept anywhere in that flow. If any of your docs/examples say "load a prompt into an `ImgGenPrompt` concept and feed it to PipeImgGen", that was always wrong — replace it with the template-injection model above.
>
> `PipeImgGen`'s only concept constraints: declared image inputs must be `Image`-compatible, and the output must be `Image`-compatible. The operator's runtime behavior is unchanged by this removal.
>
> **Where to check in your repo** (grep for `ImgGenPrompt` and judge by context — concept ref vs. the model/category/error above):
> - `mthds-plugins/` — any skill, prompt, or doc that enumerates native concepts (e.g. build/check/explain skills), or example `.mthds` snippets using `ImgGenPrompt` as a concept.
> - `mthds/` (spec docs site) — native-concepts reference page / any built-in concept list.
> - `mthds-js/`, `mthds-python/` — hardcoded native-concept lists used for validation or codegen.
> - `vscode-pipelex/` (`plxt` CLI / LSP) — native-concept completion/validation tables.
> - `conformance/` — fixtures or expected-output corpora referencing `native.ImgGenPrompt`.
> - `pipelex-cookbook/`, `methods/`, `test-bed/`, `pipelex-starter-python/` — example `.mthds` files (pipelex's own bundled libraries were already verified clean).
>
> Migration in all cases is the same: `ImgGenPrompt` (as a concept) → `Text`.

---

## DO-NOT-TOUCH guardrail (the conflation traps, restated)

If you find yourself editing any of these, STOP — you've drifted into the name collision:

- `pipelex/cogt/img_gen/img_gen_prompt.py` (the `ImgGenPrompt` BaseModel) and everything that imports it (`img_gen_job.py`, `img_gen_job_factory.py`, `img_gen_prompt_blueprint.py`, `content_generator.py`, `pipe_img_gen.py`, `pipe_img_gen_factory.py`, and their tests).
- `pipelex/cogt/templating/template_category.py` + `pipelex/tools/jinja2/jinja2_environment.py` (`TemplateCategory.IMG_GEN_PROMPT`).
- `pipelex/cogt/exceptions.py` `ImgGenPromptError` + `docs/errors/img-gen-prompt-error.md` + `docs/errors/inference-and-providers.md`.

These all stay exactly as they are.
