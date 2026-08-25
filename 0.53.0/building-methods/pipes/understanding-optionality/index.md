# Understanding Optionality

Real methods meet values that may legitimately not exist: a nickname that was never provided, a document section that wasn't found, a branch of a condition that decided to produce nothing. Optionality makes that a first-class, declared part of your method's contract — instead of a crash, a fabricated placeholder, or a silent `null`.

This guide explains the presence markers (`?` and `!`), what happens at run time when a value is absent, and the static validation that proves your method handles every possible absence before it ever runs.

## The Presence Markers

A concept reference in a pipe's `inputs` or `output` can carry a presence marker:

| Declaration | Meaning |
|---|---|
| `notes = "Note"` | **Plain** (default): the pipe needs the value. If it is absent, the pipe is skipped (see [lifting](#the-runtime-trichotomy-skip-run-or-fail)). |
| `notes = "Note?"` | **Optional** (`?`): the pipe runs even when the value is absent and handles absence itself. On an output, the pipe may resolve it as a *recorded absence* instead of a value. |
| `notes = "Note!"` | **Force** (`!`, inputs only): the pipe asserts the value must be present — an absent value fails the run loudly with `OptionalValueAbsentError`, carrying the full provenance of where absence came from. |

Two grammar rules keep the model coherent:

- **Markers never combine with multiplicity.** `Note[]?` is invalid (`optional_marker_invalid`): a plural slot is never absent — when nothing is found, it is the **empty list**. Absence is a singular-value notion.
- **Outputs take only `?`.** A force marker on an output has no meaning (a pipe cannot assert its own output into existence).

Concept definitions, `refines`, and structure-field references never carry markers — presence is a property of a pipe's contract, not of a concept.

Markers work the same way in the [expanded slot form](index.md#understanding-the-pipe-contract): the `concept` key takes the identical grammar, so `notes = { concept = "Note?", hints = { intent = "prose" } }` is an optional input carrying a hint.

## The Runtime Trichotomy: Skip, Run, or Fail

At run time, a value slot resolves to a value **or a recorded absence** — never a silent hole. When a pipe is about to run and one of its inputs is absent, the marker decides what happens:

1. **Plain input absent → the pipe is skipped (lifted).** The pipe never runs; a `skipped` absence is recorded for its output, chaining to the upstream absence that caused the skip. Downstream pipes then see that output as absent and the same rule applies — absence propagates until something handles it.
2. **Optional (`?`) input absent → the pipe runs.** The pipe declared it can handle the absence — for template-rendering pipes that means guarding the reference (see [Guarding templates](#guarding-templates-over-optional-inputs)).
3. **Force (`!`) input absent → the run fails loudly.** `OptionalValueAbsentError` names the variable, the pipe, and the provenance chain back to where absence entered the flow.

A skipped pipe with a **plural** output resolves it as a real empty list (per the plural rule above), with a ledger note for observability — so downstream list consumers keep working.

### Absence records and provenance

Absence is carried as data: an `AbsenceRecord` with the variable name, a `kind` (`declared_absent` — a `?` output resolved absent; `skipped` — the producer was lifted; `not_provided` — the caller omitted an optional method input), a human-readable reason, the producing pipe, and the upstream record it chains to. Provenance is captured when absence is produced, not reconstructed at failure time — so a `!` failure or a run report can always tell you *why* a value is missing.

The invariant everywhere: **a pipe run always resolves its declared output — a value, or a recorded absence.** An absent main output is a successful run; the CLI and the API deliver an explicit absence document (`{"absent": true, ...}`), never an empty result.

## Optional Method Inputs

A `?` on your method's entry-pipe input makes it omittable by the caller: leaving it out of `inputs.json` (or the execute request) records a `not_provided` absence instead of raising the missing-input error. Plain and `!` inputs stay required at the boundary.

```toml
[pipe.brief_flow]
type        = "PipeSequence"
description = "Write a brief; enrich it when a hint is provided"
inputs      = { topic = "Topic", hint = "Hint?" }
output      = "Brief"
steps = [
  { pipe = "enrich_hint", result = "enriched" },
  { pipe = "write_brief", result = "brief" },
]
```

Here a caller may provide only `topic`. The `enrich_hint` step (which consumes `hint` plainly) is skipped, and `write_brief` — which takes the enrichment as `Enriched?` — runs with it absent.

## Guarding Templates Over Optional Inputs

A template that renders an optional input must guard the reference — otherwise validation rejects it (`optional_input_unguarded`). Three guard idioms are recognized:

- **The optional block sigil `@?`** — inserts the input's content when present, renders nothing when absent:

```toml
prompt = """
Write a brief about this topic: $topic

@?enriched
"""
```

- **A presence block** — `{% if enriched %} ... {% endif %}` (any reference inside the block is guarded, including `$enriched` and attribute access).
- **An inline presence conditional** — `{{ enriched.text if enriched else "no enrichment" }}`.

The guard-lint covers every pipe that renders authored templates over its inputs: PipeLLM (prompt and system prompt), PipeCompose (template mode), PipeCondition (expression), PipeSearch, and PipeImgGen.

## Controllers Under Absence

Each controller has a defined behavior when a value inside its flow resolves absent:

- **PipeSequence** — steps consuming an absent value plainly are lifted (skipped), and the absence propagates step to step. The sequence's own declared output must account for it: if the last producing step can be lifted, the sequence output must be declared `?` (otherwise `optional_not_handled`).
- **PipeCondition** — the `continue` outcome resolves the declared output as a **declared-absent** record (memory otherwise unchanged). A condition that can reach `continue` must declare its output `?` (`optional_output_required`). See [PipeCondition](pipe-controllers/PipeCondition.md).
- **PipeParallel** — combining under absence: a `Composite` output omits the absent component (with a ledger note); a structured output absorbs an absent branch into a non-required field as that field's declared default; a **required** field fed by a maybe-absent branch is rejected statically (`optional_branch_required_field`). See [PipeParallel](pipe-controllers/PipeParallel.md).
- **PipeBatch** — absent branch results are **compacted** out of the aggregated list (a list cannot hold a hole). See [PipeBatch](pipe-controllers/PipeBatch.md).

## The Static Safety Net

You never discover an unhandled absence at run time. Validation walks every controller flow and computes, per slot, whether it is guaranteed present or maybe-absent — and requires every possible absence to reach an explicit sink (a `?` boundary, a guard, an absorbing field). The optionality error types:

| Error | Meaning |
|---|---|
| `optional_marker_invalid` | Grammar misuse: a marker combined with multiplicity, or `!` on an output. |
| `optional_not_handled` | A maybe-absent value escapes through a non-optional boundary. The message names the absence origin, the propagation path, and the fixes. |
| `optional_output_required` | A `continue`-reachable PipeCondition without a `?` output. |
| `optional_input_unguarded` | An unguarded template reference to a declared-optional input. |
| `optional_branch_required_field` | A maybe-absent parallel branch feeding a required structure field. |

Two more facts surface on the **valid** report (`pipelex validate`, the agent CLI, and the API) — the first about optionality, the second a mixed bag of advisories that the same report carries:

- **`liftable_pipes`** — every pipe that may be silently skipped at run time, with the slots whose absence triggers the skip and where that absence can come from. Implicit lifting is acceptable *because* it is visible at build time.
- **`warnings`** — advisory lints that never flip the verdict, spanning optionality and the intent-hint vocabulary alike. Every whole-bundle validate channel carries the same set — the protocol report, the agent CLI, the builder's per-bundle operations, and the bare CLI's `validate bundle` and `validate --all`. (`pipelex validate <PIPE_CODE>` makes no bundle-wide claim and prints none of them; neither does the builder's `validate_all`, which carries no `warnings` key at all.)

    - `optional_force_redundant` — a `!` whose slot is guaranteed present in every analyzed flow, so the assertion can never fire and the marker is dead weight.
    - `input_presence_vacuous` — a **method input** (an input of the bundle's declared `main_pipe`) that must be supplied, but whose concept declares no required field. The empty object satisfies it, so the declaration enforces nothing and a caller cannot tell what to fill in. Either mark the input `?`, or give the concept a required field. See [Inline Structures](../concepts/inline-structures.md#all-optional-structures-and-the-input_presence_vacuous-lint).
    - `hint_unknown_key`, `hint_unknown_intent`, `hint_inapplicable_intent` — the intent-hints lints: a hint key this version of the standard does not define, an `intent` word outside the vocabulary, and a known word on a site it does not apply to. Hints are non-normative, so the entry is preserved and only named.

## Best Practices

- **Declare `?` at the boundary you mean it.** An optional method input is a statement to your callers; an optional output is a statement to your consumers. Inside the flow, prefer letting plain pipes lift over sprinkling `?` everywhere — the skip semantics usually express "no input, no output" exactly.
- **Guard every optional reference in templates** with `@?` when you just want the content inserted, or `{% if %}` when the surrounding prose changes with presence.
- **Reserve `!` for genuine assertions** — places where your flow analysis says the value could be absent but you know better and want a loud failure rather than a skip. If the lint says it's redundant, remove it.
- **Check `liftable_pipes` when validating**: it is the list of "this may silently not run" — confirm each entry is intended.

## Related Documentation

- [Understanding Multiplicity](understanding-multiplicity.md) — the other axis of a slot's shape; plural absence is the empty list
- [PipeCondition](pipe-controllers/PipeCondition.md) — the `continue` outcome and its migration notes
- [PipeParallel](pipe-controllers/PipeParallel.md) — combining under absence
- [PipeBatch](pipe-controllers/PipeBatch.md) — compaction of absent branch results
- [Execution Graph Tracing](../../under-the-hood/execution-graph-tracing.md) — skipped nodes, `skip_reason`, and optional data edges
- [Per-Pipe IO Contracts](../../under-the-hood/pipe-io-contracts.md) — how an input's marker is reported on `pipe_io_contracts` as the three-valued `presence`, and an output's as the two-valued `optional`
