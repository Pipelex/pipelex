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

> **Session paused here (2026-08-14), nothing of Phase 2 started.** Phases 0 and 1 are committed and green. The survey done just before the pause, so the next session need not redo it — every remaining `templating_style` site outside the LLM entry path:
>
> - `kernel/img_gen_prompt.py` — `assemble_img_gen_prompt` and `_render_text` take no style at all today; `_render_text` passes `template_blueprint.templating_style` (always `None` on this path) straight to `render_template`, which is exactly the silent-`TICKS` route.
> - `kernel/compose_ops.py:72` — `run_compose_template` has `templating_style: TemplatingStyle | None = None`; `pipe_compose.py:206` passes `self.templating_style` (the existing authored compose surface) and its `desc()` at line 61 still says "prompting style".
> - `kernel/llm_prompt_content.py` — `assemble_llm_prompt` (line 75) and `_unravel_text` (line 383) both default to `None`; line 387 holds the per-template merge `jinja2_blueprint.templating_style or templating_style` that stays but becomes total.
> - `pipe_operators/llm/llm_prompt_blueprint.py:70` — `make_llm_prompt` likewise optional.
> - `kernel/llm_ops.py` — `run_llm_text` / `run_llm_object` still `TemplatingStyle | None = None`.
> - The fallbacks to delete (D5): `apply_tag_style`'s `tag_style = TagStyle(...) if tag_style_str else TagStyle.TICKS` at `jinja2_filters.py:122`, the `format` filter's `TextFormat.PLAIN` default at line 43, the `with_images` twin, and the zero-caller `TemplatingStyle.make_default_prompting_style`.

Goal: img-gen, search and compose prompts stop falling into the silent `TICKS` fallback and inherit the same config default; `TemplatingStyle` stops being optional along the prompt-rendering path (§4.3); the fallbacks die.

- [ ] **Img-gen:** `kernel/img_gen_prompt.py` — `assemble_img_gen_prompt` and `_render_text` gain a required `templating_style: TemplatingStyle`; `pipe_img_gen.py` resolves via `resolve_templating_style(authored=None)` (no authored surface, D6) and passes it down. Blueprint-carried styles (always `None` today on this path) stop mattering: the resolved style is what renders, `template_blueprint.templating_style or resolved` if we keep the per-template override arm — mirror the LLM path's merge exactly.
- [ ] **Search:** the query template (`pipe_search_factory.py` builds it style-less) renders under the resolved default — same treatment at its render site.
- [ ] **Compose:** `kernel/compose_ops.py` `run_compose_template` — `templating_style` becomes required; `pipe_compose.py` resolves `resolve_templating_style(authored=self.templating_style)` (the authored arm is the existing compose surface: spec `target_format` / blueprint `template.templating_style`). Behaviour note for the changelog: a bare-string compose template using `| tag` flips from the TICKS fallback to the config default.
- [ ] **Tighten the LLM chain:** `run_llm_text`, `run_llm_object` (`kernel/llm_ops.py`), `assemble_llm_prompt`, `_unravel_text` (`kernel/llm_prompt_content.py`), `make_llm_prompt` (`llm_prompt_blueprint.py`) — `templating_style: TemplatingStyle`, required, no default. The per-template merge `jinja2_blueprint.templating_style or templating_style` stays (a template-level declaration still wins) but is now total by construction.
- [ ] `render_template` / `render_jinja2_*` keep an optional style (filter-less categories, D5); `_prepare_templating_context` unchanged in shape.
- [ ] **Delete the fallbacks (D5):** `apply_tag_style`'s `TICKS` arm (`jinja2_filters.py`) → missing `TAG_STYLE` raises `Jinja2ContextError`; the `format` filter's `PLAIN` default and `jinja2_with_images_filter.py`'s twin likewise go strict. Also delete the dead `TemplatingStyle.make_default_prompting_style` (zero callers).
- [ ] Tests: rewrite `test_default_tag_style_is_ticks_when_not_set` into "missing TAG_STYLE raises"; restyle `test_jinja2_tag_filter.py`'s class-level TICKS default context so explicit-style tests stay explicit; sweep the other jinja/rendering tests that relied on implicit context; add an img-gen-renders-under-config-default test (the LLM twin exists from Phase 1); check `dry_mock.py`'s style stringification against the now-total style.
- [ ] Gates: targeted tests, stage + `make agent-check`, `make tb`.

