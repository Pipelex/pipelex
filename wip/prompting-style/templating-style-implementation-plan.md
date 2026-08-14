# Templating style as an authoring decision — implementation plan

**2026-08-14, branch `fix/Keyless-dry-run` (worktree `_keyless`), off v0.44.0.** Implements [`prompt-style-as-an-authoring-decision.md`](prompt-style-as-an-authoring-decision.md) under the settled §7 rulings: **`templating_style` everywhere**, global default **`xml` + `plain`**, **no per-model/preset override**, authored surface = **full `TemplatingStyle`** (bare string = `tag_style` shorthand, inline table = full struct).

Progress is tracked with the checkboxes below. **Checkpoints marked ✋ are hard stops: the executing agent must not proceed past them without Louis' explicit go.** At every checkpoint, update this doc first: tick boxes, fill the checkpoint log at the bottom (status, decisions taken, open questions, state of the code), so the work can hand off into a fresh session with nothing lost.

## Decisions derived from the rulings (veto here, cheaply)

These follow from "one name everywhere" but were not explicitly ruled; they are what this plan builds unless overridden:

- **D1 — config vocabulary follows the ruling.** `PromptingConfig` → `TemplatingConfig`, mounted as `pipelex.templating_config`; TOML section `[pipelex.templating_config]` with the single field `default_templating_style = { tag_style = "xml" }` (`text_format` omitted → `plain` via the model default). The `prompting_styles` map is deleted, not renamed.
- **D2 — the resolver lives in a small new kernel module**, `pipelex/kernel/templating_style_ops.py`: `resolve_templating_style(*, authored: TemplatingStyle | None) -> TemplatingStyle` returning `authored or get_config().pipelex.templating_config.default_templating_style`. It serves the LLM, img-gen, search and compose paths alike; putting it in `llm_ops.py` would misname it for three of the four.
- **D3 — the authored union is typed, not stringly.** `templating_style: TagStyle | TemplatingStyle | None = None` on blueprint and spec — pydantic's lax mode coerces the bare TOML string into the `TagStyle` StrEnum, and the MTHDS JSON Schema gets a proper enum for the string arm instead of a free-form `str`. The factory widens `TagStyle` → `TemplatingStyle(tag_style=...)` so the runtime `PipeLLM` holds `TemplatingStyle | None` and the union never travels past parsing. Same idiom family as `PipeComposeBlueprint.template: str | TemplateBlueprint` (bare smart union, narrowing before use — no validator needed).
- **D4 — the kernel façade gains the same lever.** `PipelexKernel.llm_text` / `llm_object` accept an optional `templating_style` argument, resolved through the same total resolver. This is what finally dissolves parity gap 2.2 / KF-16: the façade and the interpreter agree because neither derives anything.
- **D5 — filters go strict, entry points resolve.** `render_template` keeps an optional `templating_style` (the EXPRESSION and MERMAID categories have no tag/format filters and legitimately render style-less), but the `tag` / `format` / `with_images` filters lose their silent fallbacks (`TICKS`, `PLAIN`): a missing context key raises `Jinja2ContextError`, because after this change every prompt-rendering entry point supplies a resolved style — a missing one is a bug, per §4.3.
- **D6 — no new authored field on PipeImgGen/PipeSearch in this change.** They inherit the config default through the resolver (§5's requirement); giving them their own authored knob is a deliberate follow-up if ever wanted, not scope creep now.

## Baseline: what is already sitting uncommitted on this branch

The worktree carries doc-migration changes from the design session: `pipelex/kernel/pipelex_kernel.py` (docstring pointer re-aimed at the new design-doc filename), the `wip/prompting-style/` README deletion + design doc, the `wip/keyless/` brief and plan, and `wip/parity/` updates. Plus this plan and the design doc's §7 ruling record.

- [x] Commit the standing wip/doc baseline as its own commit before Phase 0 code begins, so each phase's diff is reviewable on its own. — Already done before this session: the branch-tip commit "plans" carries exactly that baseline (kernel docstring pointer, wip/prompting-style, wip/keyless, wip/parity).

## Phase map

- **Phase 0** — prerequisite: re-home reasoning budgets off `prompting_target` (§6). Standalone, shippable, zero style-behaviour change. → ✋ **Checkpoint 1**
- **Phase 1** — the authored surface + total resolver on the LLM path (TDD). The behaviour flip (back-ticks → XML) lands here.
- **Phase 2** — one resolver, every prompt: img-gen, search, compose; tighten `TemplatingStyle | None` → `TemplatingStyle` along the rendering path; delete the silent filter fallbacks.
- **Phase 3** — deletions: `prompting_target` from every surface, the target→style map, the dead template module, grants. → ✋ **Checkpoint 2**
- **Phase 4** — migration surfaces: MTHDS schema, docs, changelog, drift acks.
- **Phase 5** — bookkeeping: KF-16 closure, keyless plan re-scope, design-doc status. → ✋ **Checkpoint 3 (final)**

## Traps to keep in view (learned from the inventories — read before each phase)

- **Silent-header hazard.** `backend_library.py` (`_load_backend` around lines 191-193) reclassifies any per-model TOML key not in `InferenceModelSpecBlueprint.model_fields` as an outbound **HTTP extra header**. Deleting the blueprint field while portkey's per-model `prompting_target = "gemini"` lines survive would ship those as headers, silently. The field deletion and the TOML deletions must be one commit, verified by grep.
- **Config sync is one-directional.** `.pipelex/inference/backends/` is the source of truth; edit there, then `make ukc` to sync `pipelex/kit/configs/inference/backends/`, gated by `make ccs`.
- **Config model and TOML move in lockstep** or boot fails — `make tb` after every config-shape edit.
- **Drift reads the git index.** Stage changes before `make drift-check` / `agent-check`, or the gate sees nothing. The `config-docs` contract (triggers: `configuration/**`, `config_cogt.py`, `pipelex.toml`) fires in Phases 0 and 1; `pipelex-kernel-docs` (triggers: `kernel/**`) fires from Phase 1 on. Ack only after actually reviewing the named docs.
- **The keyword-only auto-fixer is destructive to intent.** `make agent-check` runs `fix-keyword-only`; deleting grants is deliberate here (the granted defs are deleted or made fully keyword-only), but never let it silently keyword-only something meant to keep a granted subject. `subject_grants.toml` must stay sorted.
- **Deleted/renamed tests leave `.test_durations` stale** — only the full `make agent-test` at checkpoints catches the fallout; don't skip it.

---

## Phase 0 — Re-home reasoning budgets (prerequisite, §6)

Goal: no code reads `inference_model.prompting_target` for thinking budgets; each worker supplies its own family key. Pure re-homing — the style path is untouched, `prompting_target` still exists everywhere else. Independently shippable.

- [x] **Tests first (red):** in `tests/unit/pipelex/providers/google/test_google_reasoning.py`, rewrite `_make_worker` so the mock model spec has **no** `prompting_target` and the budget tests still pass once the worker owns its key; add the missing twin coverage for the Anthropic worker's manual-thinking budget resolution (today its budget branch has no test at all). — Done: `del mock_model.prompting_target` proves the spec is never read; new `tests/unit/pipelex/providers/anthropic/test_anthropic_reasoning.py` covers the manual budget branch, NONE gating, cap, explicit passthrough, and thinking_mode=none raise; both budget tests assert the lookup is keyed `family="anthropic"`/`"gemini"`. Confirmed red before implementation (14 failed), green after.
- [x] Give each worker its own key: a `ClassVar` on the worker class — `reasoning_budget_family = "anthropic"` on `AnthropicLLMWorker`, `"gemini"` on `GoogleLLMWorker` — read where the workers previously read `self.inference_model.prompting_target`.
- [x] Delete both `prompting_target is None → LLMCapabilityError` raise sites (the "has no prompting_target configured" branches) — unreachable once the key is worker-owned. The `LLMCapabilityError` class survives (other users).
- [x] Rename the concept in `pipelex/cogt/config_cogt.py`: `get_reasoning_budget(self, prompting_target, *, effort)` becomes fully keyword-only `get_reasoning_budget(*, family: str, effort: ReasoningEffort)`; update the two error message strings; delete the now-dead subject grant for it in `subject_grants.toml` (preserving sort order). `effort_to_budget_maps` keeps its name and its TOML keys (`anthropic`, `gemini`) — only the lookup parameter stops borrowing the word "prompting".
- [x] Update `tests/unit/pipelex/cogt/llm/test_llm_config_reasoning.py` for the new signature.
- [x] Docs in the same change: `docs/under-the-hood/reasoning-controls.md` — both "keyed by `prompting_target`" passages now describe the worker-owned key.
- [x] Gates: targeted pytest green (64 passed), `make agent-check` green after honest acks of `config-docs` (no configuration page mentions the budget lookup; the one `prompting_target` hit is the style path, Phase 3/4 scope) and `pipelex-kernel-docs` (trigger was the baseline commit's docstring pointer re-aim; kernel page references no wip paths and still describes today's code). Full `make agent-test` green — see Checkpoint 1 log.

### ✋ CHECKPOINT 1 — HARD STOP

Do not start Phase 1 without Louis' explicit go. Present: the Phase 0 diff summary, test results, and confirmation that `prompting_target` now has exactly one consumer left (the style path). Louis decides whether Phase 0 is committed (and possibly PR'd separately) before the breaking work begins. Update the checkpoint log below. This is also a natural fresh-session handoff point.

