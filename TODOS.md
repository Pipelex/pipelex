# Portable image size for image generation — implementation plan

Implements the design in [`wip/img-gen-size-portable-design.md`](wip/img-gen-size-portable-design.md). The design decisions are **settled** (with Louis, 2026-07-02) — do not re-litigate them; if implementation reveals a genuine conflict with the design, stop and surface it instead of silently deviating.

**Branch**: `feature/Img2Img-with-gpt-image`.

## Working conventions for this plan

- **TDD**: write the failing tests first, then implement (red → green), per phase.
- **One commit per phase.** Record each phase's commit SHA in the "State for cold start" section below, so each review fan-out gets a precise diff pointer.
- **Verification commands**: `make agent-check` after code changes; targeted tests via `.venv/bin/pytest -x -q <path>` during development; `make tb` whenever a config model or `pipelex.toml` structure changes; full `make agent-test` at the final checkpoint (and at any checkpoint if the phase touched shared surfaces).
- **Keyword-only args**: any new function in `pipelex/` source must follow the keyword-only convention (bare `*` after the subject) — `make agent-check` hard-blocks violations.
- **Checkpoint protocol** (mandatory at every CHECKPOINT below — the agent must stop and do all of this before starting the next phase):
  1. **Verify**: run the phase's verification commands; everything green before proceeding.
  2. **Commit** the phase's work.
  3. **Update this file**: tick the boxes, record the commit SHA, note decisions taken, open questions, and anything a cold-start session needs in "State for cold start".
  4. **Fan out a code review**: spawn a **Sonnet-5** sub-agent with **no inherited context** to run the `/code-review` skill. Hand it *only* a pointer to the changes (the phase's commit SHA / `git diff <sha>^..<sha>`, or `git diff <base>..HEAD` for multi-commit spans) — never this plan, the design doc, the rationale, or your own conclusions. Target: clean solid software, not over-engineering.
  5. **Triage the review findings**: apply clear correctness/simplification fixes (amend or follow-up commit); findings that are design tradeoffs (not silent bugs) go to a deferred-items doc under `wip/img-gen-size/` instead of being reflexively "fixed".
  6. It must be safe to end the session at any checkpoint — the "State for cold start" section is the handoff.

## Phase 0 — baseline

The working tree starts with the prior aspect-ratio work **staged but uncommitted** (img-gen aspect-ratio files + the design doc). That work is authorized prior work — commit it as-is first so the size work diffs cleanly.

- [x] Commit the currently staged changes as their own commit (aspect-ratio follow-up + design doc); record the SHA below as `BASE`
- [x] Confirm green baseline: `make agent-check` + `.venv/bin/pytest -x -q tests/unit/pipelex/cogt/img_gen/ tests/unit/pipelex/plugins/ tests/unit/pipelex/pipe_operators/pipe_img_gen/` + `make tb`
- [x] If the baseline is not green, fix or surface to the user before writing any size code

## Phase 1 — types & surface

New `size` field end to end on the params/blueprint/spec surface, no behavior on the wire yet.

- [x] **Tests first**: parsing unit tests in `tests/unit/pipelex/cogt/img_gen/` — tier tokens (`"0.5k"`/`"1k"`/`"2k"`/`"4k"`), exact `"WxH"` → `ImageSize`, garbage strings → clear `ValueError`; serialization round-trip for both union arms (StrEnum as str, `ImageSize` as dict)
- [x] **Tests first**: blueprint validator tests in `tests/unit/pipelex/pipe_operators/pipe_img_gen/test_pipe_img_gen_blueprint.py` — tier composes with `aspect_ratio`; exact size + `aspect_ratio` set together → validation error; each alone OK
- [x] `SizeTier` StrEnum in `pipelex/cogt/img_gen/img_gen_job_components.py` next to `AspectRatio`: `HALF_K = "0.5k"`, `ONE_K = "1k"`, `TWO_K = "2k"`, `FOUR_K = "4k"`
- [x] `ImgGenJobParams.size` becomes `SizeTier | ImageSize | None` via an annotated union with a `BeforeValidator` that parses strings (tier token → `SizeTier`, `"<int>x<int>"` → `ImageSize`, else `ValueError`); reuse the same annotated type for all three surfaces
- [x] `PipeImgGenBlueprint.size` (`pipelex/pipe_operators/img_gen/pipe_img_gen_blueprint.py`) + `PipeImgGenSpec.size` (`pipelex/builder/pipe/pipe_img_gen_spec.py`) use the same union; blueprint gains the `size`-vs-`aspect_ratio` exclusivity validator (spec's `to_blueprint()` threads it through)
- [x] `PipeImgGen` (`pipelex/pipe_operators/img_gen/pipe_img_gen.py`) threads `self.size or img_gen_param_defaults.size` into `ImgGenJobParams` like the other one-time settings
- [x] `ImgGenJobParamsDefaults` gains optional `size` — class default `None` (the Optional exception to the no-class-defaults config rule); **no key added** to `pipelex/pipelex.toml` or `.pipelex/pipelex.toml` (`None` = provider default)
- [x] Explicit non-goal, do not add: `size` on `ImgGenSetting` (deck presets) — geometry is pipe intent, not model preset
- [x] Verify: `make agent-check`, targeted tests, `make tb` (config model changed)

### CHECKPOINT 1 — surface in place

The new `size` surface is the foundation everything else builds on; catch shape/over-engineering problems now, before Phase 2 builds on the union type. Full checkpoint protocol: verify → commit → update this file → fan out `/code-review` (Sonnet-5, context-free, pointer = this phase's commit SHA) → triage findings.

- [x] Checkpoint 1 done (commit SHA recorded below, review findings triaged)

Checkpoint 1 review triage (context-free Sonnet `/code-review` on `19ce81eeb`):

- **Fixed** (follow-up commit `18b1364c5`): exact `ImageSize` was silently dropped on the Flux / Flux-1.1-Ultra / Qwen taxonomies — now a hard `ImgGenParameterError` ("does not support exact image sizes"), with a parametrized test. Also deduplicated the tier-token error text into `SizeTier.quoted_tokens()` and removed the spec `size` description's reference to `aspect_ratio` (the spec surface has no such field).
- **Known, deferred by plan**: `check_blueprint_params` not yet receiving `size` (no static validation of `size` at blueprint load) — that is exactly the Phase 2 item "`check_blueprint_params` now receives the explicitly-set `size`"; not fixed early.

## Phase 2 — rules & validation

Static validation story complete: Google models get deck rules, tiers and exact sizes are checked at blueprint-load/runtime-pre-call, exact-grid matching works. **No wire changes in this phase.**

- [x] **Tests first**: per-taxonomy support matrices in `tests/unit/pipelex/cogt/img_gen/test_img_gen_param_support.py` — which (aspect_ratio × tier) pairs pass/fail per taxonomy value, incl. `1k` as universal no-op, `2k`/`4k` rejections on incapable models, `0.5k` rejected everywhere for now
- [x] **Tests first**: exact-grid hit/miss tests — `"2048x2048"` on a gemini-3 grid → derives (1:1, 2K); `"2000x2000"` → error naming nearest cells
- [x] **Tests first**: static blueprint-validation tests for Google models (the previously-skipped gap) + the four portability worked examples from the design's "acceptance bar" section as test cases
- [x] New `AspectRatioTaxonomy` values in `pipelex/cogt/img_gen/img_gen_model_rules.py`: `gemini_2_5` (1K only, standard ratios), `gemini_3_pro` (1K/2K/4K, standard ratios), `gemini_3_flash` (1K/2K/4K now — 0.5k deferred, all ratios), `gemini_3_flash_lite` (1K only, all ratios); docstring states the topic governs ratio **and** size jointly (topic keeps its `aspect_ratio` name — no rename)
- [x] `pipelex/kit/configs/inference/backends/google.toml`: `rules` blocks on Google image models (`aspect_ratio = "gemini_3_flash"` etc.); source of truth is `.pipelex/inference/backends/google.toml`, synced via `make ukc` + `make ccs` (both run, in sync)
- [x] `GoogleImgGenFactory` (`pipelex/plugins/google/google_img_gen_factory.py`) re-keyed by taxonomy instead of matching on model names; **`GoogleImageGenModel` name enum killed** (model handles are deck config, not code constants); dimension grids stay in the factory as the single source of truth for dims
- [x] Exact-grid match: `derive_ratio_and_size_from_exact_size` searches the taxonomy's grids for an equal cell → derives (ratio, tier); on miss → `ImgGenParameterError` suggesting the nearest valid cells (closest ratio, then closest area); never silently snaps
- [x] `ImgGenParamSupport`: `check_aspect_ratio` covers (aspect_ratio, size) jointly incl. tier values; `check_blueprint_params` now receives the explicitly-set `size`; `check_job_params` picks it from params as before; unknown-taxonomy abstain policy kept
- [x] Tier satisfiability for non-Google taxonomies wired into the same check: gpt-image-2 accepts `1k`/`2k`, rejects `0.5k`/`4k`; legacy gpt-image accepts `1k` only; Flux/SDXL/Qwen accept `1k` as no-op, reject the rest; exact size on no-exact-size models → validation error
- [x] Verify: `make agent-check`, targeted unit tests, `make tb` (deck TOML changed), full `tests/unit/` suite green

### CHECKPOINT 2 — validation story complete (design's explicit checkpoint)

Natural handoff point: everything static is done and green; Phase 3 opens the worker/API-call area. Full checkpoint protocol: verify → commit → update this file → fan out `/code-review` (Sonnet-5, context-free, pointer = this phase's commit SHA) → triage findings. Also run the broader unit suite here (`.venv/bin/pytest -x -q tests/unit/`) since taxonomy/deck changes have wide reach.

- [x] Checkpoint 2 done (commit SHA recorded below, review findings triaged)

Checkpoint 2 review triage (context-free Sonnet `/code-review` on `ec0aa7ce7`): **no correctness bugs found**; the reviewer confirmed the hardcoded worker `size="1K"` and the gateway's commented-out `image_size` are the planned Phase 3 gap, not regressions. Two low-severity notes, both addressed in follow-up commit `a8e56bfe5`:

- `grids_for_taxonomy` returned the class-level grid dict directly (latent mutation footgun) → return type is now a read-only `Mapping`, with the shared-tables contract stated in the docstring.
- The SQUARE stand-in in `check_blueprint_params` relied on an unstated invariant (every taxonomy supports SQUARE; tier verdicts are ratio-uniform) → now guarded by `test_square_stand_in_invariant`, parametrized over every taxonomy, which fails first if a future taxonomy breaks either half.

## Phase 3 — wire

Providers actually receive the size intent.

- [ ] **Tests first**: worker/gateway payload assertions (extend `tests/unit/pipelex/plugins/google/test_google_img_gen_factory.py` and gateway factory tests) — tier → `image_size` token (`"1k"` → `"1K"`), **param omitted entirely when `size` unset** (never silently upgrade; provider default = 1K); args-factory tests for OpenAI tier-derived sizes
- [ ] Google worker (`pipelex/plugins/google/google_img_gen_worker.py`): send `image_config.image_size` from the tier, stop hardcoding `"1K"`; computed grid dims keep stamping `GeneratedImageRawDetails.size` metadata, now tier-aware
- [ ] Gateway (`pipelex/plugins/gateway/gateway_factory.py` `make_extras`): thread the same `image_size` into `extra_body["image_config"]` for gemini-routed jobs (replaces the commented-out placeholder)
- [ ] `ImgGenArgsFactory` (`pipelex/cogt/img_gen/img_gen_args_factory.py`) handles the union on OpenAI paths: tier → scale the existing `GPT_IMAGE_2_ASPECT_RATIO_TO_SIZE` table (`2k` = ×2 per edge, `0.5k` = ×½, `4k` = ×4) → run through existing `validate_gpt_image_2_size`; exact size → existing pass-through unchanged
- [ ] Reliability-boundary warning: demote to `log.verbose` when the size is tier-derived; keep the loud warning for user-supplied exact sizes
- [ ] Legacy gpt-image path: tier `1k` → the existing fixed size for the chosen ratio; nothing else changes
- [ ] Verify: `make agent-check`, targeted tests (`tests/unit/pipelex/cogt/img_gen/`, `tests/unit/pipelex/plugins/`)

### CHECKPOINT 3 — wire complete

The provider-facing change surface is done; Phase 4 is docs/e2e/release, a different concern. Full checkpoint protocol: verify → commit → update this file → fan out `/code-review` (Sonnet-5, context-free, pointer = this phase's commit SHA) → triage findings.

- [ ] Checkpoint 3 done (commit SHA recorded below, review findings triaged)

## Phase 4 — docs, e2e & release readiness

- [ ] `docs/building-methods/pipes/pipe-operators/PipeImgGen.md`: `size` in the param table; portability section with the design's worked examples; cost note (2k/4k cost proportionally more; unset = provider default cost) — Material for MkDocs conventions, blank line before lists, no hard wraps
- [ ] `docs/configuration/config-technical/cogt-config.md`: document the optional `size` default in `ImgGenJobParamsDefaults`
- [ ] MTHDS JSON Schema regen: `.venv/bin/pipelex-dev generate-mthds-schema` (blueprint field changed — schema should expose enum-or-pattern for `size`)
- [ ] `CHANGELOG.md` entry under `[Unreleased]` (breaking changes marked "breaking"; no mention of `wip/` docs)
- [ ] E2E smoke (cost-gated test profile, see `/test-model` skill conventions): one 2K generation on `nano-banana-2` and one on `gpt-image-2` in `tests/e2e/pipelex/pipes/pipe_operators/pipe_img_gen/`
- [ ] Retire the superseded WIP note if still present anywhere; move any deferred-review-findings doc into `wip/img-gen-size/`
- [ ] Full gates: `make agent-check` + `make agent-test` + `make tb`

### CHECKPOINT 4 — final gate

Full checkpoint protocol one last time: full suite green → commit → update this file (final state, remaining follow-ups) → fan out `/code-review` (Sonnet-5, context-free, pointer = `git diff <BASE>..HEAD` for the whole feature) → triage findings. Then hand back to the user for merge/release decisions.

- [ ] Checkpoint 4 done (feature-complete, full suite green, final review triaged)

## Out of scope (explicit follow-ups, do not implement here)

- `0.5k` wire-token verification against Gemini 3.1 Flash (empirical test of `"512"` / `"0.5K"`), then enabling it in the `gemini_3_flash` taxonomy + adding the published 512px grid to the factory. Until then `0.5k` is a validation error on every model.
- Adding 4:5/5:4 to the `AspectRatio` enum (published in Gemini grids) — separate decision.
- `size` on `ImgGenSetting` deck presets — only if a real need materializes.

## State for cold start

> Update this section at every checkpoint. A fresh session should be able to resume from this section + the design doc alone.

- **Status**: Phases 0–2 done and committed; Checkpoint 2 complete (review fanned out, findings triaged, follow-ups committed). Next: Phase 3 (wire), starting with its tests-first items. NOTE: the gateway remote config edit (see decisions below) is in `pipelex-back-office` working tree — Louis uploads it; not part of this repo's commits.
- **`BASE` commit (Phase 0)**: `17f478e7b` (plan + design doc; the aspect-ratio code itself was already committed as `d42084e91` before this plan started — nothing else was staged)
- **Phase 1 commit**: `19ce81eeb`; Checkpoint 1 review fixes: `18b1364c5`
- **Phase 2 commit**: `ec0aa7ce7`; Checkpoint 2 review follow-ups: `a8e56bfe5`
- **Phase 3 commit**: —
- **Phase 4 commit**: —
- **Decisions taken during implementation**:
  - The shared annotated union is `ImgGenSize: TypeAlias = Annotated[SizeTier | ImageSize, BeforeValidator(parse_img_gen_size)]` in `img_gen_job_components.py`; fields declare `ImgGenSize | None`.
  - Exact-size parsing accepts only positive `WxH` (regex `([1-9]\d*)x([1-9]\d*)`, lowercase `x`, no spaces); everything else raises "expected a size tier (…) or an exact size like '2048x1152'".
  - Interim guard: `ImgGenArgsFactory.make_args_from_aspect_ratio` raises `ImgGenParameterError` for any `SizeTier` ("not yet supported") so a tier can never silently reach the wire between Phase 1 and Phases 2–3; `check_aspect_ratio` was widened to the union. Phases 2–3 replace this guard with real per-taxonomy logic.
  - `mthds_schema.json` regen deliberately deferred to Phase 4 (the schema unit tests don't gate on drift — verified).
  - Phase 2 necessarily implements the gpt-image-2 tier→scaled-size computation (`OpenAIImgGenFactory._gpt_image_2_size_for_tier`): the capability check reuses `ImgGenArgsFactory` as the single source of truth, so "gpt-image-2 accepts 1k/2k" can only be checked by actually deriving and validating the scaled size. Phase 3's OpenAI item reduces to the reliability-warning demotion + payload assertions.
  - No global early guard for `0.5k`: each taxonomy rejects it with its honest reason (Gemini: unverified wire token via `image_size_for_tier`; gpt-image-2: below the 0.65 MP floor via the scaled-size validator; Flux/SDXL/Qwen/legacy: only-'1k' message).
  - `check_blueprint_params` checks a set `size` even when `aspect_ratio` is None, using `AspectRatio.SQUARE` as a neutral stand-in — the size verdict is ratio-independent (exact sizes ignore the ratio everywhere; tier satisfiability is uniform across each model's supported ratios). The deferred deck-default ratio itself still gets checked at runtime.
  - `GoogleImgGenWorker` resolves its taxonomy from `inference_model.rules` (new `_img_gen_taxonomy()`, clear `ImgGenParameterError` if rules/topic missing or unknown); the wire still hardcodes `size="1K"` until Phase 3.
  - Gemini taxonomy cases in `make_args_from_aspect_ratio` validate (ratio, size) against the grids and return `{"aspect_ratio": <literal>}` — the Google native worker and gateway build their own `image_config`, so nothing consumes these args yet (Phase 3 threads `image_size`).
  - Pre-existing drift fixed by `make ukc`: kit `google.toml` had `nano-banana-2-lite` `inputs = ["text"]` while the `.pipelex` source (of-truth) said `["text", "images"]` since the img2img commit `38c716b56` — kit now matches the source (lite accepts image inputs).
  - Gateway remote config (`pipelex-back-office/pipelex_back_office/remote_config/gateway_models.toml`, per Louis) also got the four `rules` blocks: gateway gemini img-gen models run through `OpenAICompletionsImgGenWorker` (sdk `gateway_completions`) which never reads rules on the wire, and older pipelex releases abstain on the unknown taxonomy — so the addition is validation-only and version-safe. **Louis uploads it** so it becomes live remotely.
- **Open questions**: —
