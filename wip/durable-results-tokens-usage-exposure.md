# Durable-run results drop `tokens_usages` — expose usage on the start+poll path

**Status:** Feature ask from the Fenix workspace (delivery-plan task A6, cost-measurement
exploration, 2026-07-18). Live-verified against hosted api-dev. Full findings:
`~/repos/Fenix/project/designs/a6-cost-measurement.md`.

> **Superseded on the wire shape (2026-07-19):** the "keep it raw records, not a computed $ total" note below was deliberately reversed by the tokens-usage wire contract (workspace `wip/usage/tokens-usage-wire-contract.md`, FINAL). The wire record ships a server-computed `cost` and MUST NOT expose `unit_costs` — rates are the runtime's pricing data, not client contract, and `cost: null` (vs `0.0`) resolves the "zero-cost record" caveat flagged below. Consumers that want a run total sum the per-record `cost` values; the deterministic multiply-and-sum now happens server-side, pinned by parity tests against `CostRegistry`. The artifact/route plumbing described in this doc remains accurate.

## The gap

The engine assembles per-call usage onto `PipeOutput.tokens_usages` (token counts by category +
`unit_costs` $/1M + model id, for LLM **and** img-gen/extract/search), and the sync path returns
it: `POST /v1/execute` → `pipe_output.tokens_usages` — confirmed live (probe run `d020718b…`:
claude-4.6-sonnet, `{input: 15, output: 4}`, `unit_costs {input: 3.0, output: 15.0}` → $0.000105
computable client-side).

But a durable client (`start` + `GET /v1/runs/{id}/results`) never sees it:

- **pipelex** — `pipe_run/delivery_executor.py` `generate_result_files(pipe_output)` receives the
  full `PipeOutput` (so `tokens_usages` + `usage_assembly_error` are in hand) but persists only
  `graphspec.json`, `main_stuff.json` (+ md/html/viewer renders), `working_memory.json`.
- **pipelex-platform** — `src/pipelex_platform/routers/v1/runs.py`
  `_fetch_run_result_artifacts()` reads exactly those three files; `RunResultsResponse` has no
  usage field. Per-node `metrics: {}` in the graphspec sits empty; no
  `/runs/{id}/usage`-style route exists (probed, 404).

Sync `/execute` is not a workaround for durable clients: the ~30s gateway ceiling rules it out
for img-gen and parallel-heavy pipes — exactly the runs whose cost matters most.

## Proposed change (smallest that closes it)

1. **pipelex** `delivery_executor.generate_result_files`: also write `tokens_usages.json` —
   `{"tokens_usages": [...], "usage_assembly_error": null}`, same serialization the `/execute`
   response already uses.
2. **pipelex-platform** `runs.py`: fetch the fourth file in `_fetch_run_result_artifacts()`
   (tolerating its absence for runs delivered before the change) and add
   `tokens_usages` / `usage_assembly_error` to `RunResultsResponse`.

No SDK release needed to unblock: `pipelex-sdk` 0.4.0's `RunResults` is `extra="allow"`, so the
new fields ride along via `model_extra`; typing them in the SDK can follow.

## Notes

- Keep it raw records, not a computed $ total — consumers (e.g. `fenix-pipelex`) do the
  multiply-and-sum deterministically, and the existing `CostRegistry.build_cost_summary` shape is
  available if a summary is wanted later.
- Known caveat carried over from the engine: models with no `costs` in their backend TOML price
  at 0 — consumers should flag zero-cost records rather than trust them.