---

## Phase 1 — Authored surface + total resolver on the LLM path

Goal: a `PipeLLM` step can declare `templating_style`; when it says nothing, the config default (`xml`) applies; nothing consults the deck. **This is where every OpenAI-family prompt flips from back-ticks to XML** — the point of the change. TDD throughout: each box's test lands red before its implementation.

Config (D1):

- [x] `pipelex/system/configuration/configs.py`: `PromptingConfig` → `TemplatingConfig` with the single field `default_templating_style: TemplatingStyle`; delete `prompting_styles` and `get_prompting_style` (and its subject grant, keeping `subject_grants.toml` sorted); remount as `templating_config`.
- [x] `pipelex/pipelex.toml`: replace the `[pipelex.prompting_config]` block (and its `prompting_styles` sub-table) with `[pipelex.templating_config]` / `default_templating_style = { tag_style = "xml" }`. Neither `.pipelex/pipelex.toml` nor the kit `pipelex.toml` carries the section — no other TOML moves. `make tb` proves the lockstep.

Resolver (D2):

- [x] New `pipelex/kernel/templating_style_ops.py` with `resolve_templating_style(*, authored: TemplatingStyle | None) -> TemplatingStyle` — total, deck-free, credential-free.
- [x] Unit tests: totality (returns config default on `None`), authored-wins precedence, and the invariant that it never returns `None`. — `tests/unit/pipelex/kernel/test_templating_style_ops.py`, which also pins the shipped house default (xml + plain).

Authored surface (D3):

- [x] `PipeLLMBlueprint.templating_style: TagStyle | TemplatingStyle | None = None` (`pipe_llm_blueprint.py`).
- [x] `PipeLLMSpec.templating_style` — same union, passed through in `to_blueprint()` (`builder/pipe/pipe_llm_spec.py`), per the spec-vs-blueprint layering.
- [x] `PipeLLMFactory.make` widens `TagStyle` → `TemplatingStyle(tag_style=...)`; `PipeLLM` gains `templating_style: TemplatingStyle | None = None` (`pipe_llm_factory.py`, `pipe_llm.py`).
- [x] Parsing tests: bare string (`templating_style = "no_tag"`), inline table (`{ tag_style = "xml", text_format = "markdown" }`), absent → `None` at blueprint level. — `tests/unit/pipelex/pipe_operators/pipe_llm/test_pipe_llm_templating_style.py`, covering both parsing shapes, the spec passthrough, and all three factory-widening outcomes.
- [x] An e2e/integration bundle exercising the authored field — `tests/integration/pipelex/pipes/pipelines/templating_style.mthds` + `test_templating_style_bundle.py`: all three arms parse, load, and actually govern the rendered text. (a small `.mthds` under the existing test-package layout) — today zero `.mthds` files in the repo touch styling, so this is the first.