## Phase 3 — Deletions (pure by now)

Everything below is uncalled after Phases 0-2; this phase is grep-verified removal. **One commit for the model-field + TOML pair** (silent-header hazard).

- [ ] `LLMSetting.prompting_target` (field, import, the `desc()` fragment) — `cogt/llm/llm_setting.py`. This also erases the independent keyless-plan symptom "an explicitly set `llm_setting.prompting_target` is ignored" — dissolved, not fixed.
- [ ] `InferenceModelSpec.prompting_target` + `InferenceModelSpecBlueprint.prompting_target` (+ the factory passthrough) — `cogt/model_backends/model_spec.py`, `model_spec_factory.py`.
- [ ] **Same commit:** every `prompting_target` line in `.pipelex/inference/backends/*.toml` — the `[defaults]` line in anthropic, azure_openai, bedrock, fal, google, minimax, mistral, ollama, openai, portkey, vertexai, xai, **plus portkey's per-model `gemini` overrides** — then `make ukc` to sync the kit copies, `make ccs` to prove it. Grep both trees afterwards: zero hits.
- [ ] The `PromptingTarget` enum module — `cogt/model_backends/prompting_target.py` — and its imports.
- [ ] `derive_templating_style` (`kernel/llm_ops.py`) and its docstring.
- [ ] **The dead template module:** re-confirm `cogt/llm/llm_prompt_template.py` has no production consumer (inventory says: only two serde test files import it), then delete it together with its only base `llm_prompt_factory_abstract.py`; rework `tests/integration/pipelex/cogt/test_serde_llm_classes.py` and `test_data.py` to serde-test a living model (e.g. `LLMPrompt` itself) instead. The hardcoded xml+markdown style dies with it.
- [ ] **Investigate `llm_prompt_template_inputs.py`:** if its only production consumer was the dead module, delete it too along with `LLMPromptTemplateInputsError` — then remove its subject-grant entries, run `make gei` (error-identity snapshot) and `make gep` (error pages), and let `docs/errors/llm-prompt-template-inputs-error.md` go. If something live uses it, keep all of it and record why here.
- [ ] Final sweeps: `prompting_target` greps clean outside `wip/` and `CHANGELOG.md`; `PromptingTarget` zero; `prompting_style`/`prompting_config` greps surface only docs slated for Phase 4.
- [ ] Gates: stage + `make agent-check`, **full `make agent-test`**.

### ✋ CHECKPOINT 2 — HARD STOP

Do not start Phase 4 without Louis' explicit go. This is the point-of-no-return review of the behaviour flip. Present: full diff stats by phase, the green `agent-test` run, and a **before/after rendering of one real prompt** (e.g. from the flipped `test_prompt_image_extraction` case) showing back-ticks → XML. Louis reviews the actual prompt text change, rules on any surprises logged along the way, and decides the commit strategy for Phases 1-3. Update the checkpoint log. Natural fresh-session handoff.

---

## Phase 4 — Migration surfaces: schema, docs, changelog, drift

Schema (mechanical half — cross-repo propagation is release-gated, see follow-ups):

- [ ] `make gms` then `make cms` — the diff is two-sided: `PipeLLMBlueprint` gains `templating_style`; `LLMSetting` loses `prompting_target` and the `PromptingTarget` definition disappears (`TemplatingStyle`/`TagStyle` were already published via `TemplateBlueprint`).

Docs (the design's §8 — replace, don't patch, the dead-premise page):

