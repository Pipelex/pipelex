# `tokens_usages.json` carries no run total, so every consumer sums it themselves

Status: **not started.** Found 2026-08-14, wiring the run cost into pipelex-app's Run Details panel.

## What is missing

`_generate_usage_file` (`pipe_run/delivery_executor.py`) writes the durable usage artifact as a two-field envelope:

```python
usage_doc: dict[str, Any] = {
    "tokens_usages": dump_tokens_usage_records(pipe_output.tokens_usages),
    "usage_assembly_error": pipe_output.usage_assembly_error,
}
```

A flat list of per-call records, each with its own `cost`, and nothing that says what the **run** cost. A real 8-call run delivers this and no total:

```
extract_pages           azure-document-intelligence  $0.030000
extract_header          claude-4.6-sonnet            $0.036186
…six more…
                                          run total   (absent)
```

So every consumer that wants "what did this run cost" has to iterate and add up — which is arithmetic on money, performed by whoever happens to be asking, in whatever language they happen to be writing.

## Why the graph spec is not the answer

`GraphSpec.usage.total.cost` already holds exactly this number, and pipelex-app reads it today (`src/lib/run-cost.ts`). That is a **stopgap and is documented as one**, for three reasons:

- **The graph is optional.** `is_generate_graph = false` and the total silently vanishes, while the usage artifact is still written — `_generate_usage_file` is called unconditionally, precisely so a client can distinguish "usage assembly was off" from "delivered before the artifact existed".
- **It is a rendering artifact**, sometimes megabytes, fetched in full to read one float.
- **Nothing promises its shape** the way a delivery contract does. `TokensUsageRecord` is `extra="forbid"` and is described in `reporting/usage_records.py` as the client wire contract; the graph spec is not that.

## The trap

There must not be a third way of computing money. Today there are two, and they already agree by construction because both go through `compute_tokens_usage_cost`:

- `CostRegistry.aggregate_costs` → the CLI cost table and the agent CLI's JSON summary.
- `GraphUsageSpec.total` → the run graph's rollup.

A stored total must come from that same engine and must equal `graph_spec.usage.total.cost` for the same run. Two artifacts from one run quoting different prices is worse than no total at all.

Carry the three-valued semantics with the number, do not flatten them:

- `cost is None` ⟺ **unrated** (no rate table). Never render as `0`. A consumer that coerces this to zero tells the user the run was free.
- `rated_inference_calls < inference_calls` ⟹ the total is a **lower bound**, not a price.
- `unattributed` exists on the graph rollup so the graph's total can never silently disagree with the cost report's; whatever shape is stored should keep that property or explicitly not need it.

## Shape question to settle first

Two options, and the choice is a contract decision rather than an implementation one:

1. **Add a `total` object to the envelope**, reusing the same shape as the graph's `NodeUsageSpec` total (calls, rated calls, cost, cost_input/output, by_model). Consistent with the graph, richer, and answers per-model questions too. Costs a new public wire type.
2. **Add a scalar pair** (`total_cost: float | None`, `total_rated_inference_calls: int`). Minimal, but a consumer wanting per-model breakdown is back to summing the list.

Option 1 is probably right — the app's Run Details panel wants the cost, but the billing surfaces will want per-model — and it keeps one usage vocabulary rather than inventing a fifth (`reporting/usage_records.py` already makes that argument for the record shape).

## The rest of the chain already exists

This is smaller than it looks. Downstream of pipelex, everything is wired:

- `pipelex-server/platform/.../routers/v1/runs.py` already fetches `tokens_usages.json` and unpacks its envelope onto `RunResultsResponse` — it needs one more field.
- `pipelex-sdk-js/src/runs.ts` already declares `tokens_usages` and `usage_assembly_error` on `RunResults` — one more field.
- `pipelex-app`'s `fetchRunResults` currently drops both on the floor (it maps only `graph_spec` / `main_stuff` / `working_memory`); it needs to stop doing that.

Rough size: half a day in pipelex including tests and changelog, ~1h in platform (**needs a version bump** — an already-published tag is a green no-op, so a forgotten bump ships nothing and reports success), ~30min in the SDK plus a publish, half a day in the app.

## Consumer waiting on this

`pipelex-app` → `src/lib/run-cost.ts`, and its `TODOS.md` entry "Store the run total cost in `tokens_usages.json`". When this lands, that module swaps its source and the graph spec stops being a data source for the app.
