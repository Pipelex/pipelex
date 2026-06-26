# Handoff — one-arg `render_cost_report_for_output(pipe_output)` submitter helper

**Status: ✅ Shipped** (`feature/Cost-report-helper`). `render_cost_report_for_output` is in `pipelex/reporting/cost_report_renderer.py`, the `pipelex run` CLI (`_run_core.py`) uses it, `render_run_cost_report` is unchanged as the primitive, unit tests pin the gate-from-output derivation (`tests/unit/pipelex/reporting/test_render_cost_report_for_output.py`), and the as-built overview + `docs/features/cost-tracking.md` document the surface. Downstream cocode collapse is still pending (re-pin `pipelex`, then delete cocode's local `_render_cost_report` gate). The rationale below is kept because it composes with the still-open decisions #3/#6 in `cost-report-deferred-decisions.md`.

**Task:** add a thin, self-contained cost-report rendering helper to `pipelex/reporting/cost_report_renderer.py` that takes only a finished `PipeOutput`, so every "submitter" (the `pipelex run` CLI, and external embedders like cocode) stops re-deriving the same three arguments — and stops re-reading global config to reconstruct a decision the run already recorded on the output.

This is the **submitter-ergonomics facet** of the same theme as the deferred decisions in this registry (`cost-report-deferred-decisions.md` #3/#6, and its cross-cutting note: "there is no single owner of *is cost reporting on for this run?*"). It does not resolve #3 or #6 — it is a smaller, additive convenience that should land on its own, and it composes cleanly with whatever those decisions settle.

## Where this came from

Bumping the `pipelex` dependency in the sibling `../cocode/` repo broke its build: the new `ReportingProtocol` (post the event-sourced cost-report rework, PR #967) no longer has `generate_report()`. cocode migrated its call sites to `render_run_cost_report(...)`, and to do so it had to write this glue (`../cocode/cocode/swe/swe_cmd.py`, `_render_cost_report`):

```python
render_run_cost_report(
    pipeline_run_id=pipe_output.pipeline_run_id,
    tokens_usages=pipe_output.tokens_usages,
    is_generate_costs=get_config().pipelex.pipeline_execution_config.is_generate_usage,
)
```

Two smells fall out of that:

1. **Duplication.** All three arguments are derivable from a finished run. The `pipelex run` CLI writes the same unpacking by hand (`pipelex/cli/commands/run/_run_core.py:320`). Every embedder that wants the standard cost report has to reproduce it.
2. **Wrong source of truth for the gate.** cocode re-reads global config (`is_generate_usage`) to reconstruct whether costs were on — but the runner already made that decision at run time, with all `--costs/--no-costs` override resolution applied, and **recorded it on the output**: `PipeOutput.tokens_usages` is `None` precisely when cost reporting was off. See the field docstring at `pipelex/core/pipes/pipe_output.py:28-32`:

   > the submitter renders the cost report from this field. None when cost reporting was off or the run emitted no trace events at all; an empty list when on with events present but no inference happened.

   Reading config afterwards re-derives a fact the output already carries — correct only when config wasn't overridden and wasn't mutated between run and render. The output is authoritative; config is not.

## Proposed change

Add a free function next to `render_run_cost_report` (do **not** add a method on `PipeOutput` — that would couple the core model to the renderer's deps: config, `CostRegistry`, Rich; reporting may depend on core, not the reverse):

```python
def render_cost_report_for_output(pipe_output: PipeOutput) -> None:
    """Render the end-of-run cost report from a finished output (self-contained).

    The gate is read off the output, not config: pipe_output.tokens_usages is None
    exactly when cost reporting was off for this run (see PipeOutput.tokens_usages).
    """
    render_run_cost_report(
        pipeline_run_id=pipe_output.pipeline_run_id,
        tokens_usages=pipe_output.tokens_usages,
        is_generate_costs=pipe_output.tokens_usages is not None,
    )
```

Keep `render_run_cost_report(*, pipeline_run_id, tokens_usages, is_generate_costs)` exactly as-is — it stays the **low-level primitive** for the cases where the three values genuinely come from different places: the agent CLI's machine-readable envelope path (`build_cost_summary`, `pipelex/cli/agent_cli/commands/run/_run_core.py`) and any distributed/Temporal reassembly where the output isn't the single carrier.

Then collapse the `pipelex run` call site (`_run_core.py:320`) to `render_cost_report_for_output(pipe_output)`.

## Why deriving the gate from the output is behaviorally identical to the current CLI gate

`render_run_cost_report` already ANDs both guards (`if not is_generate_costs or not tokens_usages: return`, `cost_report_renderer.py:50`), so for every run produced by the standard runner the *rendered outcome* is unchanged when the gate is read from `tokens_usages` instead of from `execution_config.is_generate_usage`:

- usage on, inference happened → `tokens_usages` non-empty → render (both agree).
- usage on, dry run (no inference) → `tokens_usages == []` → `is not None` True, then `has_reportable_usage` suppresses (both agree).
- usage on but tracing disabled (decision **#3**) → `tokens_usages is None` → no render. The current CLI gate is `True` here but the renderer no-ops on `not tokens_usages` anyway → same outcome. **The helper inherits #3, it does not worsen it.**
- usage off → `tokens_usages is None` → no render (both agree).

So this is a pure de-duplication + correct-source-of-truth change, not a behavior change.

## Scope / non-goals

- **Do not** fold in decisions #3 (cost reporting coupled to `tracing_config.is_enabled`) or #6 (agent-CLI vs main-CLI gate divergence). Those are separate deliberate calls tracked in `cost-report-deferred-decisions.md`. This helper is render-surface only (console/CSV) and is orthogonal to the agent CLI's `build_cost_summary` JSON path.
- **Do not** change the signature of `render_run_cost_report`.
- **Do not** add a `PipeOutput` method (layering — see above).
- This is complementary to the cross-cutting note's "one resolved predicate on `PipelineExecutionConfig`": even after that lands, the *render-time* consumer should read the resolved decision off the output, which already records it.

## Read first

- `cost-reporting-overview.html` — as-built architecture (start here for the event-sourced model).
- `cost-report-deferred-decisions.md` — #3 and #6, the adjacent gate-source decisions; this handoff is the third, smaller facet.
- `deferred-followups.md` — T3 request-scoped tracing state (the broader "single owner" refactor this rolls toward).

## Acceptance criteria

- `render_cost_report_for_output(pipe_output)` added to `pipelex/reporting/cost_report_renderer.py`; `render_run_cost_report` unchanged.
- `pipelex run` (`_run_core.py`) uses the new helper; no behavior change to its console/CSV output (verify with a real run under `--costs`, `--no-costs`, `--dry-run`, and a free/zero-price model).
- No new import cycle (`reporting` → `core.pipe_output` is fine; `core.pipe_output` must not import the renderer).
- Docs updated in `pipelex/docs/` where the cost-report rendering surface is described.
- `make check` / `make test` green.

## Downstream (sibling repo, not part of this change)

Once shipped and pipelex is re-pinned in `../cocode/`, cocode's `_render_cost_report` collapses to a one-line delegate to `render_cost_report_for_output(...)` and then deletes — its current config-reading gate goes away. No action needed in pipelex; noting it so the API shape stays embedder-friendly (the one-arg form is the whole point).
