# Capability: usage reporting independent of cost

**Status: IDEA, LOW PRIORITY.** Not decided, not scheduled. Captured because it is interesting in its own right; revisit when a concrete signal appears (a user wanting token counts without dollars, or a model/backend with no cost data).

## The capability gap

Today usage-emission and cost-rendering are **bundled under one switch**. The `--costs` flag (→ internal gate `is_generate_usage`, renamed from `is_generate_costs` in #968) turns on usage-event emission *and* the cost report is the only deliverable. There is **no mode that gives you token counts without dollar figures.**

But usage (token counts) is valuable on its own, not just as an input to a cost number:

- **Consumption monitoring / profiling** — how many tokens a run burns, where, regardless of price. Useful for prompt-size regressions and context-budget work even when you don't care about (or can't price) the spend.
- **Models / backends without cost data.** A handle with no per-token unit cost configured produces a meaningless or zero cost report, but its token counts are still real and worth surfacing.
- **Budget-agnostic dashboards.** Token usage is a stable signal; prices drift. Reporting usage separately lets a downstream consumer apply its own pricing.

The data is already there — `UsageReportEvent` carries `TokensUsage` (`nb_tokens_by_category`); cost is computed *from* it by `CostRegistry`. So "usage without cost" is dropping a derivation step, not capturing new data.

## Why this is the deeper question behind the naming cleanup

The companion rename merged in #968 (`is_generate_costs → is_generate_usage`, `GraphContext → TraceContext`) handled *consistency* — it aligned the internal gate name to the usage stream it feeds, and deliberately left the public `--costs` flag and the cost domain alone. It did **not** add any capability.

This doc is the *capability* question: should usage be a first-class, separately-requestable output, with cost as one **view** layered on top? If yes, the public `--costs`-vs-`--usage` naming falls out of it naturally (usage = the measured data, cost = a priced projection). If no, keeping "cost" as the single user-facing word is correct and the naming work stops at the internal gate. **Decide the capability first; the public naming is downstream of it.**

## Rough shape if pursued (not designed)

- Split the single gate into two intents: *emit usage* and *render cost*. Cost-render becomes gated on usage-present (it already is, post-companion-rename) plus a separate "show costs" choice.
- Surface a **usage-only report**: token counts by category / by model, no dollar columns — a sibling renderer (or a mode of `cost_report_renderer.py`) that omits the priced columns.
- Public surface: likely a `--usage` / `--costs` pair (or `--report usage|cost|both`), where `--costs` implies usage. Exact ergonomics TBD.

## Related, already-captured

- **Cost-per-node breakdown** ([`deferred-followups.md`](deferred-followups.md), "Cost-per-node correlation") — also a *view* over the same `UsageReportEvent` stream (aggregate by `node_id` instead of by model). A usage-only-per-node report is the intersection of that item and this one; if both get built, they share the same "projection over the usage event stream" machinery.
