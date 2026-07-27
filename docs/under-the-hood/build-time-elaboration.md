---
title: "Build-time Elaboration"
description: "How Pipelex rewrites high-level MTHDS directives — like structuring_method = preliminary_text — into concrete pipe trees before any pipe runs."
---

# Build-time Elaboration

Some MTHDS directives are **shorthands**: they describe what the user wants in one line, but the executable form needs several pipes wired together. Rather than handle them in the runtime, Pipelex rewrites them at load time, before any pipe runs. The runtime sees only normal pipes — `PipeLLM`, [`PipeStructure`](../building-methods/pipes/pipe-operators/PipeStructure.md), [`PipeSequence`](../building-methods/pipes/pipe-controllers/PipeSequence.md), and so on.

Today, exactly one directive is elaborated: `structuring_method = "preliminary_text"` on a [`PipeLLM`](../building-methods/pipes/pipe-operators/PipeLLM.md). This page documents the mechanism so contributors and AI agents can reason about it.

## Where it runs

`BundleElaborator.elaborate(bundle)` runs inside `MthdsParser.make_pipelex_bundle_blueprint()`, right after the bundle dict has been validated into a `PipelexBundleBlueprint`. Every code path that loads a bundle from a `.mthds` file goes through it.

The elaborator has a fast-path short-circuit: if no pipe in the bundle carries `structuring_method = "preliminary_text"`, the input bundle is returned unchanged (identity-preserving). Loading a bundle without preliminary-text pipes pays no overhead.

## What `preliminary_text` becomes

Given a user-authored pipe like:

```toml
[pipe.review_restaurant]
type = "PipeLLM"
description = "Write a structured review of a restaurant from a transcript"
inputs = { transcript = "Text" }
output = "RestaurantReview"
structuring_method = "preliminary_text"
prompt = """
Write a thorough review of this restaurant based on the transcript:

@transcript
"""
```

the elaborator replaces the single entry `review_restaurant` with three blueprints:

- **`review_restaurant__draft_text`** — a `PipeLLMBlueprint` that inherits the original `inputs`, `system_prompt`, `prompt`, and `model`. Its output is **always literal `Text`**, regardless of the original output's multiplicity. `structuring_method` is reset to `None` so the elaborator never recurses.
- **`review_restaurant__structure`** — a `PipeStructureBlueprint` with `inputs = { draft_text = "Text" }`, `output = original.output` (preserving multiplicity — `Foo`, `Foo[]`, `Foo[N]`), and `model = original.model_to_structure`. When `model_to_structure` is `None`, `PipeStructure` falls back to the deck's `for_object` LLM choice at runtime — same behavior as the legacy text-then-object path.
- **`review_restaurant`** (replaced) — a `PipeSequenceBlueprint` wrapping the two synthetic steps, keeping the original `inputs`, `output`, and `description`. The original `pipe_code` is preserved so anything that calls or references the pipe (other pipes, `main_pipe`, the run API) keeps working unchanged.

The two synthetic codes are recorded in `bundle.elaboration_metadata`, a side-table on `PipelexBundleBlueprint` that maps each synthetic code to its `parent_pipe_code` and a `step_role` (`DRAFT_TEXT` or `STRUCTURE`). The wrapping sequence is **not** registered — it is the user-facing pipe.

## Why a side-table

`elaboration_metadata` is declared with `Field(exclude=True)`, so it never serializes back to `.mthds`, TOML, or JSON. The runtime `PipeAbstract` has no `parent_pipe_code` field; the user-facing per-pipe blueprint surface is unpolluted by the elaboration concern.

The side-table is the durable source of truth that downstream tools (graph viewer, CLI listings, distributed traces) can consult to render synthetic pipes specially. Today they don't — synthetic pipes appear as regular pipes in logs and traces — but the metadata is in place so that opt-in can land later without another round of plumbing.

### Lifetime

`elaboration_metadata` is **process-local**. It survives `model_copy` (used by the elaborator itself), but any `model_dump` → `model_validate` round-trip drops the side-table — that is what `exclude=True` buys us. The elaborator's own re-validate pass (`model_validate(elaborated.model_dump(by_alias=True))`) discards the rehydrated bundle and returns the original `model_copy`-built one with metadata intact, precisely because of this.

Practical consequences:

- Within a single process, after `BundleElaborator.elaborate(...)`, the metadata is available everywhere the bundle goes.
- Across any serialization boundary — kajson dump, library cache, Temporal payload, MTHDS export — the metadata is gone. Downstream consumers that need it today have to re-elaborate.
- The dependency loader handles one specific consequence: when a manifest restricts exports, synthetic helpers of exported parents are still loaded, even though they are never named in the manifest. This is implemented inline in `LibraryManager._load_single_dependency`.