Wiring:

- [x] `pipe_llm.py` — replace `templating_style = derive_templating_style(llm_setting=llm_setting_main)` with `resolve_templating_style(authored=self.templating_style)`; drop the "both paths render under the text setting's style" comment (there is no derived style to agree about any more — both arms simply pass the pipe's resolved style).
- [x] `pipelex_kernel.py` — `llm_text` / `llm_object` gain `templating_style: TemplatingStyle | None = None`, resolved through the resolver (D4); **delete the `llm_object` docstring paragraph** recording the parity-gap 2.2 adjudication ("One `model`, and it carries…") — the question it adjudicates dissolves.
- [x] Update `tests/unit/pipelex/pipe_operators/pipe_llm/test_prompt_rendering_purity.py`: the "blueprint style wins over the **run-derived** one" parametrization becomes authored-vs-config-default; the purity assertion itself (blueprint not mutated) survives as-is.
- [x] Flip the two default-shape assertions in `tests/integration/pipelex/pipes/llm_prompt_inputs/test_prompt_image_extraction.py` (`assert "```" in llm_prompt.user_text` → XML shape) and fix its docstring prose.
- [x] MTHDS schema test `tests/unit/pipelex/language/test_mthds_schema.py`: assert `PipeLLMBlueprint` now carries `templating_style` (optional — the minimal-table cases stay valid).
- [x] Gates: `make tb`, targeted tests, stage + `make agent-check` (both drift contracts fire — review `docs/configuration/**` and `docs/under-the-hood/pipelex-kernel.md`; the kernel page's surface table still names `derive_templating_style`, which is *correct to leave red until Phase 4* — if the ack would be dishonest, defer the ack to Phase 4 and run gates knowing drift is the one expected red, or update the one table row now and ack honestly. Prefer the latter: keep gates green.)

Note: `LLMSetting.prompting_target` and friends are now **uncalled but still present** — deletion is batched in Phase 3 so this phase stays reviewable as "add + rewire".

**Deviation taken in Phase 1:** `derive_templating_style` could *not* wait for Phase 3. Its only data source was `PromptingConfig.get_prompting_style`, which D1 deletes here, so leaving it in place would have left the tree not type-checking. It was deleted in this phase together with the config it read; everything else in the Phase 3 deletion batch is untouched.

## Phase 2 — One resolver, every prompt; tighten optionality; strict filters

Goal: img-gen, search and compose prompts stop falling into the silent `TICKS` fallback and inherit the same config default; `TemplatingStyle` stops being optional along the prompt-rendering path (§4.3); the fallbacks die.

- [x] **Img-gen:** `kernel/img_gen_prompt.py` — `assemble_img_gen_prompt` and `_render_text` gain a required `templating_style: TemplatingStyle`; `pipe_img_gen.py` resolves via `resolve_templating_style(authored=None)` (no authored surface, D6) and passes it down. — Done; `_render_text` keeps the per-template override arm (`template_blueprint.templating_style or templating_style`), mirroring `_unravel_text` exactly.
- [x] **Search:** the query template renders under the resolved default. — `run_search` gains a required `templating_style`; `pipe_search.py` resolves `authored=None`. Its docstring no longer justifies the source-plus-category signature with "no style".
- [x] **Compose:** `run_compose_template`'s `templating_style` is required; `pipe_compose.py` resolves `authored=self.templating_style`. Behaviour note for the changelog: a bare-string compose template using `| tag` flips from the TICKS fallback to the config default. **Beyond the plan:** construct mode needed the same treatment — `StructuredContentComposer` renders each TEMPLATE field with `render_template(category=BASIC)`, which is filter-bearing and was style-less, so a construct field using `| tag` would have hard-failed once the fallbacks died. It now takes a `templating_style` and threads it into nested composers.
- [x] **Tighten the LLM chain:** `run_llm_text`, `run_llm_object` (`kernel/llm_ops.py`), `assemble_llm_prompt`, `_unravel_text` (`kernel/llm_prompt_content.py`), `make_llm_prompt` (`llm_prompt_blueprint.py`) — `templating_style: TemplatingStyle`, required, no default. The per-template merge `jinja2_blueprint.templating_style or templating_style` stays (a template-level declaration still wins) but is now total by construction.
- [x] `render_template` / `render_jinja2_*` keep an optional style (filter-less categories, D5); `_prepare_templating_context` unchanged in shape. Also left optional, deliberately: `ContentGeneratorProtocol.make_templated_text` and its `TemplatingAssignment` — a generic templating seam with no production caller, not a prompt-rendering entry point, and a caller may legitimately render an EXPRESSION or MERMAID template style-less. A caller that does use `| tag` there now gets a loud error instead of silent TICKS, which is D5's intent.
- [x] **Delete the fallbacks (D5):** `apply_tag_style`'s `TICKS` arm (`jinja2_filters.py`) → missing `TAG_STYLE` raises `Jinja2ContextError`; the `format` filter's `PLAIN` default and `jinja2_with_images_filter.py`'s twin likewise go strict. Also delete the dead `TemplatingStyle.make_default_prompting_style` (zero callers).
- [x] Tests: `test_default_style_is_ticks_when_not_set` is now `test_missing_tag_style_raises`; `test_jinja2_tag_filter.py`'s `_make_context` takes a keyword-only `tag_style` with no default, so every case states the style it renders under. New `tests/unit/pipelex/tools/test_jinja2_style_context_strictness.py` covers all three filters raising on a style-less context, plus the case that must NOT raise (an explicit `| format("markdown")` argument never reads the context key). The img-gen twin is `test_img_gen_prompt_renders_under_config_default` in the Phase-1 bundle test, against a new `default_style_picture` PipeImgGen in `templating_style.mthds`. `dry_mock.py` needed nothing: it stringifies `TemplatingAssignment.templating_style`, which stays optional on the seam left optional above. The kernel boot-contract subprocess now resolves the style itself, which incidentally proves the resolver runs on a library-less boot.
- [x] Gates: targeted tests green across tools, kernel, pipe_operators, integration pipes and cogt; `make tb`; stage + `make agent-check`.

**Two things Phase 2 touched that the plan had not anticipated**, both consequences of the filters going strict — a style-less render of a filter-bearing category stops being merely odd and becomes a hard failure, so every such render site had to be found, not just the ones on the prompt paths:

- **Construct-mode template fields** (`StructuredContentComposer`), described in the compose box above. This one was user-facing: `.mthds` construct fields are authored templates.
- **The two generic prompt templates** — `derive_structure_prompt` (`kernel/llm_ops.py`) and the structuring prompt rendered in `pipe_structure.py`. Both render `TemplateCategory.LLM_PROMPT` with no style. The shipped templates use no filter, so nothing breaks today, but they are config-editable, and a user who added `| tag` would have hit the new error with no way to supply a style. `derive_structure_prompt` now takes the style its caller already holds (it is appended to that same prompt, so any other answer would be incoherent); `pipe_structure.py` resolves `authored=None` like the other operators with no authored surface.

**One pre-existing wrinkle fixed in passing**, in the `format` filter being edited anyway: its `text_format` argument was annotated `TextFormat | None`, but Jinja2 hands a template-supplied `{{ x | format("markdown") }}` over as a raw `str`. The annotation made two branches unreachable to the type checker while the reachable path raised a bare `ValueError` on an unknown format name. Now annotated `TextFormat | str | None`, normalising both through `TextFormat(...)` and reporting an unknown name as a `Jinja2ContextError` — which the renderer already wraps into a template render error.

## Phase 3 — Deletions (pure by now)

Everything below is uncalled after Phases 0-2; this phase is grep-verified removal. **One commit for the model-field + TOML pair** (silent-header hazard).

- [x] `LLMSetting.prompting_target` (field, import, the `desc()` fragment) — `cogt/llm/llm_setting.py`. This also erases the independent keyless-plan symptom "an explicitly set `llm_setting.prompting_target` is ignored" — dissolved, not fixed.
- [x] `InferenceModelSpec.prompting_target` + `InferenceModelSpecBlueprint.prompting_target` (+ the factory passthrough) — `cogt/model_backends/model_spec.py`, `model_spec_factory.py`.
- [x] **Same commit:** every `prompting_target` line in `.pipelex/inference/backends/*.toml` — the `[defaults]` line in anthropic, azure_openai, bedrock, fal, google, minimax, mistral, ollama, openai, portkey, vertexai, xai, **plus portkey's per-model `gemini` overrides** — then `make ukc` to sync the kit copies, `make ccs` to prove it. Grep both trees afterwards: zero hits. — Done: 17 lines across 12 files, `make ccs` green, both trees grep clean.
- [x] The `PromptingTarget` enum module — `cogt/model_backends/prompting_target.py` — and its imports.
- [x] `derive_templating_style` (`kernel/llm_ops.py`) and its docstring. — Deleted in Phase 1, see the deviation note there.
- [x] **The dead template module:** re-confirm `cogt/llm/llm_prompt_template.py` has no production consumer (inventory says: only two serde test files import it), then delete it together with its only base `llm_prompt_factory_abstract.py`; rework `tests/integration/pipelex/cogt/test_serde_llm_classes.py` and `test_data.py` to serde-test a living model (e.g. `LLMPrompt` itself) instead. The hardcoded xml+markdown style dies with it. — Done: `SerDeTestLLMCases` now serde-tests `LLMPrompt`, which genuinely crosses a process boundary, and its docstring says why that subject was chosen (the `user_images` items are `PromptImage` subclasses, so a round-trip losing the subclass would silently drop the image).
- [x] **Investigate `llm_prompt_template_inputs.py`:** if its only production consumer was the dead module, delete it too along with `LLMPromptTemplateInputsError` — then remove its subject-grant entries, run `make gei` (error-identity snapshot) and `make gep` (error pages), and let `docs/errors/llm-prompt-template-inputs-error.md` go. If something live uses it, keep all of it and record why here. — Verdict: nothing live used it, so it went, along with `LLMPromptTemplateInputsError`, its two subject grants, its `docs/errors/` page and its `error_identity.txt` row (both regenerated, not hand-edited), and the error's case in `test_class_level_metadata.py`.
- [x] Final sweeps: `prompting_target` greps clean outside `wip/`, `CHANGELOG.md` and the `.drift/acks` historical record; `PromptingTarget` zero; `prompting_style`/`prompting_config` survive only in the three Phase-4 doc targets (the styling page, `inference-backend-config.md`'s stale example, `add-model/SKILL.md`). Also removed the two now-pointless `del mock_model.prompting_target` lines in the reasoning tests: they guarded against reading a field that no longer exists.
- [x] Gates: stage + `make agent-check`, **full `make agent-test`** — both green.

**A blocker Phase 3 uncovered, and what was done about it.** Deleting `prompting_target` from `InferenceModelSpecBlueprint` made the *entire* test suite error at boot — 9671 errors, all one cause. The Pipelex Gateway backend does not read its model specs from this repo: they are fetched from the Pipelex API and cached at `~/.pipelex/cache/remote_config.json`, and that config's `defaults` block still declares `prompting_target = "anthropic"`. The blueprint is `extra="forbid"`, so a served config declaring a field this client no longer knows stops the boot dead.

The fix is not a shim for this field. `drop_unknown_gateway_defaults` (`cogt/model_backends/gateway_config.py`) prunes keys the blueprint does not know from the **remote** config's `defaults` before the merge with local overrides, on the principle that a config served by a component deploying on its own schedule is legitimately written by a different release than the client reading it — version skew to tolerate, not a typo to reject. Local backend files stay strict. Tested in `tests/unit/pipelex/cogt/model_backends/test_gateway_unknown_defaults.py`.

Two things this leaves for elsewhere, written up in [`gateway-config-still-declares-prompting-target.md`](gateway-config-still-declares-prompting-target.md): dropping the now-dead field from the config `pipelex-server` serves, and deciding whether the per-model unknown-key → HTTP-header rule should survive for the gateway backend (a removed field living per-model rather than in `defaults` would have been *sent to the provider as a header* instead of raising — a worse outcome than the one actually hit, and one no test would catch).

### ✋ CHECKPOINT 2 — HARD STOP

Do not start Phase 4 without Louis' explicit go. This is the point-of-no-return review of the behaviour flip. Present: full diff stats by phase, the green `agent-test` run, and a **before/after rendering of one real prompt** (e.g. from the flipped `test_prompt_image_extraction` case) showing back-ticks → XML. Louis reviews the actual prompt text change, rules on any surprises logged along the way, and decides the commit strategy for Phases 1-3. Update the checkpoint log. Natural fresh-session handoff.

---

## Phase 4 — Migration surfaces: schema, docs, changelog, drift

Schema (mechanical half — cross-repo propagation is release-gated, see follow-ups):

- [x] `make gms` then `make cms` — the diff is two-sided: `PipeLLMBlueprint` gains `templating_style`; `LLMSetting` loses `prompting_target` and the `PromptingTarget` definition disappears (`TemplatingStyle`/`TagStyle` were already published via `TemplateBlueprint`). — Regenerated, `make cms` green. **No tracked diff:** `derived/mthds_schema.json` is gitignored, so the schema change reaches consumers only through the release-gated downstream sync already listed in the follow-ups.

Docs (the design's §8 — replace, don't patch, the dead-premise page):

- [x] **New authoring page** (e.g. `docs/building-methods/templating-style.md`): the two-level model (pipe > config default), bare-string shorthand vs full table, the tag-style gallery incl. `no_tag`, the compose/img-gen story, xml as house default. Written for authors, not infra.
- [x] **Delete** `docs/building-methods/adapt-to-llm-prompting-style-openai-anthropic-mistral.md`; update `mkdocs.yml`: both nav entries, the existing legacy redirect re-pointed to the new page, and a new redirect from the deleted path.
- [x] `docs/features/llm-integration.md` — rewrite the "Prompting Styles" section (its "provider-specific formatting … automatically" claim is exactly what's deleted) + front-matter description; `docs/features/index.md` blurb.
- [x] `docs/configuration/config-technical/inference-backend-config.md` — drop the (already-stale) prompting field from the model-spec example.
- [x] `docs/under-the-hood/pipelex-kernel.md` — the flow prose ("derive a prompting style"), the kernel-surface table row, the per-call note; whatever Phase 1 already touched, finish here. — Nothing left to do: Phases 1-2 finished this page to keep their drift acks honest, and it now contains no `prompting` hit at all.
- [x] `docs/building-methods/pipes/pipe-operators/PipeLLM.md` — new `templating_style` parameter row; inline model-table field list checked (it never documented `prompting_target`, so no deletion there).
- [x] `docs/building-methods/pipes/pipe-operators/PipeCompose.md` — align wording with the one-name vocabulary; cross-link the new page.
- [x] `.claude/skills/add-model/SKILL.md` — remove the `prompting_target` authoring step. **Pulled forward out of Phase 4 and done**, because it is an agent-executable instruction living in the repo: between Phase 3 and Phase 4 it told an author to write a key that now hard-fails the boot. Replaced with a line saying a model spec never declares prompt formatting, and that an unknown key becomes an outbound header.
- [x] Verify `docs/CLAUDE.md`'s language-surface note still reads true now that PipeLLM carries the field too. — It does. The note's claim is scoped to its own example (`PipeComposeSpec.target_format` is a spec convenience; the language uses `category` + `templating_style` on `TemplateBlueprint`), and that remains exactly true. `templating_style` now living on `PipeLLMBlueprint` as well does not contradict it — both are blueprint-level, which is the point the note is making. Left unedited.
- [x] Sweep for stragglers: `grep -ri "prompting" docs/` and judge each survivor. — Two survivors, both the ordinary English verb and both correct: `init-cli-flows.md` ("credential prompting", i.e. asking the user) and `tools/cli/update.md` ("without prompting on the unchanged files"). Left alone.

Changelog:

- [x] Insert `## [Unreleased]` at the top of `CHANGELOG.md` (the header was consumed by v0.44.0) with a breaking entry, condensed style. Draft: **"Breaking — templating style is now an authoring decision.** How a pipe's inputs are tagged into a prompt is declared on the pipe (`templating_style` on `PipeLLM`: bare tag-style string or full `{ tag_style, text_format }` table) with a single runtime default (`[pipelex.templating_config].default_templating_style`, `xml`). It is no longer derived from model metadata: `prompting_target` is gone from model specs, backend TOMLs and inline model tables, along with the per-target style map. Every prompt rendered for an OpenAI-family model changes shape from back-tick blocks to XML tags; img-gen, search and compose prompts follow the same default instead of a silent triple-backtick fallback." Plus a Changed entry: reasoning budgets are worker-owned, no longer read from `prompting_target`.

Drift:

- [x] `make drift-plan`; review and ack whatever remains open of `config-docs` / `pipelex-kernel-docs` with honest rationales; append the dogfood observation to `wip/drift-contracts/dogfood-log.md`. — **Nothing open:** Phases 1-3 acked both contracts, and Phase 4 touches only docs, which are review targets rather than triggers. No ack was invented to fill the box. Two dogfood entries appended, and the first is a genuine finding rather than a formality: `config-docs` reviews only `docs/configuration/**`, so the page that actually documented `[pipelex.prompting_config]` — filed under `docs/building-methods/` because it was written for authors — was invisible to the one contract whose description claims to cover config docs. It stayed stale for three phases behind an honest green ack.
- [x] Gates: stage + `make agent-check`.

## Phase 5 — Bookkeeping: KF-16 closes, keyless un-holds

- [x] `wip/parity/README.md` — flip the Phase-2 "slated to become" sentence to closed; update the 2.2 gaps-table row.
- [x] `wip/parity/SESSION-HANDOFF.md` and `wip/parity/parity-gaps-plan.md` — record KF-16 as closed by this change (name commits by subject, never SHA — this branch may rebase); the §2.2 deferral record's "do not fix by object-only derivation" trap is now moot and can say so.
- [x] `wip/keyless/keyless-dry-prompts-fix-plan.md` — replace the hold banner: the headline symptom, Part 1, and most of Part 3 are dissolved by construction; re-scope the plan to the surviving residue (`max_prompt_images` unenforced, img-gen param rules skipped, handle-pinned bundles rejected keylessly, the two CLIs disagreeing on `--dry-run` credentials). Re-judging that residue is its own future task, not this one.
- [x] `wip/keyless/keyless-boot-changes-dry-prompts.md` — a short closing note pointing at the dissolution.
- [x] This design doc — status flips to built; this plan's checkpoint log completed.
- [x] Final gates: stage everything, `make agent-check`, **full `make agent-test`** — both green. Also ran `make docs-check` (`mkdocs build --strict`), which the plan had not listed and which this phase needed: Phase 4 rewires `mkdocs.yml` nav and redirects, and a nav entry pointing at a deleted file fails only at build time. Clean.

### ✋ CHECKPOINT 3 — FINAL HARD STOP

Everything is green and documented; nothing is committed beyond what earlier checkpoints approved. Louis decides: commit/PR shape (one PR vs. Phase 0 split out), whether this branch keeps the `fix/Keyless-dry-run` name or is rebranded (the keyless fix it was cut for has been dissolved, not fixed), and release timing. Present the release-gated follow-ups below. Update the checkpoint log.

## Out of scope here — release-gated / cross-repo follow-ups

- **MTHDS schema downstream sync** (mthds, vscode-pipelex, mthds-ui committed copies) via the `mthds-schema-sync` skill — gated on a released `pipelex` version.
- **MTHDS spec prose** — a pipe-level `templating_style` is a language-surface change owned by the `mthds/` repo; the schema regen is only the mechanical half. A deliverable of its own after release.
- **`pipelex-api` CI** — its openapi check runs only under its own `make check` and has been bitten by pipelex bumps before; verify on the release bump whether the schema change surfaces there.
- **Cookbook / starter sweeps** — no shipped `.mthds` uses any styling surface today, so no migration is expected; a post-release sanity pass confirms.
- **Downstream backend-TOML sweep — a boot-breaker, and the one item on this list that is not optional.** Every repo that ships its own `.pipelex/inference/backends/*.toml` still declares `prompting_target`, and local backend files are read strictly: on the `pipelex` version bump each one dies at boot with `Extra forbidden fields: 'prompting_target'`. Tracked-file hits confirmed in `pipelex-server/worker/`, `pipelex-api/`, `cocode/`, `pipelex-cookbook/`, `pipelex-demos/`, `mthds-ui/`, plus two `pipelex-js/` fixtures. **`portkey.toml` is the trap in every one of them**: the key appears once in `[defaults]` *and* again on several per-model entries, so a "fix" that deletes only the `[defaults]` line unblocks the boot while leaving the per-model ones — which the loader reclassifies as **outbound HTTP headers** sent to Portkey. Delete every occurrence, `[defaults]` and per-model alike, and grep to prove it.
- **~~The served gateway config~~ — DONE (2026-08-14), and it changed the branch.** The config is owned by `pipelex-back-office`, not `pipelex-server`: `pipelex_back_office/remote_config/gateway_models.toml` declared `prompting_target = "anthropic"` in its `[defaults]`, and `build_service.py` publishes that block as the remote config's `backend_model_specs` — that file is the reason `drop_unknown_gateway_defaults` exists. The key is deleted there (edit + `[Unreleased]` changelog, uncommitted in that repo) and **published**.

  Publishing it was only safe because **the served config is versioned in its URL, and this branch bumps it**: `pipelex/system/pipelex_service/pipelex_details.py` now points at `pipelex_remote_config_12.json` (was `_11`) — an uncommitted change on this branch that must ship with it. `_11` is frozen and still carries the key, so earlier releases keep resolving `anthropic` → `xml`; had they read a key-less config they would have fallen through to `TagStyle.TICKS`, flipping every gateway prompt in the field to backtick fences. Verified live against both URLs. Retires the *occasion* for the tolerance, not the tolerance itself, which is general. See [`gateway-config-still-declares-prompting-target.md`](gateway-config-still-declares-prompting-target.md).

  Two things this leaves open: **the URL bump needs a Phase 4 changelog line** (a released client fetching a different config URL is user-visible), and **`pipelex-js` is a second consumer of this same wire contract** — it pins `_11` (`packages/runtime/src/worker/catalogue.ts`) and models the field as `promptingTarget` on its spec, so it is unaffected today but diverges the moment it moves to `_12`. That is beyond the backend-TOML fixture hits already listed above.
- **PipeImgGen/PipeSearch authored styling** (D6) — only if a real need appears.

## Checkpoint log

*(Filled in as checkpoints are reached: status of completed phases, decisions taken, open questions, state of the code.)*

- **Checkpoint 1:** *(2026-08-14)* Phase 0 complete. Reasoning-budget resolution is re-homed off `prompting_target`: each worker owns a `reasoning_budget_family` ClassVar (`"anthropic"` on the Anthropic worker, `"gemini"` on the Google worker) and `LLMConfig.get_reasoning_budget` is fully keyword-only with a `family` parameter (its subject grant removed from `subject_grants.toml`). TDD red→green: new twin Anthropic reasoning test module + updated Google/config tests landed red first, went green with the implementation; the tests `del mock_model.prompting_target` so any spec read would raise — this stays valid after Phase 3 deletes the field. `effort_to_budget_maps` TOML keys unchanged. Docs updated (`docs/under-the-hood/reasoning-controls.md`). Gates: `make agent-check` green (two drift contracts honestly reviewed and acked: config-docs, pipelex-kernel-docs); full `make agent-test` green. Verified exit criterion: `prompting_target`'s only remaining consumers are the style path (configs.py `get_prompting_style`, llm_setting.py, model_spec + factory, kernel/llm_ops.py derive path) — Phases 1–3 scope. State: committed standalone on `fix/Keyless-dry-run` (commit "Phase 0 — re-home reasoning budgets off prompting_target"). Open questions: none. Louis' go received 2026-08-14 → Phase 1 underway.
- **Checkpoint 2:** *(2026-08-14)* **Reached. Phases 1-3 complete, `make agent-check` and the full `make agent-test` both green.** Awaiting Louis' go for Phase 4.

  **Phase 1 landed (2026-08-14), committed, all gates green.** What it built: `TemplatingConfig` (single field `default_templating_style`, mounted `pipelex.templating_config`; `prompting_styles` and `get_prompting_style` deleted along with the latter's subject grant), the total resolver `pipelex/kernel/templating_style_ops.py`, the authored `templating_style` union on `PipeLLMBlueprint` / `PipeLLMSpec` / `PipeLLM` with the factory widening the bare-`TagStyle` arm, and both `PipelexKernel` façade calls taking the same optional argument (D4 — the `llm_object` parity-gap docstring paragraph is deleted, the question it adjudicated having dissolved). **The behaviour flip is live:** every OpenAI-family prompt now renders XML instead of back-ticks, because nothing derives a style from model metadata any more.

  One deviation from the plan, recorded under Phase 1: `derive_templating_style` was deleted here rather than in Phase 3, because D1 deletes the config map that was its only data source — leaving it would not type-check. The rest of the Phase 3 deletion batch is untouched.

  Tests added: `test_templating_style_ops.py` (totality, house default, authored-wins), `test_pipe_llm_templating_style.py` (both parsing shapes, spec passthrough, all three factory outcomes), and the `templating_style.mthds` bundle + `test_templating_style_bundle.py` proving the authored field survives parse→load→render. `test_prompt_image_extraction.py`'s two default-shape assertions now supply the resolved style and assert XML; note the `with_images | tag` case asserts `<data>`, not `<pages>` — after `with_images` the value is a plain string with no name of its own.

  Docs touched in-phase (to keep the drift acks honest): `docs/under-the-hood/pipelex-kernel.md` — entry-point table lists `templating_style_ops` and drops `derive_templating_style`, and the flow prose plus the per-call-derivation note use the templating vocabulary. Both `config-docs` and `pipelex-kernel-docs` were reviewed and acked.

  Known and deliberate: the Claude Code `check-mthds` hook rejects `templating_style` in a `.mthds` file because it validates against the plugin's bundled schema, which is stale. `make plxt-lint` regenerates `derived/mthds_schema.json` first and passes. The downstream schema sync is already listed as a release-gated follow-up.
  **Phase 2 landed (2026-08-14), committed, all gates green.** Every prompt-rendering entry point now takes a **required** `TemplatingStyle`, and the three styling filters lost their silent fallbacks — a missing `TAG_STYLE` or `TEXT_FORMAT` raises `Jinja2ContextError` instead of quietly choosing triple-backticks or plain text. Img-gen, search and compose resolve through the same resolver the LLM path uses. Two render sites the plan had not anticipated needed the same treatment, both found by asking "which filter-bearing category still renders style-less": construct-mode template fields (user-authored `.mthds` content, so this one was user-facing) and the two generic prompt templates (the structure prompt and the structuring prompt, both config-editable). Details under the Phase 2 heading.

  **Phase 3 landed (2026-08-14), committed, all gates green.** `prompting_target` is gone from `LLMSetting`, `InferenceModelSpec`, `InferenceModelSpecBlueprint`, the factory passthrough, and every backend TOML in both trees — the field deletion and the TOML deletions in one commit, as the silent-header hazard requires. The `PromptingTarget` enum module is deleted. The dead `llm_prompt_template.py` / `llm_prompt_factory_abstract.py` / `llm_prompt_template_inputs.py` trio went with it, along with `LLMPromptTemplateInputsError` and its generated error page and identity row; the serde tests they anchored now exercise `LLMPrompt`.

  **The one surprise, and it was a big one:** the deletion broke the boot against the *remote* gateway config, which still declares `prompting_target`. Whole suite red, one cause. Resolved with a general remote-config tolerance rather than a field-specific shim; a `pipelex-server` follow-up and an open design question are written up in [`gateway-config-still-declares-prompting-target.md`](gateway-config-still-declares-prompting-target.md). **This is the item most worth Louis' ruling.**

  **Before / after, one real prompt.** Same template (`Summarize the article below.\n\n@article\n\nKeep it to one sentence.`), same input, rendered under the old OpenAI-family style and under the new default:

  ```text
  BEFORE (prompting_target "openai" -> ticks)     AFTER (no authored style -> config default)
  Summarize the article below.                    Summarize the article below.

  article: ```                                    <article>
  Bees pollinate a third of the food we eat.      Bees pollinate a third of the food we eat.
  ```                                             </article>

  Keep it to one sentence.                        Keep it to one sentence.
  ```

  The resolved default is `xml/plain`. Note the tag *name*: `@article` carries the variable name into the tag, so XML reads better than the old `article: ```' prefix-plus-fence shape.

  **Open for Louis at this checkpoint:** (a) the gateway-config finding above and its two follow-ups; (b) the commit strategy — Phases 0-3 are four separate commits on `fix/Keyless-dry-run`, so squashing to any shape is still trivial; (c) whether Phase 4's changelog entry should call out the compose and img-gen flips separately from the LLM one (they change prompt text for anyone whose template uses `| tag`, not just OpenAI-family users).

- **Checkpoint 3:** *(2026-08-14)* **Reached. Phases 4 and 5 complete; `make agent-check`, the full `make agent-test`, and `mkdocs build --strict` all green.** Phases 4-5 are **staged but uncommitted**, per this checkpoint's own terms — the commit/PR shape is Louis' call.

  **Phase 4 — migration surfaces.** Schema regenerated (`make gms`/`make cms` green); it produces no tracked diff because `derived/mthds_schema.json` is gitignored, so the schema reaches consumers only via the release-gated downstream sync. Docs: the dead-premise page `adapt-to-llm-prompting-style-openai-anthropic-mistral.md` is **deleted** and replaced by a new authoring page, [`docs/building-methods/templating-style.md`](../../docs/building-methods/templating-style.md) — the two-level model, bare-string vs full-table, the four-style gallery with rendered output for each, what the two sigils (`@` tag / `$` format) each govern, and the compose/img-gen story. `mkdocs.yml` updated in three places (both nav entries, the legacy redirect re-aimed) plus a **new** redirect from the deleted path — that fourth entry is load-bearing: `docs/404.html`'s prefix rule rewrites the legacy URL to the now-deleted `building-methods/adapt-…` path, so without it the JS-rewrite fallback would land on a 404. `llm-integration.md` (section + front-matter), `features/index.md`, `inference-backend-config.md`, `PipeLLM.md` (new parameter row), `PipeCompose.md` (wording + cross-link) all updated. Changelog `## [Unreleased]` written with the breaking entry.

  **Two things worth Louis' eye in Phase 4.** (1) I **did not use content tabs** for the style gallery — `pymdownx.tabbed` is not enabled in `mkdocs.yml`, so `=== "xml"` would have rendered as literal text; it is plain subsections instead, which also avoids a nested-fence break in the `ticks` example (that one needs a 4-backtick fence). (2) Open question (c) from Checkpoint 2 — whether to call out the compose/img-gen flips separately — I **resolved as yes**, as its own changelog entry, because it changes prompt text for a different audience (anyone whose template uses `| tag`, on any model family) than the LLM-path flip (everyone on OpenAI-family models). Easy to merge back into one entry if Louis prefers.

  **The drift box, and the one real finding in this phase.** `make drift-plan` reported **nothing open** — Phases 1-3 acked both contracts, and Phase 4 touches only docs, which are review *targets*, not triggers. No ack was invented to fill the box. But the dogfood review surfaced something worth reading: **`config-docs` reviews only `docs/configuration/**`, and the page that actually documented `[pipelex.prompting_config]` — field list, TOML sample, accessor signature — lived under `docs/building-methods/` because it was written for authors.** So in Phase 1 the trigger fired, the review target was read in full, the target was genuinely clean, the ack was honest — and the stale page sailed through three phases behind a confident green, to be deleted here by a plan step rather than by the contract. Every step of the mechanism worked and it still missed. Logged in `wip/drift-contracts/dogfood-log.md` with the narrow remedy (a derived grep check for `[pipelex.` blocks documented outside `docs/configuration/`) rather than the tempting one (widening the review target to `docs/**`, which this log has twice warned makes acks perfunctory). **Not acted on** — recorded per the pilot's bias.

  **Phase 5 — bookkeeping.** KF-16 is recorded **closed by dissolution** in all three parity docs, with the #1081 docstring's trap note explicitly marked moot (there is no object-only resolution left to derive a style from, so the warning has no referent — preserved as history, flagged not-guidance). The keyless brief is closed with a banner explaining that the bug is unreachable in principle now, since both the derivation *and* the silent `TICKS` fallback are gone. The keyless fix plan is re-scoped in place rather than rewritten: Part 1 is folded into a `<details>` block as dissolved, and struck premises are kept as the record of what was measured.

  **The re-scope produced a judgement Louis should overrule if he disagrees.** I flagged in that plan that **the surviving residue may no longer be worth Part 2's blast radius**, and said so at the top rather than quietly proceeding. The reasoning: the symptom that justified "faithful over cheap" was a dry run *silently* validating a prompt that would never be sent. Every survivor is either loud (handle-pinned bundles rejected), a skipped constraint check (`max_prompt_images`, img-gen params), or a CLI inconsistency. Item 5 in particular loses its force — it was framed as "the loud converse of item 1", and with item 1 gone a loud refusal is a much weaker case for the `BackendLoadMode` surgery than a silent rewrite was. My recommendation is to decide **Part 2 and Part 4 separately**: Part 4 (`pipelex run --dry-run` should stop demanding credentials) is cheap and clearly right on its own. I also flagged a live trap for whoever builds it: the prompt-parity end-to-end test is now **green before any production edit**, so using it as the mutation-check target would produce a false green across the whole gate.

  **Open for Louis:** (a) commit/PR shape for Phases 0-5 — six commits' worth on `fix/Keyless-dry-run`, still trivially squashable; (b) whether the branch keeps its name, since the keyless bug it was cut for was dissolved rather than fixed; (c) the Checkpoint-2 gateway-config finding and its two follow-ups, still unruled; (d) the changelog's separate compose/img-gen entry (my call, easily merged); (e) the Part 2 re-judging above. **The downstream backend-TOML sweep is the one non-optional follow-up** — every repo shipping its own `.pipelex/inference/backends/*.toml` dies at boot on the version bump, and `portkey.toml`'s per-model occurrences become outbound HTTP headers if only the `[defaults]` line is deleted.
