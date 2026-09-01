# Remove Background — design proposal

**Status:** proposal, awaiting decision on the central question (new pipe type vs PipeImgGen extension).
**Branch:** `feature/Remove-bg` (worktree `_bg`).
**Trigger:** support background removal via image-editing APIs we already reach through fal, starting with [`fal-ai/ideogram/remove-background`](https://fal.ai/models/fal-ai/ideogram/remove-background).

---

## 1. What we're adding, precisely

Background removal is a **promptless, parametric image transform**: one image in, one image out (foreground preserved on transparency), no text prompt, no creative latitude. The fal endpoint takes `image_url` (plus `sync_mode`) and returns a single transparent-background image. fal hosts several interchangeable models for the same job (`ideogram/remove-background`, `bria/background/remove`, `birefnet`, `imageutils/rembg`), and the same shape covers a whole family of future operations: upscale (`ideogram/upscale`, clarity-upscaler, recraft), erase, etc.

This is a different *kind* of thing from what `PipeImgGen` does today. It's closer to a hosted function applied to an image than to generation.

## 2. What exists today (relevant machinery)

- **`PipeImgGen` is prompt-centric by construction.** The blueprint (`pipelex/pipe_operators/img_gen/pipe_img_gen_blueprint.py`) has `prompt: str` **required**, and `validate_inputs()` is entirely about template variables. Input images exist, but they enter *only via the prompt*: each `Image` input referenced in the template is swapped for an `[Image N]` placeholder and collected into `ImgGenPrompt.input_images` (`img_gen_prompt_blueprint.py`). No prompt → no way to route an image into the job.
- **The cogt img-gen layer is already edit-capable.** `ImgGenPrompt.input_images`, the `InputImagesTaxonomy` rules (`img_gen_model_rules.py`, e.g. the BFL `input_image` / `input_image_N` mapping), and the fal worker plugin (`pipelex/plugins/fal/`) already send input images to fal endpoints. Adding a "single `image_url`" taxonomy value is a small delta.
- **Model specs describe capabilities declaratively.** `InferenceModelSpec` carries `model_type` (`ModelType`: `llm`, `text_extractor`, `img_gen`, `search`), `inputs`/`outputs`, `costs`, and per-model `rules` taxonomies. Backend TOMLs (`kit/configs/inference/backends/fal.toml`) declare each model; the deck (`kit/configs/inference/deck/2_img_gen_deck.toml`) provides aliases and task-named presets (`gen-image`, `synthesize-photo`, …).
- **Adjacent-but-different existing feature:** `background = "transparent"` on `PipeImgGen` asks the *generator* to produce a transparent background at generation time (GPT-Image). Removing the background of an **existing** image is a different user story; the docs must cross-link the two so users pick the right one.

## 3. The central question: where does this live?

Louis's question: *"Is this kind of a new feature to integrate in a PipeImgGen?"* Three honest options.

### Option A — Fold into `PipeImgGen` (model-driven)

Make `prompt` optional when the selected model declares it takes no text; auto-forward the (single) `Image` input as the job's input image.

```toml
[pipe.strip_background]
type = "PipeImgGen"
inputs = { product_photo = "Image" }
output = "Image"
model = "remove-background"   # the model implies the operation
```

**For:** no new pipe type, no MTHDS-language addition beyond making `prompt` optional; reuses everything.

**Against:**

- The mental model breaks exactly where it matters most. For a non-technical reader, `PipeImgGen` means "the AI paints an image from my description". A `PipeImgGen` with no prompt that *removes* content is a contradiction in the pipe's own name — and the reader can't tell what the pipe does without decoding the `model` value.
- The mechanism mismatch is real, not cosmetic: today images reach the job only through prompt references. A promptless path means building a parallel "forward the image inputs" mechanism *inside* PipeImgGen — that's Option B's semantics smuggled in, plus conditional validation ("prompt required, except for these models") which is the kind of "it depends" rule that confuses both humans and the builder agent.
- The operation becomes invisible to tooling: validation can't check "this pipe removes backgrounds" against anything; the graph view can only label the node "ImgGen".

### Option B — New operator: `PipeImgEdit` (operation-driven) — **recommended**

A dedicated operator for named, promptless image transforms. The **operation is the language-level intent**; the model is a swappable implementation detail, resolved through the same deck machinery as everything else.

```toml
[pipe.strip_background]
type = "PipeImgEdit"
edit = "remove_background"
inputs = { product_photo = "Image" }
output = "Image"
```

No `model` field needed in the common case: each operation has a default preset in the deck (`edit-remove-background = { model = "ideogram-remove-background" }`). Power users can still pin `model = "birefnet"` or a preset.

**For:**

- **The teachable rule is one sentence:** *describe what you want in words → `PipeImgGen`; apply a named edit → `PipeImgEdit`.* The presence/absence of a prompt is a crisp, non-technical boundary. (Prompt-guided editing with reference images — "put this hat on this dog" — stays in `PipeImgGen`, where it already works and where the prompt genuinely is the driver.)
- The pipe declaration *reads as the user's intent* (`edit = "remove_background"`), which is exactly what the builder agent, the graph view, the validation errors, and a non-technical reviewer all need.
- Future-proof for the operation family (upscale, erase, …) without ever touching `PipeImgGen` again. Start with **only** `remove_background` (smallest correct surface — no speculative enum values).
- Validation gets strong and simple: exactly one `Image`-compatible input, `Image`-compatible output, model (if given) must support the declared operation.

**Against:** a new MTHDS language surface — schema regen + cross-repo sync + spec addition on mthds.ai (see §7). One more operator in the docs list. Both costs are real but one-time; the "no backward compatibility" principle means we're free to land it clean.

### Option C — Spec-level sugar only

Keep the blueprint layer as Option A, but give the builder agent a friendly `PipeImgEditSpec` that compiles to a promptless `PipeImgGenBlueprint`. Rejected: the `.mthds` file is the artifact non-technical users see and share; sugar that disappears at the language layer means the readable form is not the stored form, which violates the whole point of MTHDS being human-readable.

### Recommendation

**Option B.** The strongest argument is the one Louis flagged as most important: how non-technical users understand pipe kinds. Operators are the "verbs" of the language (docs literally say so), and "edit this image: remove the background" is a different verb from "generate an image of…". Overloading `PipeImgGen` would make its docs page say "requires a prompt — except sometimes", which is the moment a newcomer stops trusting the taxonomy.

### Naming

- **`PipeImgEdit`** (recommended): "edit" is the everyday word (every phone photo app has an Edit button). Requires re-framing the `PipeImgGen` docs slightly: PipeImgGen = "create or reimagine images from a text prompt, optionally with reference images"; PipeImgEdit = "apply a specific edit operation to an image". The field name `edit` makes the TOML read as a sentence.
- Alternatives considered: `PipeImgTransform` (in a pipeline language, *every* pipe transforms — too generic), `PipeImgTool`/`PipeImgUtil` (jargon), one micro-operator per op like `PipeRemoveBackground` (maximally discoverable but explodes the operator list and the MTHDS schema with every new op; rejected).

## 4. Design detail (Option B)

### Language layer (blueprint)

`pipelex/pipe_operators/img_edit/pipe_img_edit_blueprint.py`:

- `type: Literal["PipeImgEdit"]`, `pipe_category: Literal["PipeOperator"]`.
- `edit: ImgEditOperation` — `StrEnum`, initially just `REMOVE_BACKGROUND = "remove_background"`.
- `model: ImgGenModelChoice | None` — same preset/alias/handle resolution as PipeImgGen; defaults to the operation's deck preset.
- `output_format: ImageFormat | None` — constrained: remove_background implies transparency, so validation rejects formats that can't carry alpha (reuse the existing `Background.TRANSPARENT` vs `output_format` validator logic).
- `validate_inputs()`: exactly one declared input, `Image`-compatible. `validate_output()`: `Image`-compatible, singular (no multiplicity — batching a folder of images is what `PipeBatch` is for, which keeps the operator's story simple).
- No prompt, no negative prompt, no aspect ratio/size (the output geometry is the input's).

### Builder layer (spec)

`pipelex/builder/pipe/pipe_img_edit_spec.py`: near-passthrough `PipeImgEditSpec` with agent-oriented field descriptions ("use `edit = \"remove_background\"` to strip the background from an input image; the subject is preserved on transparency"). Register in `pipe_spec_map.py` / `pipe_spec_union.py`.

### Model layer

- **`ModelType`:** add `IMG_EDIT = "img_edit"`. Keeping edit models out of `img_gen` matters for the deck (`_warn_if_ambiguous_img_gen`, choice defaults) and for `pipelex-agent models` listings — a remove-background model must never be resolvable as a generation model or vice versa. It also gives edit models their own deck section.
- **Backend TOML** (`fal.toml`):

  ```toml
  [ideogram-remove-background]
  model_id = "fal-ai/ideogram/remove-background"
  model_type = "img_edit"
  operation = "remove_background"
  inputs = ["image"]
  outputs = ["image"]
  costs = { input = 0.0, output = <per-image USD> }
  ```

  `operation` on the model spec is what lets validation check "pipe's `edit` ⊆ model's capability" at deck-resolution time, with a suggestion-quality error when they mismatch. (Open question: `operation: str` vs `operations: list[str]` — some providers bundle multi-op endpoints; start singular.)
- **Rules taxonomy:** add `InputImagesTaxonomy.SINGLE_IMAGE_URL` (maps the one input image to fal's `image_url`) and let `PromptTaxonomy` gain `NONE`. The args factory delta is small and stays inside the existing taxonomy system.
- **Deck:** new `img_edit` section in the deck files (`kit/configs/inference/deck/`), with per-operation default presets:

  ```toml
  [img_edit.presets]
  remove-background = { model = "ideogram-remove-background", description = "Remove the background, keep the subject on transparency" }
  ```

### Execution layer (cogt)

Reuse, don't duplicate: an `ImgEditJob` that is a thin sibling of `ImgGenJob` (input image + operation + params, no prompt), dispatched through the same worker infrastructure. The fal worker already does queue/poll/download; it gains the promptless arg path via the taxonomy above. Usage/cost reporting flows through the existing img-gen usage records (flat per-image cost — verify how `CostsByCategoryDict` models per-image pricing; today's img-gen entries already use per-image semantics in the `input` slot, so follow that precedent). Storage/URL handling (S3/GCS upload, signed URLs) is shared with img-gen outputs unchanged.

Decision to arbitrate during implementation: whether `ImgEditJob` is genuinely separate or `ImgGenJob` with an optional-prompt refactor. Separate is cleaner conceptually; shared is less code. Lean shared-with-clear-typing unless it forces conditional validation back in.

### Dry run / mock

`PipeImgEdit` must support dry-run and mock modes like the other leaf operators (mock returns a placeholder transparent PNG). This is required for `validate --all`, builder loops, and tests without spend.

## 5. DevEx walkthroughs

**Non-technical user, webapp / build chatbot:** "I upload product photos and want them on a white sheet" → builder agent proposes a two-step method: `PipeImgEdit` (`remove_background`) then a compositing step. The pipe card in the graph reads **"Remove background"** — the operation label, not the model name. The user never sees "ideogram".

**Method author, `.mthds` by hand:**

```toml
[pipe.clean_product_shot]
type = "PipeImgEdit"
description = "Remove the background from the product photo"
inputs = { product_photo = "Image" }
output = "Image"
edit = "remove_background"
```

**Builder AI agent:** discovers the operator via the spec union + `pipelex-agent models` (edit models listed under their own model type), and the one-sentence gen-vs-edit rule goes into the builder skill docs (`mthds-build`).

**Error UX:** the two foreseeable mistakes get first-class messages: (a) declaring `edit` on a `PipeImgGen` → suggested fix "use PipeImgEdit"; (b) writing a `prompt` on a `PipeImgEdit` → "edits are named operations and take no prompt; to edit an image with a text instruction, use PipeImgGen with the image as an input".

## 6. Docs plan

- New `docs/building-methods/pipes/pipe-operators/PipeImgEdit.md`; add to the operators index with the gen-vs-edit rule stated up front.
- `PipeImgGen.md` and `docs/features/image-generation.md`: re-frame as prompt-driven creation/reimagining; cross-link PipeImgEdit and contrast with `background = "transparent"` at generation time.
- Error reference pages regenerate via `pipelex-dev generate-error-pages` for the new error classes.

## 7. Cross-repo impact (release-gated, mostly)

- **MTHDS standard (`mthds/`):** new operator = language addition; needs a spec section on mthds.ai. This is the heaviest consequence of Option B and should be embraced, not worked around — the operation-family framing (named parametric edits) is worth standardizing once.
- **Schema sync:** `derived/mthds_schema.json` regen, then the `mthds-schema-sync` flow to `mthds`, `vscode-pipelex`, `mthds-ui` (gated on the released pipelex version, as usual).
- **`mthds-ui` / graph rendering:** new node kind styling; label nodes with the operation.
- **`conformance/` + `docs/specs/`:** if any spec'd surface changes (agent CLI output listing model types, validate errors), keep both sides in sync per the spec/conformance pair rule.
- **`pipelex-api` / hosted:** no route changes; new operator flows through `/v1/validate` and execution as data. Gateway model list gains the edit model(s) when we expose them through Pipelex Gateway (open question below).

## 8. Open questions for Louis

1. **Go/no-go on Option B (`PipeImgEdit`)** — this is the decision that unblocks everything else.
2. **Field name:** `edit` (reads as a sentence, recommended) vs `operation` (more generic, survives if we ever add non-edit ops).
3. **Gateway exposure:** do we route remove-background through Pipelex Gateway at launch, or fal-direct (BYOK) only at first? Gateway means metering/pricing work on the platform side.
4. **Second operation at launch?** Upscale is the obvious sibling and would validate the enum design with two members — but it drags in output-size semantics. Default: ship `remove_background` alone.
5. **Model spec `operation` singular vs plural** (see §4).

## 9. Phasing sketch (once Option B is confirmed)

1. **Phase 1 — core:** `ModelType.IMG_EDIT`, blueprint + factory + pipe, spec, fal model entry + taxonomy, deck preset, dry-run/mock, unit + e2e (mock) tests. Checkpoint: `.mthds` with `PipeImgEdit` validates and runs against fal locally.
2. **Phase 2 — polish:** error classes + suggested fixes + generated error pages, docs (operator page, index, image-generation re-frame), schema regen. Checkpoint: `make agent-check` + `make agent-test` green, docs coherent.
3. **Phase 3 — release-gated sweep:** MTHDS spec addition, schema sync to downstream repos, mthds-ui node styling, gateway exposure decision executed. (Follows the standard cut-pipelex-first release ordering.)
