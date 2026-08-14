# Prompt style as an authoring decision

**Design note, 2026-08-14.** Status: **✅ built** — all §7 rulings settled by Louis 2026-08-14 and implemented on `fix/Keyless-dry-run` across Phases 0–5 of [`templating-style-implementation-plan.md`](templating-style-implementation-plan.md), whose checkpoint log is the build record. One ruling overrides the body: the authored field is **`templating_style` everywhere** (§4.1's `prompt_style` proposal was not retained). Written on `fix/Keyless-dry-run` but deliberately scoped to stand alone — the keyless dry-run bug is what surfaced this, not what motivates it. See §9 for the relationship.

**Read the body as the design, not as the current code.** It argues from a world where `prompting_target` exists; that field, the `PromptingTarget` enum, the per-target style map and `derive_templating_style` are all deleted. Two things landed beyond what this note designed, both consequences of the strict-filter ruling in §4.3: the `TICKS`/`PLAIN` fallbacks in the Jinja2 filters are gone (a style-less render of a filter-bearing template now raises), and every prompt-rendering entry point — including compose, image generation, search, construct-mode template fields and the built-in structuring prompts — resolves a real style rather than only the LLM path. User-facing documentation is [`docs/building-methods/templating-style.md`](../../docs/building-methods/templating-style.md).

The direction itself is older: Louis first ruled the model-derived mechanism obsolete on 2026-08-03, during the parity-gaps/kernel-extraction work, and it was deferred as **KF-16**. This doc supersedes that deferred note (formerly this directory's `README.md`, deleted — its inbound pointers, the `PipelexKernel.llm_object` docstring and the `wip/parity/` docs, were re-aimed here).

## 1. The change in one sentence

**How a method's inputs get tagged into a prompt becomes something the method author declares, not something the runtime infers from which provider happens to serve the model.**

## 2. Why, independent of any bug

**The premise it rests on has expired.** The whole mechanism exists to send back-ticks to OpenAI models and XML to Anthropic ones. That distinction is several model generations old; every current frontier model handles XML tags well, and Anthropic still actively recommends them. A per-provider dialect map is now maintaining a difference that no longer pays for itself.

**The data is infra-shaped and partly arbitrary.** `prompting_target` is declared once per backend in each spec file's `[defaults]` block (`pipelex/kit/configs/inference/backends/*.toml`), with a handful of per-model overrides in `portkey.toml`. It does not track the backend — bedrock, minimax, ollama and xai all declare `anthropic`. For bedrock and minimax that is considered (they really are Anthropic-dialect endpoints). For ollama it is close to meaningless: ollama serves whatever you pull into it, and every one of those models is being told the same dialect. The field's accuracy degrades exactly where the backend is a multiplexer, which is the direction the ecosystem is moving.

**Prompt shape is a property of the method, not of the machine.** A method is meant to be portable — written once, run against whatever model is available. Today, moving a method from an OpenAI preset to an Anthropic one silently rewrites every prompt it renders. The author never asked for that and cannot see it in the `.mthds` file. If tag style materially affects output quality, it belongs where the author can read, diff, review and version it. If it doesn't, it shouldn't be per-model at all. Either way the current placement is wrong.

**There are three defaults today, in three layers, and they disagree.** This is the strongest argument, because it means the current behaviour is not a design at all:

| # | Site | Value | When it applies |
| --- | --- | --- | --- |
| 1 | `pipelex.toml` → `prompting_config.default_prompting_style` | `xml` | Only when a `prompting_target` **is set but unrecognised**. Unreachable when the target is absent — `PromptingConfig.get_prompting_style(None)` returns `None`, not the default. |
| 2 | `tools/jinja2/jinja2_filters.py:120-122` (`apply_tag_style`) | `TICKS` | Whenever `TAG_STYLE` was never put on the Jinja2 context — i.e. the actual fallback for "no style", in the tools layer, several layers below anyone who could have decided. |
| 3 | `cogt/llm/llm_prompt_template.py:93` | `xml` + `markdown`, hardcoded | The `LLMPromptTemplate` path, which appears to be dead (referenced only from its own module and `cogt/exceptions.py` — confirm and delete). |

So the setting named "default prompting style" is not the default, and the real default lives in a Jinja2 filter. Any change to this area has to collapse these to one regardless of which way the per-model question goes.

## 3. What exists today

**The resolution chain.** `pipelex/kernel/llm_ops.py:62-75`:

```
llm_setting.model (handle)  →  deck.get_optional_inference_model(handle)  →  spec.prompting_target
  →  prompting_config.prompting_styles[target]  →  TemplatingStyle(tag_style, text_format)
    →  Jinja2 context TAG_STYLE / TEXT_FORMAT  →  the `| tag` and `| format` filters
```

The handle is only a lookup key; nothing parses it. `prompting_target` is a model-family label, and `TemplatingStyle` is the pair of knobs that actually does anything.

**`prompting_target` has a second consumer that is not about prompting.** `cogt.llm_config.effort_to_budget_maps` is keyed by it, and the Anthropic and Google workers read `inference_model.prompting_target` to resolve a thinking budget, raising *"has no prompting_target configured, cannot resolve reasoning budget"* when it is absent (`providers/anthropic/anthropic_llm_worker.py:180-185`, `providers/google/google_llm_worker.py:149-154`, `cogt/config_cogt.py:96`). This is the one hard blocker — see §6.

**Authoring surfaces that already exist**, and which this design extends rather than invents:

- `TemplateBlueprint.templating_style` (`cogt/templating/template_blueprint.py:15`), described in its own field docstring as *"Style of prompting to use (typically for different LLMs)"*. Used by `PipeCompose` and by `PipeImgGen`'s prompt assembly (`kernel/img_gen_prompt.py:245-249`). So an authored style is already a language concept — it just doesn't reach `PipeLLM`.
- `PipeComposeSpec.target_format` — the spec layer's friendly enum widening into a `TemplatingStyle`, the precedent for a shorthand.
- `LLMSetting.prompting_target` — reachable today from a deck preset or an inline `.mthds` model table (`model = { model = "gpt-4o-mini", temperature = 1, prompting_target = "anthropic" }`). No shipped config uses it, and `derive_templating_style` ignores it anyway when the deck lacks the model.

## 4. The design

### 4.1 Vocabulary

One concept, one type. `TemplatingStyle` stays the type (`tag_style` + `text_format`). The authored field on a `PipeLLM` is **`prompt_style`**, because there the thing being styled *is* the prompt. `PipeCompose` keeps `templating_style` inside its `template` table, because a composed template may render HTML that never reaches an LLM — calling that a "prompt style" would be a lie. Two names for one type is a real cost; §7 asks for a ruling rather than pretending it isn't.

`PromptingTarget` (the `openai` / `anthropic` / `mistral` / `gemini` / `fal` enum) disappears from style selection entirely. Authors do not think "my target is openai"; they think "tag my inputs with XML".

### 4.2 Two levels, pipe wins

1. **The pipe** — `PipeLLM.prompt_style`. For a step that needs a specific shape.
2. **The runtime config** — `pipelex.prompting_config.default_prompt_style`. The value every pipe gets when it says nothing; house style for an org that wants one.

Resolution is a **total function**: `pipe.prompt_style or config.default_prompt_style`. It consults no deck, no model spec, no credentials — which is why the result cannot depend on how the process booted.

(A domain-level `prompt_style` inheriting down like `system_prompt` does was considered and **rejected — Louis, 2026-08-14**: two levels are enough. If a whole method genuinely wants one style, that is what the config default is for; don't add a third place to look.)

### 4.3 The invariant: there is no "no style"

The resolver never returns `None`. That is the load-bearing part, and it is what collapses the three defaults of §2:

- `templating_style: TemplatingStyle | None` stops being optional along the prompt-rendering path — concretely, the kernel ops `run_llm_text` / `run_llm_object` and `assemble_llm_prompt` take a plain `TemplatingStyle` (the tightening the KF-16 note already anticipated).
- The `TICKS` fallback in `apply_tag_style` becomes unreachable and gets **deleted**. A missing `TAG_STYLE` on the Jinja2 context stops being a silent default and becomes what it actually is — a bug.
- The hardcoded `xml`/`markdown` in `llm_prompt_template.py` goes with the module, if that module is indeed dead.

It also disposes of the "external LLM plugin" case cleanly: a model served by a plugin the deck knows nothing about no longer gets to have an opinion about prompt shape, because nothing about prompt shape is read from a model any more.

### 4.4 The authored surface

A string shorthand that widens into the struct — the same idiom `PipeComposeBlueprint.template: str | TemplateBlueprint` already uses:

```toml
[pipe.extract_clauses]
type   = "PipeLLM"
prompt = "Extract the clauses from $contract"          # says nothing → config default (xml)

[pipe.summarize_verbatim]
type         = "PipeLLM"
prompt       = "Summarize $clauses"
prompt_style = { tag_style = "no_tag", text_format = "markdown" }   # this one step differs
```

Bare string = `tag_style`, the overwhelmingly common case. Inline table = the full `TemplatingStyle`. `no_tag` is already in the enum and becomes a genuinely useful authoring choice ("don't wrap my inputs in anything").

### 4.5 Layering

Per the spec-vs-blueprint split: `PipeLLMBlueprint` gets `prompt_style` (language), `PipeLLMSpec` gets the matching authoring field mapped through `to_blueprint()` (convenience). The resolver belongs next to the other kernel prompt semantics, replacing `derive_templating_style` in `kernel/llm_ops.py`.

### 4.6 What gets deleted

- `InferenceModelSpec.prompting_target` and every `prompting_target` line in the kit's backend spec TOMLs.
- `LLMSetting.prompting_target`.
- `PromptingConfig.prompting_styles` (the target → style map in `pipelex.toml`).
- `PromptingTarget` itself, once §6 lands.
- The `TICKS` fallback in `apply_tag_style`, and `derive_templating_style`'s deck lookup.
- The `PipelexKernel.llm_object` docstring paragraph recording the parity-gap 2.2 adjudication — why its single `model` carries the text-choice semantics for templating, the "do not fix by deriving from an object-only resolution" trap, and its pointer to this directory (`pipelex/kernel/pipelex_kernel.py`). With derivation gone, prompt style no longer depends on which model resolution ran, so the question that paragraph adjudicates dissolves. **KF-16 closes with this change** — update the `wip/parity/` docs that carry it.

## 5. One resolver, every prompt

The resolver must serve **every pipe that renders a prompt**, not just `PipeLLM`. Today `PipeImgGen`'s prompt renders with whatever `TemplateBlueprint.templating_style` the author supplied, which is normally nothing — so it falls into the same `TICKS` default from the same filter. Once the resolver is total, img-gen and compose prompts inherit the config default the same way, and the author gets one mental model instead of three.

Note that the style is consumed **before** dispatch — `assemble_llm_prompt` renders in the interpreter and the content generator receives an already-rendered `LLMPrompt` — so nothing about this has to cross the transport boundary for `PipeLLM`. `TemplatingAssignment.templating_style` (`cogt/content_generation/assignment_models.py:116`) does travel, for the compose path; it is a plain pydantic field and stays as-is.

## 6. The blocker: reasoning budgets must move first

`effort_to_budget_maps` is keyed by `prompting_target`, so deleting the field breaks thinking-budget resolution on Anthropic and Google. The fix is small and improves things: **the worker already knows its own family.** The Anthropic worker is the Anthropic worker; it does not need a config field to tell it so. Have each worker supply its own budget-map key, keep the config map keyed as it is (`anthropic`, `gemini`), and rename the concept so it stops borrowing the word "prompting" for something that is about reasoning effort.

This is a prerequisite, not a follow-up. Sequence it first so that removing `prompting_target` is a pure deletion.

## 7. Rulings — all settled (Louis, 2026-08-14)

- **Naming: `templating_style` everywhere.** One name for the one type, on PipeLLM and PipeCompose alike — the §4.1 proposal of `prompt_style` on PipeLLM was not retained. Accepts that "templating" is the broader word; avoids two names for one type. Config vocabulary follows (see the implementation plan's derived decisions).
- **The new global default: `xml` + `plain`**, as proposed. OpenAI-family prompts flip from back-ticks to XML — the point of the change.
- **No per-model or per-preset override survives.** Pure two-level resolution: pipe > config default, nothing else. The infra-side lever is removed entirely.
- **The authored surface is the full `TemplatingStyle`.** Bare string = `tag_style` shorthand (the common case); inline table = the full struct including `text_format`.

## 8. Migration and blast radius

- **Every prompt rendered for an OpenAI-family model changes shape** — from `` name: ``` `` back-tick blocks to `<name>` XML tags. This is the point of the change, not a side effect, but it is a change to the actual text sent for a large share of shipped methods and should be stated plainly in the changelog. Anything with recorded prompt goldens will move.
- **Test fixtures and goldens** that assert rendered prompt text will need regenerating; grep for both tag shapes.
- **Schema propagation.** `PipeLLMBlueprint` gaining a field changes the MTHDS JSON Schema: regenerate with `pipelex-dev generate-mthds-schema`, then propagate to the downstream committed copies via the `mthds-schema-sync` skill, gated on a released `pipelex` version.
- **Config shape.** `prompting_config` loses `prompting_styles` and renames its default — the config model and every `pipelex.toml` must move together or boot fails; `make tb` is the quick check.
- **Docs.** Prompt style becomes an authoring topic (a page under method authoring) rather than an inference-config topic; the backend-config docs lose a field. One whole published page is premised on the old mechanism — `docs/building-methods/adapt-to-llm-prompting-style-openai-anthropic-mistral.md` ("adapt prompting styles for OpenAI, Anthropic, Mistral…"), linked from `docs/features/llm-integration.md` — replace it with the authoring page rather than patching it; even its URL states the dead premise.
- **MTHDS spec.** A pipe-level `templating_style` is a language-surface change, which the `mthds/` spec repo owns — the JSON-Schema regen and downstream sync above are only the mechanical half; the spec prose is a deliverable of its own.
- **No backward compatibility**, per repo policy: no deprecation window, just the changelog entry.

## 9. Relationship to the keyless dry-run bug

`wip/keyless/` documents a bug where a process booted without credentials renders different prompts than one booted with them, because prompt style is derived from model metadata that only loads with credentials. **This design dissolves that bug rather than fixing it** — once style depends on nothing but authored declarations and config, a keyless boot and a keyed boot agree by construction.

That is a consequence, not a justification. The keyless investigation has its own residue that survives this change and must still be judged on its own merits: `max_prompt_images` unenforced, img-gen param rules skipped, and handle-pinned bundles *rejected* on a keyless machine. Settle prompt style first; then re-open `wip/keyless/keyless-dry-prompts-fix-plan.md` with a smaller and clearer question.
