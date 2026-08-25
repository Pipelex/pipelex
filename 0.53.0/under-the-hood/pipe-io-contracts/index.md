# Per-Pipe IO Contracts

Every valid `validate` report carries a **`pipe_io_contracts`** map: for each pipe, the typed contract of what it takes in and what it produces. It sits beside the [input-form descriptor](input-form-descriptor.md) on the same report, and the two are keyed identically — by the namespaced `pipe_ref` (`domain.code`) — over exactly the same set of pipes, `PipeSignature` placeholders included.

Reach for `pipe_io_contracts` when you need the schema and the declared contract; reach for `input_form` when you are building a form and want field kinds, defaults, and choices without reading schemas.

## Where it lives

- `pipelex/pipeline/pipe_io_contracts.py` — the wire models (`PipeInputContract`, `PipeOutputContract`, `IOMultiplicity`) and the one public derivation, `build_pipe_io_contracts(pipes)`.
- `PipelexValidationReport.pipe_io_contracts` (`pipelex/pipeline/validation_report.py`) — where the artifact travels.
- `pipelex/pipeline/validate_in_process.py` — the in-process assembly derives it inside the validation library's window, right beside `build_input_form`. Iterating the same loaded pipes is what makes the two key sets equal by construction.

## What an entry carries

Each pipe gets an `inputs` map and one `output`.

An **input entry** carries the `concept_ref`, the JSON Schema of its content (`json_schema`), and two facts about the slot as declared:

- `presence` — the authored marker, verbatim: `plain`, `optional` (`?`, the caller may omit it and the pipe handles absence itself), or `force` (`!`, must be provided, and the author asserted so). `plain` and `force` are both required; the distinction is the assertion, which lint and graph surfaces read.
- `multiplicity` — `single`, `variable` (`Concept[]`, unbounded), or `fixed` (`Concept[N]`), with `item_count` carrying the exact N on the `fixed` arm and `null` otherwise. `Concept[1]` is `single`: no list framing.

An **output entry** carries `concept_ref`, the same `multiplicity` / `item_count` pair, and a two-valued `optional` — `!` is rejected on outputs, so there is nothing three-valued to report. It carries **no `json_schema`**: the schema render runs per input only. A consumer that wants the output's payload shape gets it from [`build output --format schema`](../tools/cli/build/output.md), not from this contract.

## Where the concept identity sits on the schema

The JSON Schema on an input names its concept: `title` is the `concept_ref`, `description` the concept's authored description. On a `single` slot those sit at the top level; on `variable` and `fixed` slots the schema is an array wrap that keeps them on `items`, and a fixed count adds `minItems`/`maxItems` on the wrap itself. A variable list carries no bounds.

```json
{
  "type": "array",
  "items": { "type": "object", "title": "my_domain.Gadget", "description": "…", "properties": { "…": "…" } },
  "minItems": 2,
  "maxItems": 2
}
```

## Which surfaces carry it

The protocol `validate` operation carries `pipe_io_contracts` on its report. The [Agent CLI](../tools/cli/agent-cli.md#validate) does not: `pipelex-agent validate` emits the verdict, `pending_signatures`, `is_runnable`, and its own advisory `warnings` array, and stops there — the typed contracts are not part of its envelope.

## Seeing it

`pipelex-dev trace-input-semantics` captures the contracts as `hop5_pipe_io_contracts.json` beside `hop5_input_form.json`, so an authored fact can be checked on both projections at once — see [Tracing Input Semantics](../contribute/trace-input-semantics.md). The emitted shapes are pinned by `tests/integration/pipelex/pipeline/test_pipe_io_contracts.py`.

## Related Documentation

- [Input-Form Descriptor](input-form-descriptor.md) — the renderer-facing view of the same inputs
- [Understanding Optionality](../building-methods/pipes/understanding-optionality.md) — the markers behind `presence`
- [Understanding Multiplicity](../building-methods/pipes/understanding-multiplicity.md) — the bracket notation behind `multiplicity`