- [ ] **New authoring page** (e.g. `docs/building-methods/templating-style.md`): the two-level model (pipe > config default), bare-string shorthand vs full table, the tag-style gallery incl. `no_tag`, the compose/img-gen story, xml as house default. Written for authors, not infra.
- [ ] **Delete** `docs/building-methods/adapt-to-llm-prompting-style-openai-anthropic-mistral.md`; update `mkdocs.yml`: both nav entries, the existing legacy redirect re-pointed to the new page, and a new redirect from the deleted path.
- [ ] `docs/features/llm-integration.md` — rewrite the "Prompting Styles" section (its "provider-specific formatting … automatically" claim is exactly what's deleted) + front-matter description; `docs/features/index.md` blurb.
- [ ] `docs/configuration/config-technical/inference-backend-config.md` — drop the (already-stale) prompting field from the model-spec example.
- [ ] `docs/under-the-hood/pipelex-kernel.md` — the flow prose ("derive a prompting style"), the kernel-surface table row, the per-call note; whatever Phase 1 already touched, finish here.
- [ ] `docs/building-methods/pipes/pipe-operators/PipeLLM.md` — new `templating_style` parameter row; inline model-table field list checked (it never documented `prompting_target`, so no deletion there).
- [ ] `docs/building-methods/pipes/pipe-operators/PipeCompose.md` — align wording with the one-name vocabulary; cross-link the new page.
- [ ] `.claude/skills/add-model/SKILL.md` — remove the `prompting_target` authoring step.
- [ ] Verify `docs/CLAUDE.md`'s language-surface note still reads true now that PipeLLM carries the field too.
- [ ] Sweep for stragglers: `grep -ri "prompting" docs/` and judge each survivor.

Changelog:

- [ ] Insert `## [Unreleased]` at the top of `CHANGELOG.md` (the header was consumed by v0.44.0) with a breaking entry, condensed style. Draft: **"Breaking — templating style is now an authoring decision.** How a pipe's inputs are tagged into a prompt is declared on the pipe (`templating_style` on `PipeLLM`: bare tag-style string or full `{ tag_style, text_format }` table) with a single runtime default (`[pipelex.templating_config].default_templating_style`, `xml`). It is no longer derived from model metadata: `prompting_target` is gone from model specs, backend TOMLs and inline model tables, along with the per-target style map. Every prompt rendered for an OpenAI-family model changes shape from back-tick blocks to XML tags; img-gen, search and compose prompts follow the same default instead of a silent triple-backtick fallback." Plus a Changed entry: reasoning budgets are worker-owned, no longer read from `prompting_target`.

Drift:

- [ ] `make drift-plan`; review and ack whatever remains open of `config-docs` / `pipelex-kernel-docs` with honest rationales; append the dogfood observation to `wip/drift-contracts/dogfood-log.md`.
- [ ] Gates: stage + `make agent-check`.

## Phase 5 — Bookkeeping: KF-16 closes, keyless un-holds

- [ ] `wip/parity/README.md` — flip the Phase-2 "slated to become" sentence to closed; update the 2.2 gaps-table row.
- [ ] `wip/parity/SESSION-HANDOFF.md` and `wip/parity/parity-gaps-plan.md` — record KF-16 as closed by this change (name commits by subject, never SHA — this branch may rebase); the §2.2 deferral record's "do not fix by object-only derivation" trap is now moot and can say so.
- [ ] `wip/keyless/keyless-dry-prompts-fix-plan.md` — replace the hold banner: the headline symptom, Part 1, and most of Part 3 are dissolved by construction; re-scope the plan to the surviving residue (`max_prompt_images` unenforced, img-gen param rules skipped, handle-pinned bundles rejected keylessly, the two CLIs disagreeing on `--dry-run` credentials). Re-judging that residue is its own future task, not this one.
- [ ] `wip/keyless/keyless-boot-changes-dry-prompts.md` — a short closing note pointing at the dissolution.
- [ ] This design doc — status flips to built; this plan's checkpoint log completed.
- [ ] Final gates: stage everything, `make agent-check`, **full `make agent-test`**.

### ✋ CHECKPOINT 3 — FINAL HARD STOP

Everything is green and documented; nothing is committed beyond what earlier checkpoints approved. Louis decides: commit/PR shape (one PR vs. Phase 0 split out), whether this branch keeps the `fix/Keyless-dry-run` name or is rebranded (the keyless fix it was cut for has been dissolved, not fixed), and release timing. Present the release-gated follow-ups below. Update the checkpoint log.

## Out of scope here — release-gated / cross-repo follow-ups

- **MTHDS schema downstream sync** (mthds, vscode-pipelex, mthds-ui committed copies) via the `mthds-schema-sync` skill — gated on a released `pipelex` version.
- **MTHDS spec prose** — a pipe-level `templating_style` is a language-surface change owned by the `mthds/` repo; the schema regen is only the mechanical half. A deliverable of its own after release.
- **`pipelex-api` CI** — its openapi check runs only under its own `make check` and has been bitten by pipelex bumps before; verify on the release bump whether the schema change surfaces there.
- **Cookbook / starter sweeps** — no shipped `.mthds` uses any styling surface today, so no migration is expected; a post-release sanity pass confirms.
- **PipeImgGen/PipeSearch authored styling** (D6) — only if a real need appears.

## Checkpoint log

*(Filled in as checkpoints are reached: status of completed phases, decisions taken, open questions, state of the code.)*

- **Checkpoint 1:** *(2026-08-14)* Phase 0 complete. Reasoning-budget resolution is re-homed off `prompting_target`: each worker owns a `reasoning_budget_family` ClassVar (`"anthropic"` on the Anthropic worker, `"gemini"` on the Google worker) and `LLMConfig.get_reasoning_budget` is fully keyword-only with a `family` parameter (its subject grant removed from `subject_grants.toml`). TDD red→green: new twin Anthropic reasoning test module + updated Google/config tests landed red first, went green with the implementation; the tests `del mock_model.prompting_target` so any spec read would raise — this stays valid after Phase 3 deletes the field. `effort_to_budget_maps` TOML keys unchanged. Docs updated (`docs/under-the-hood/reasoning-controls.md`). Gates: `make agent-check` green (two drift contracts honestly reviewed and acked: config-docs, pipelex-kernel-docs); full `make agent-test` green. Verified exit criterion: `prompting_target`'s only remaining consumers are the style path (configs.py `get_prompting_style`, llm_setting.py, model_spec + factory, kernel/llm_ops.py derive path) — Phases 1–3 scope. State: committed standalone on `fix/Keyless-dry-run` (commit "Phase 0 — re-home reasoning budgets off prompting_target"). Open questions: none. Louis' go received 2026-08-14 → Phase 1 underway.
- **Checkpoint 2:** — *(not reached; Phase 2 not started. Session paused after Phase 1 — see the pause note under Phase 2 for the survey already done.)*

  **Phase 1 landed (2026-08-14), committed, all gates green.** What it built: `TemplatingConfig` (single field `default_templating_style`, mounted `pipelex.templating_config`; `prompting_styles` and `get_prompting_style` deleted along with the latter's subject grant), the total resolver `pipelex/kernel/templating_style_ops.py`, the authored `templating_style` union on `PipeLLMBlueprint` / `PipeLLMSpec` / `PipeLLM` with the factory widening the bare-`TagStyle` arm, and both `PipelexKernel` façade calls taking the same optional argument (D4 — the `llm_object` parity-gap docstring paragraph is deleted, the question it adjudicated having dissolved). **The behaviour flip is live:** every OpenAI-family prompt now renders XML instead of back-ticks, because nothing derives a style from model metadata any more.

  One deviation from the plan, recorded under Phase 1: `derive_templating_style` was deleted here rather than in Phase 3, because D1 deletes the config map that was its only data source — leaving it would not type-check. The rest of the Phase 3 deletion batch is untouched.

  Tests added: `test_templating_style_ops.py` (totality, house default, authored-wins), `test_pipe_llm_templating_style.py` (both parsing shapes, spec passthrough, all three factory outcomes), and the `templating_style.mthds` bundle + `test_templating_style_bundle.py` proving the authored field survives parse→load→render. `test_prompt_image_extraction.py`'s two default-shape assertions now supply the resolved style and assert XML; note the `with_images | tag` case asserts `<data>`, not `<pages>` — after `with_images` the value is a plain string with no name of its own.

  Docs touched in-phase (to keep the drift acks honest): `docs/under-the-hood/pipelex-kernel.md` — entry-point table lists `templating_style_ops` and drops `derive_templating_style`, and the flow prose plus the per-call-derivation note use the templating vocabulary. Both `config-docs` and `pipelex-kernel-docs` were reviewed and acked.

  Known and deliberate: the Claude Code `check-mthds` hook rejects `templating_style` in a `.mthds` file because it validates against the plugin's bundled schema, which is stale. `make plxt-lint` regenerates `derived/mthds_schema.json` first and passes. The downstream schema sync is already listed as a release-gated follow-up.
- **Checkpoint 3:** —