When a future consumer (graph viewer, persistent observability store) wants the metadata across boundaries, dropping `exclude=True` is the deliberate next step.

## Multiplicity rule

Step 1 always produces a single `Text`, even when the original output was `Foo[]` or `Foo[3]`. Step 2 is the one that fans out: `PipeStructure` inspects its declared `output` and either calls `make_object` (single) or `make_object_list` (list, with optional fixed `nb_items`). This matches the deleted `make_text_then_object_list` behavior verbatim — one preliminary text, structured into N objects.

## Image inputs

The original `inputs` dict (including any image variables) flows through to step 1. Step 2's input dict is hard-wired to `{ "draft_text": "Text" }`. The structuring template references only `{{ text }}`. Image variables therefore appear only on step 1, where they belong — the elaborator does not need explicit drop logic.

## Pre-checks and validation

Three layers guard against authoring mistakes around the output concept:

1. **Construction-time (string)** — `PipeLLMBlueprint.validate_preliminary_text_output` (a `model_validator(mode="after")`) rejects a literal Text output (`"Text"`, `"native.Text"`, `"Text[]"`, `"Text[N]"`) combined with `structuring_method = "preliminary_text"`. This fires during `model_validate`, before the elaborator runs, so the user gets the error at parse time with a normal Pydantic validation failure.
2. **Defense-in-depth (string)** — `BundleElaborator._elaborate_preliminary_text` re-runs the same string check. Only reachable if a caller bypasses validation via `model_construct`; the test suite exercises it, but nothing in the framework relies on the bypass.
3. **Library-time (concept)** — `PipeStructure.validate_output_with_library` runs once the elaborated `PipeStructure` resolves its concept against the loaded library. This is the only layer that catches a *domain concept* that `refines = "Text"` — those slip past the string-level guards because they don't read as `Text` in the bundle source. A clean separation: string-level guards run at parse time; concept-level guards run at library load.

The elaborator additionally:

- Verifies that the synthetic codes (`<pipe_code>__draft_text`, `<pipe_code>__structure`) don't already exist in the bundle.
- Verifies that the synthetic codes pass `is_pipe_code_valid` (snake_case).
- After producing the new bundle, re-runs `PipelexBundleBlueprint.model_validate(elaborated.model_dump(...))` so bundle-level validators (concept refs, pipe refs, `main_pipe`) re-check the synthetic pipes. Any `ValidationError` here is wrapped in `PipelexUnexpectedError`, with a message naming the bundle's `domain` and the sorted list of synthetic pipe codes (`BundleElaboratorError` is used only for the earlier synthesis-time checks during the same `elaborate()` call).
- Asserts that no synthesized blueprint itself carries `structuring_method = "preliminary_text"` — a recursive-elaboration guard. Today's synthesis explicitly sets `None`; the guard protects against future elaboration kinds copying fields wholesale.

## Cost and runtime semantics

A `preliminary_text` pipe issues **two LLM calls per invocation** (one for the draft text, one for the structuring step). The reporting layer counts both — the integration tests assert exactly two `LLMTokensUsage` records per run.

Runtime, including the Temporal data path, has no knowledge of `structuring_method`. Temporal sees only the elaborated form (`PipeSequence` + `PipeLLM` + `PipeStructure`); the existing `PipeOperator` machinery covers it.

## When to add a new elaboration kind

`BundleElaborator` is intentionally narrow today. Adding a second kind means:

1. A new directive on a blueprint (e.g. another field on `PipeLLMBlueprint` or a new field on a different blueprint).
2. A construction-time validator that rejects nonsensical combinations of the directive with other fields.
3. A new private method on `BundleElaborator` (`_elaborate_<kind>`) that synthesizes the replacement pipes and registers metadata.
4. Extending the `_is_<kind>_pipe` `TypeGuard` set + dispatch in `elaborate`.

When the second kind lands, the dispatch logic should be promoted to a small registry keyed by directive — but not before. One concrete consumer is enough; two is a pattern.

## Related

- [`PipeLLM` › Structuring Method (preliminary_text)](../building-methods/pipes/pipe-operators/PipeLLM.md#structuring-method-preliminary-text) — the user-facing surface.
- [`PipeStructure`](../building-methods/pipes/pipe-operators/PipeStructure.md) — the operator that backs step 2.
- [`PipeSequence`](../building-methods/pipes/pipe-controllers/PipeSequence.md) — the controller that wraps the two synthetic steps.
