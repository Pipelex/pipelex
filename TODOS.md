# Determinism: prompt rendering must not mutate library-held pipe objects

**Branch:** `refactor/Determinism`

**Status: COMPLETE.** All three phases done. Every design claim was verified against the code before implementing (see [Verification log](#verification-log)). Gates green (`make agent-check`), full suite green (`make agent-test`). The MTHDS schema came out byte-identical and never mentioned `LLMPromptBlueprint` at all. No doc changes were needed. Deviations from the design are recorded at the bottom.

## Problem

Rendering an LLM prompt writes a derived value back onto objects owned by the pipe library. `PipeLibrary.get_required_pipe` (`pipelex/libraries/pipe/pipe_library.py:111`) returns the stored instance — nothing copies it — so these write-backs mutate shared, long-lived state as a side effect of running a pipe. Two sites:

1. `pipelex/pipe_operators/llm/pipe_llm.py:232` — inside `_live_run_operator_pipe`, the operator caches the config-derived prompting style onto its own spec: `self.llm_prompt_spec.templating_style = get_config().pipelex.prompting_config.get_prompting_style(...)`. (Thirty lines above, `resolve_dynamic_output_stuff_spec`'s docstring advertises "Pure: never mutates `self`" — that purity is local to that one method; the run method itself is not pure.)
2. `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:358-359` — `_unravel_text` writes the spec-level style into the caller's `TemplateBlueprint`: `jinja2_blueprint.templating_style = templating_style`. The written value is never even read on this path — the `render_template` call at line 374-379 passes `self.templating_style`, not the blueprint's field — so the write is pure pollution of a library-held object.

Executed proof (three lines: boot dry, build an `LLMPromptBlueprint` with a `TemplateBlueprint`, set `templating_style` on the spec, `await make_llm_prompt(...)`, read `template_blueprint.templating_style`):

```
BEFORE  spec.templating_style=None   prompt_blueprint.templating_style=None
AFTER   spec.templating_style=<set>  prompt_blueprint.templating_style=<set>
SAME OBJECT as spec.prompt_blueprint: True
```

**Consequences:**

- A pipe's `model_dump()` — used by `_make_pipe_data_for_registry` for the graph registry and by the crate payload that travels to a Temporal worker — differs before and after its first run in a process. Serialized output depends on run order.
- The cached value can go stale: a deck reconfigured in-process, or an external-plugin model with no `InferenceModel`, means the first run's cached style silently governs every later run. First run and subsequent runs of the same instance are not equivalent.
- Any harness that compares two executions in one process is measuring a mutated object on the second pass.

## Design

Compute the style into a local and pass it down — the value stays run-scoped, never written onto `self` or the blueprint.

**Key facts established by code reading (verify cheaply before relying on them):**

- `LLMPromptBlueprint.templating_style` has exactly one writer in the tree: the run-time cache at `pipe_llm.py:232`. `PipeLLMFactory.make` (`pipe_llm_factory.py:118-125`) never sets it; no test, doc, or schema references it. The field *is* the cache — remove it (no backward compat, per workspace policy).
- `TemplateBlueprint.templating_style` stays: it is a declared field that the compose and img-gen paths legitimately read (`pipe_compose_blueprint.py:82`, `img_gen_prompt_blueprint.py:294`). On the LLM path the factory never sets it, so it is `None` for every LLM prompt blueprint today.
- The only reader of the config-derived style is `render_template(templating_style=...)`; `get_prompting_style` (`system/configuration/configs.py:84`) is a cheap pure lookup — recomputing per run instead of caching is free and is the *correct* behavior (a deck/config change in-process takes effect on the next run instead of being shadowed by the first run's cache).

**Changes:**

1. `pipe_llm.py::_live_run_operator_pipe`: replace the cache-guard block (lines 226-234) with a local:

   ```python
   templating_style: TemplatingStyle | None = None
   if inference_model := model_deck.get_optional_inference_model(model_handle=llm_setting_main.model, model_type=ModelType.LLM):
       prompting_target = llm_setting_main.prompting_target or inference_model.prompting_target
       templating_style = get_config().pipelex.prompting_config.get_prompting_style(prompting_target=prompting_target)
   ```

   Pass `templating_style=templating_style` to **both** `make_llm_prompt` calls (text branch line ~252, object branch line ~297). Keep the existing TODO comment about external LLM plugins having no inference model.
2. `llm_prompt_blueprint.py::make_llm_prompt`: add keyword-only param `templating_style: TemplatingStyle | None = None`; thread it to both `_unravel_text` calls (system prompt line ~230, user prompt line ~242).
3. `llm_prompt_blueprint.py::_unravel_text`: add the same param; delete the write-back (lines 358-360); compute the effective style into a local and hand it to `render_template`:

   ```python
   effective_style = jinja2_blueprint.templating_style or templating_style
   ```

   Blueprint-declared style wins over the run-derived one — that is the evident intent of the old guard (`and not jinja2_blueprint.templating_style`), and it fixes the latent inconsistency where the blueprint's own style was respected by the write-back guard but then ignored by the render call. Behavior-identical today on the LLM path (the factory never sets the blueprint field), but now coherent.
4. `llm_prompt_blueprint.py`: remove the `templating_style` field from `LLMPromptBlueprint` (line 30). It has no remaining reader or writer after 1-3.
5. Default param stays `None` so the many existing `make_llm_prompt` call sites in `tests/integration/pipelex/pipes/llm_prompt_inputs/` keep working unchanged (they exercise image/document extraction, not styling).

**Non-goals:**

- `TemplateBlueprint` model and the compose / img-gen styling paths — untouched.
- `WorkingMemory` mutation semantics (`set_new_main_stuff`) — separate concern, out of scope.
- Other library-held-object mutation hazards, if any turn up — file them, don't fix them here.

## Phase 0 — Red tests (TDD)

- [x] New test module, e.g. `tests/unit/pipelex/pipe_operators/pipe_llm/test_prompt_rendering_purity.py`:
  - [x] **Blueprint-level purity:** build an `LLMPromptBlueprint` with a `prompt_blueprint` `TemplateBlueprint`, snapshot `spec.model_dump()`, `await make_llm_prompt(...)` with a style passed in (and a minimal context provider — reuse whatever the `llm_prompt_inputs` integration tests use), assert `template_blueprint.templating_style is None` afterward and `spec.model_dump()` is unchanged. This is the executed proof from the problem statement, inverted into a regression test.
  - [x] **Effective-style precedence:** a `TemplateBlueprint` with an explicit `templating_style` renders with its own style even when a different one is passed in; a blueprint without one renders with the passed style. Assert via the rendered output or by monkeypatching/spying `render_template` — whichever the existing test idiom supports (check `tests/unit/pipelex/tools/test_template_content_rendering.py` for the established pattern).
  - [x] **Pipe-level purity (site 1):** run a `PipeLLM` in dry mode, snapshot `pipe.model_dump()` before and after, assert identical. Dry run boots without inference; follow the boot pattern used by existing dry-run tests.
- [x] Run the new module only (`.venv/bin/pytest -x -q <module>`), confirm the purity tests are **red** against the current code (the precedence test may need the new param to exist first — it can start as red-on-TypeError).

## Phase 1 — Implement

- [x] Changes 1-4 above, in one pass (they are interlocking; the field removal is what makes the compiler/type-checker find any reader the grep missed).
- [x] Re-grep `templating_style` across `pipelex/` to confirm the only remaining occurrences are `TemplateBlueprint`, the compose/img-gen paths, jinja2 plumbing, and config.
- [x] New params are keyword-only (both methods already have `*`-sections — add the param after `*`).
- [x] Run the Phase 0 module: all green.

## Phase 2 — Gates, docs, changelog

- [x] `make agent-check` — includes the mthds-schema regen; inspect the `derived/mthds_schema.json` diff. Expected: no change (`LLMPromptBlueprint` is factory-built, not part of the parse surface). If it *does* change, stop and reassess — that would mean the field was on a documented surface after all.
- [x] `git diff` review: no stray edits, no leftover guard at `pipe_llm.py:226`.
- [x] Grep `docs/` for `templating_style` / prompting-style caching claims; update anything that describes the old cache-on-first-run behavior.
- [x] `CHANGELOG.md` under `[Unreleased]`:
  - Fixed: rendering an LLM prompt no longer mutates the library-held pipe (`templating_style` write-backs removed); a pipe's serialized form is now identical before and after runs, and in-process config/deck changes take effect on the next run instead of being shadowed by a first-run cache.
  - Changed (breaking): `LLMPromptBlueprint` no longer has a `templating_style` field; `make_llm_prompt` takes the style as a parameter.
- [x] `make agent-test` — full suite.

## Checkpoint — wrap-up

- [x] Update this file: mark phases done, record any deviations from the design (especially if the schema diff or the doc grep turned something up).
- [x] Commit on `refactor/Determinism`. Do not push or open a PR without explicit go-ahead.

## Verification log

Each "key fact" the design said to verify cheaply, and how it actually checked out:

- **One writer, no stray readers.** A tree-wide grep for `templating_style` (py/toml/mthds/json/md) confirms `LLMPromptBlueprint.templating_style` had exactly one writer (`pipe_llm.py:232`) and two readers, both inside `_unravel_text`. Zero references in tests, docs, or the schema. Confirmed removable.
- **The factory never sets it.** `pipe_llm_factory.py` contains no occurrence of `templating_style` at all; it builds `LLMPromptBlueprint` without the field and its `TemplateBlueprint`s without a style.
- **Nothing on the LLM path can declare a blueprint-level style.** `PipeLLMBlueprint.prompt` and `system_prompt` are plain `str | None` — no nested template section, unlike PipeCompose's `template`. So the new precedence rule (`jinja2_blueprint.templating_style or templating_style`) is unreachable-by-declaration on the LLM path today, and the change is a coherence fix rather than a live behavior change. Worth re-checking if PipeLLM ever gains a rich prompt section.
- **The dry path really does reach the mutating code.** `PipeLLM` does not override `_dry_run_operator_pipe`, and the `PipeOperator` default delegates to `_live_run_operator_pipe`. This is what makes the dry-run purity test a valid guard on site 1 rather than a vacuous pass.
- **The mutation is observable with the default deck.** Probed before writing the test: the default text model resolves to `claude-4.6-sonnet`, whose `LLMSetting.prompting_target` is `None` but whose `InferenceModelSpec.prompting_target` is `anthropic`, deriving a real `xml/plain` style. Had both been `None` the write-back would have been `None`-over-`None` and the pipe-level test would have passed against the unfixed code. Confirmed red for the right reason before implementing (the failure diff named `llm_prompt_spec`).
- **Schema untouched.** `derived/mthds_schema.json` is gitignored, so a snapshot/compare was used instead of `git diff`: byte-identical across the regen, and `LLMPromptBlueprint` appears in it **zero** times — it is factory-built and was never on the parse surface, exactly as the design predicted.
- **Docs clean.** No page describes the cache-on-first-run behavior. The prompting-style page documents only `PromptingConfig` and `get_prompting_style` (both unchanged); `features/llm-integration.md` says provider-specific formatting is applied "automatically", which stays true and is now more accurate. No doc edit needed.

## Deviations from the design

- **Precedence asserted through rendered output, not a spy.** The design left the choice open. Observing the output is stronger and needs no mocking: the XML tag style wraps an `@variable` in `<name>…</name>` while NO_TAG inlines it bare, so the rendered text names the style that actually governed. The test is parametrized over three cases, including a negative one (passed NO_TAG really applies) so the two positive cases can't both pass by accident.
- **`TemplatingStyle` in `pipe_llm.py` sits in a `TYPE_CHECKING` block.** It is used only in a local-variable annotation, so ruff's `TC001` requires it; the module had no `TYPE_CHECKING` block before and gained one (with `TYPE_CHECKING` added to the `typing` import). Local annotations aren't evaluated at runtime, so this is safe. `llm_prompt_blueprint.py` keeps its runtime import — there the name appears in method signatures on a `BaseModel`.
- **The `log.verbose` line changed meaning.** It was `"Setting prompting style to …"`, emitted only when the cache was written; it is now `"Rendering with prompting style …"`, emitted on every render (including when the effective style is `None`). Intentional: with the cache gone there is no "setting" event to report, and the per-render line is the more useful trace.
- **One tuple-vs-string lint nit.** `pytest.mark.parametrize` takes a tuple of names in this repo (ruff `PT006`), not the comma-separated string shown in `.claude/rules/pytest-standards.md`.

## Follow-ups (not done here, per the non-goals)

- `WorkingMemory` mutation semantics (`set_new_main_stuff`) — untouched, separate concern.
- No other library-held-object mutation hazard surfaced during the grep sweep. The `resolve_dynamic_output_stuff_spec` purity docstring noted in the problem statement is now accurate for the whole run method, not just that one helper.
