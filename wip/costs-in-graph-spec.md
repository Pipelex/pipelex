# Per-node cost and token usage in the GraphSpec

Status: **implemented and verified, all six phases.** Not yet shipped: nothing reaches users until `@pipelex/mthds-ui` is published and `make refresh-graph-ui-sri` bumps the pinned bundle.

Revision 2 — absorbs the Codex outside-voice pass. See "Outside voice absorbed" at the end for what changed and why.

## Implementation status

| Phase | State |
|---|---|
| 1 — pipelex model + assembler | done (T1-T5, T7) |
| 2 — pipelex tests | done (T6 + `test_usage_attribution.py`, `test_assembler_usage_attribution.py`, roundtrip tests) |
| 3 — pipelex docs + changelog | done (T8, new `docs/under-the-hood/per-node-usage-attribution.md`) |
| 4 — DRY fixtures with `--mock-usage` | done (T10, T11 — full corpus regenerated, all green) |
| 5 — mthds-ui | done (T9, T12 + `usageFormat.ts`, `UsageSection.tsx`, `docs/usage-attribution.md`) |
| 6 — LIVE regeneration | done — all 32 pipelines, $2.85, zero failures |

**CHECKPOINT 1 findings.** The rollup is correct on the deepest fixture: `pipeline_24` (DEEP_NESTING, 12 nodes, containment depth 3) matches an independent recomputation from the CONTAINS edges on every node, and its root subtree equals `graph.usage.total`. Nothing in the corpus is deep or wide enough to *measure* the memoization — the walk is memoized and uses an explicit stack, so the O(n) claim and the recursion-limit independence are structural, not benchmarked. `GraphSpec.usage.unattributed.inference_calls` is **0 on every one of the 32 DRY fixtures** — nothing escapes attribution on a local in-process run.

**CHECKPOINT 2.** pipelex is shippable as-is: Phases 1-3 are self-contained and the API, the MCP and `vscode-pipelex` get per-node usage whether or not a card renders it.

**CHECKPOINT 3.** Reached and reviewed in Storybook against the real LIVE corpus. The treatment changed substantially from the plan under review — see "What review changed" below. Remaining: commit both repos, publish `@pipelex/mthds-ui`, and `make refresh-graph-ui-sri` to bump the pinned bundle. Until that publish, the standalone `reactflow.html` pipelex emits still loads the old bundle and shows no cost.

### What review changed (post-implementation)

The plan's UI design did not survive contact with the screen. Four reversals, all in the same direction — showing less, and only what was actually measured:

1. **No cost on the cards at all.** The plan put a chip in the card's annotation row. Removed entirely — the card is for structure; a price on every node turns the graph into a spreadsheet. Cost lives only in the side panel.
2. **Cost sits on the status line**, formatted exactly like the duration beside it (`● Succeeded  8.37s  $0.0268 ⌄`), not as a labelled block. They are three facts of the same kind about one run.
3. **No token counts anywhere.** The decisive finding: extract, search and image generation are billed per request, and pipelex encodes that price by putting exactly `1_000_000` in each token category (rates are per-million, so the arithmetic reproduces the per-request price — `linkup_extract_worker.py:89`, `linkup_search_worker.py:92`, `gateway_extract_worker.py:182`). A one-page extract reports 2,000,000 "tokens". Worse, a controller's `subtree_total_tokens` sums those sentinels with real LLM tokens, so **no token figure is trustworthy at any level of a graph**. Cost is the only number that survives the encoding.
4. **`--mock-usage` reverted out of the DRY fixtures.** It makes a dry run report invented token counts; a dry run executes nothing, so those were fabrications rendered as measurements. DRY specs now carry zero tokens and a null cost, which is the truth, and the cost surface is gated on a real run.

### New defect found, not fixed (out of scope)

The `1_000_000` sentinel is not confined to the graph. It rides the `/execute` API's `tokens_usages` records and the CLI cost table's token columns, and `AggregatedCosts.total_nb_tokens` sums it — so any client computing token usage from the API gets nonsense as soon as a method touches extract or search. The fix is a `billing_unit` discriminator on the usage record so per-request prices stop masquerading as token counts. That is an API-contract change and needs its own plan.

### Where the plan was refined during implementation

1. **Invariant 1 is weaker than stated, and the docstring now says so honestly.** The plan wrote `usage is None <=> collection was OFF`. The event stream carries no "collection is on" signal, so a run with collection on that makes *zero* inference calls is indistinguishable from collection off. The shipped invariant is: `usage is None` ⟺ **no usage was reported anywhere in the run** (off, or zero calls) — and it stays all-or-nothing across a graph, which is the property consumers actually branch on. Both states render as nothing, so nothing downstream cares.
2. **Attribution resolves in pass 2, not in the handler.** A `UsageReportEvent` can be read *before* the `PipeStartEvent` of the node it names (different workers, stream ordered by `(workflow_id, sequence)`), so "is this node real?" is only answerable once every event is in. `_handle_usage_report` folds by raw `node_id`; `_attribute_usage` resolves. This also gets a test.
3. **`UNATTRIBUTED_NODE_ID` is now a named constant** in `trace_events.py`, replacing the bare `"unknown"` literal duplicated at `reporting_manager.py:219` and `:293`.
4. **The Phase 4 fixture gate is split by freshness.** `assertValid` holds only *freshly generated* specs to the usage gate; specs reused from disk are exempt. Otherwise a partial `--only` LIVE run against the existing (pre-usage) LIVE corpus would die on every reused spec.
5. **The DRY token gate is conditional.** "at least one node has `total_tokens > 0`" fires only when the run made any inference call, so an inference-free pipeline does not fail the gate. Note only `PipeLLM` reports mock usage — `PipeExtract` / `PipeSearch` / `PipeImgGen` nodes show zero calls in DRY.
6. **Fixture regeneration turned out not to be bit-stable, for reasons unrelated to usage.** `pipeline_11`'s `PipeCondition` branches on mock-generated text, so a dry run routes to either branch; `snapshots.test.ts` already documents per-regeneration fingerprint drift and prescribes `vitest -u`. Regenerating the *whole* corpus at once produced a coherent, fully green tree (1835 tests). Regenerating a subset can leave the corpus internally inconsistent.

## The problem in one paragraph

Pipelex already records what every inference call cost, and already records the shape of the run as a graph. Both are built from **one** trace-event stream, and every usage event already carries the graph node it belongs to. At assembly the link is thrown away: `GraphSpecAssembler` skips `UsageReportEvent` entirely, and `UsageAggregator` returns a flat list with `node_id` stripped. So `PipeOutput.graph_spec` and `PipeOutput.tokens_usages` are two disjoint artifacts describing the same run, and no consumer can answer "which pipe spent the money".

```
  inference call completes
          │
          ▼
  ReportingManager._emit_usage_event                 trace_context.parent_node_id
  reporting_manager.py:161                                      │
          │                                                     │
          ▼                                                     │
  UsageReportEvent{ node_id ◄──────────────────────────────────┘ , tokens_usage }
  trace_events.py:182                    the link ALREADY EXISTS here
          │
          ▼
  ┌──────────────── event log — ONE stream, one read ────────────────┐
  │  PipeStartEvent   PipeEndSuccessEvent   EdgeEvent   UsageReport  │
  └───────────────────────────────┬──────────────────────────────────┘
                                  │  tracing_assembly.py:101-136
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
       GraphSpecAssembler                   UsageAggregator
       :197  elif UsageReportEvent:         :22  [e.tokens_usage for e in ...]
             pass  ◄── LINK DROPPED               ◄── node_id DROPPED
                  │                               │
                  ▼                               ▼
        PipeOutput.graph_spec           PipeOutput.tokens_usages
        (nodes, edges, no cost)         (costs, no graph position)
```

The fix is to stop dropping it, model the result unambiguously, and render it.

## What already exists

Reuse these; do not rebuild them.

| Thing | Where | How this plan uses it |
|---|---|---|
| `UsageReportEvent.node_id` | `tracing/trace_events.py:182-187` | The correlation key. Already emitted on both paths (`reporting_manager.py:219`, `:293`). |
| `compute_tokens_usage_cost()` | `cogt/usage/cost_registry.py:27` | The single canonical per-call USD total, and the authority on rated-vs-unrated (returns `None` iff `unit_costs` is empty). **Call it; never re-derive cost math.** |
| `AggregatedCosts.total_nb_tokens` | `cogt/usage/cost_registry.py:~70` | Defines the canonical token total as input-joined + output. Our `total_tokens` uses the same definition so the graph and the cost report cannot disagree. |
| `TokenCategory` / `nb_tokens_by_category` | `cogt/usage/token_category.py`, `reporting/usage_records.py:49` | The already-shipped token vocabulary. Reused verbatim — no new token names. |
| `TokensUsageRecord.cost: float \| None` | `reporting/usage_records.py:51` | The already-shipped encoding of "unrated". Mirrored, not reinvented. |
| Node parentage | `_AssemblerNodeData.parent_node_id` (`graphspec_assembler.py:69`) | Subtree rollup walks this; no need to re-derive from `CONTAINS` edges. |
| `mthds-ui` GraphSpec plumbing | `types.ts`, `validateGraphSpec.ts`, `pipeCardPayload.ts`, `PipeCardBase.tsx` | The payload pipeline already exists; we add one field through all four. |
| `generate-fixtures.mjs` | `mthds-ui/scripts/` | Already shells out to `../pipelex/.venv/bin/pipelex`. A local Python change is picked up with **zero wiring**. |
| `is_generate_usage = true` | `pipelex/pipelex.toml:307`, not overridden in `mthds-ui/.pipelex/pipelex.toml` | Usage events are **already** emitted on every fixture run. No CLI flag change needed. |
| `--mock-usage` | `_run_core.py:55-76`, `dry_mock.py:150+` | Hidden dry-run sub-flag producing non-zero synthetic tokens. Used in Phase 4 to get a meaningful free token chip. |

## Decisions taken

Decided on best-practice / most-future-proof grounds rather than asked.

### D1 — A typed `NodeSpec.usage` with no overloaded nulls

`NodeSpec.metrics: dict[str, float]` exists and is already rendered by `PipeDetailPanel.tsx:190`, which makes it the tempting zero-schema-change home. **Rejected.** `dict[str, float]` cannot express *unrated*: `compute_tokens_usage_cost` returns `None` whenever the model carries no rate table, and `dry_mock.py:133` hardcodes `unit_costs={}` for every synthetic dry-run call — so **every one of the 32 committed DRY fixtures is unrated**. In a float dict the only encoding for "unrated" is to omit the key, indistinguishable from "never collected".

The first draft of this plan then made the same mistake one level up, by letting a single `cost: None` mean four different things. It does not now. Three states, three orthogonal encodings, stated as invariants:

```python
# pipelex/graph/graphspec.py


class NodeUsageSpec(BaseModel):
    """Inference usage attributed to one graph node.

    Field names mirror the already-shipped client-facing ``TokensUsageRecord``
    (reporting/usage_records.py) so the graph does not introduce a fifth
    vocabulary for numbers this codebase already names four ways
    (TokenCategory, LLMTokenCostReportField, GenAISpanAttr, PostHogAttr).

    INVARIANTS — the UI and every other consumer branch on these, not on
    guesses about why a number is missing:

      1. ``NodeSpec.usage is None``  <=>  usage collection was OFF for the run.
         When it was ON, EVERY node carries a spec, zeroed if it ran no
         inference. A controller, a lifted pipe, and a PipeFunc all get
         ``inference_calls=0``, never ``usage=None``.

      2. ``cost is None``  <=>  ``rated_inference_calls == 0``.
         Nothing else. "Made no call" and "made only unrated calls" both land
         here and are told apart by ``inference_calls``.

      3. ``inference_calls > rated_inference_calls > 0``  =>  ``cost`` is a
         LOWER BOUND, not a total. The UI must mark it (a leading "≥").

      4. ``total_tokens`` is input_joined + output — the same definition as
         ``AggregatedCosts.total_nb_tokens``. It is NOT the sum of
         ``nb_tokens_by_category``: ``input_cached`` is a SUBSET of ``input``,
         not additive (usage_records.py:47-48), so summing double-counts.
         Never sum the dict; read this field.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    # This node's own inference.
    inference_calls: int = 0
    rated_inference_calls: int = 0
    nb_tokens_by_category: dict[str, int] = Field(default_factory=dict)
    total_tokens: int = 0
    cost: float | None = None

    # This node plus every descendant.
    subtree_inference_calls: int = 0
    subtree_rated_inference_calls: int = 0
    subtree_nb_tokens_by_category: dict[str, int] = Field(default_factory=dict)
    subtree_total_tokens: int = 0
    subtree_cost: float | None = None
```

`NodeSpec` gains `usage: NodeUsageSpec | None = None`. `metrics` is left exactly as it is — still free-form, still unused — so nothing that reads it today changes.

**Why not OTel semconv keys** (`gen_ai.usage.input_tokens`, already imported at `otel_constants.py:50`): semconv names *span attributes*, a different layer with different consumers (Langfuse, PostHog), and pipelex already uses it correctly there (`llm_worker_abstract.py:256`). Borrowing that dotted namespace into a graph contract read by UIs buys nothing and, with `PipeDetailPanel.tsx:195` rendering `label={key}`, would leak `gen_ai.usage.input_tokens` onto the screen. A typed model has field names, not attribute keys, so the question dissolves.

### D2 — Own and subtree, for tokens as well as cost

A controller (`PipeSequence`, `PipeBatch`, `PipeParallel`) runs no inference, so its own numbers are always zero. Shipping only own values makes every controller card read empty, which reads as a bug.

Subtree tokens matter as much as subtree cost, and more in practice: the default Storybook view is the DRY corpus, which is unrated, so **tokens are the only number a controller can show there**. Both rollups ship.

Rollup is computed **in the assembler**, not the UI, for the same reason `AggregatedCosts` computes its totals once: three consumers (`pipelex-app`, `vscode-pipelex`, MCP) must not each re-derive it and disagree.

```
  seq_node       calls 0 (0 rated)   subtree 3 calls (2 rated)  subtree_cost 0.0071  subtree_tokens 4210
    ├── llm_a    calls 1 (1 rated)   cost 0.0043   tokens 2130
    ├── llm_b    calls 1 (1 rated)   cost 0.0028   tokens 2080
    └── func_c   calls 0 (0 rated)   cost None     tokens 0      ← ran, made no inference
```

`func_c` has `usage` present with `cost=None` and `inference_calls=0` — invariant 1 and 2 together say "collected, ran nothing", never "unknown".

### D3 — A typed `GraphSpec.usage`, not a `meta` bag

Both emit paths fall back to `node_id = trace_context.parent_node_id or "unknown"` (`reporting_manager.py:219`, `:293`). Usage landing on `"unknown"` has no node to attach to, and dropping it would make the graph's total silently disagree with the cost report.

The first draft put the run total and the unattributed bucket in `GraphSpec.meta`. That was inconsistent — arguing for typing at the node level and then reaching for an untyped bag at the graph level. `meta` is `[key: string]: unknown` in `mthds-ui`, so anything put there arrives untyped at every consumer.

```python
class GraphUsageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    total: NodeUsageSpec  # whole-run rollup
    unattributed: NodeUsageSpec  # usage whose node_id was "unknown"
```

`GraphSpec` gains `usage: GraphUsageSpec | None = None`, `None` under the same invariant 1 as the node field. Reusing `NodeUsageSpec` for both keeps exactly one usage shape in the contract.

### D4 — Assert the builder divergence; do not normalize it away

There are two GraphSpec builders. `GraphSpecAssembler` produces every consumed spec. The in-process `GraphTracer`'s `teardown()` output is **discarded at every call site** — `runner.py:281`, `pipe_run.py:60`, and `dry_run_in_process.py:151` (which then reads `pipe_output.graph_spec`, i.e. the assembler's). `GraphTracerProtocol` has no method to receive usage at all; adding one, plus its no-op implementations, would be plumbing into output nobody reads.

But `test_assembler_equivalence.py:57` puts `"metrics": node.metrics` in its structural comparison, and **none of its six scenarios emit a usage event**. Left alone, the two builders diverge and CI stays green — a rotting test, worse than an absent one.

Add `_scenario_with_usage`, and rather than deleting `usage` from `_normalize_node` (which would weaken the test permanently), **assert the divergence explicitly**: the assembled spec has `usage` populated, the tracer spec has `usage is None`, and that asymmetry is the assertion. If someone later plumbs usage into the tracer, the test fails and tells them to delete the assertion — which is what a test documenting an intentional gap should do.

### D5 — Free runs prove the unrated path; only paid runs show a dollar

`_report_synthetic_llm_job` sets `unit_costs={}` unconditionally (`dry_mock.py:133`), shared by both `report_dry_llm_job` and `report_mock_usage_llm_job`. The hidden `--mock-usage` flag buys non-zero *tokens* and never a non-zero *cost*.

So the free loop is worth more than the first draft credited, provided it uses `--mock-usage`. Plain `--dry-run` emits zero-token usage, which exercises `inference_calls` and nothing else. With `--mock-usage` the DRY corpus produces a genuinely non-zero **unrated** graph — the exact default Storybook state — and the token chip becomes reviewable for free. Only the dollar itself needs Phase 6 and real money.

### D6 — One attribution module, not logic buried in `_AssemblerState`

Codex's strongest structural point: the plan risks a second aggregation model with subtly different semantics from `CostRegistry`. Mitigated by extracting accumulation and rollup into `pipelex/tracing/usage_attribution.py` — independently testable, one place where the invariants live, and reusable if the tracer ever needs it. `_AssemblerState` calls into it and holds no usage arithmetic of its own.

Not accepted: Codex's fuller version, preserving `node_id` on the records `UsageAggregator` returns. That would change `PipeOutput.tokens_usages`, whose trimmed wire shape (`TokensUsageRecord`, `extra="forbid"`) is a shipped client contract. Two projections of one stream is the design `tracing_assembly.py` already documents; the DRY fix belongs in the shared helper, not in merging the projections.

---

## Phases

### Phase 1 — pipelex: model and assemble

Files: `pipelex/graph/graphspec.py`, new `pipelex/tracing/usage_attribution.py`, `pipelex/tracing/graphspec_assembler.py`.

1. Add `NodeUsageSpec`, `GraphUsageSpec`, `NodeSpec.usage`, `GraphSpec.usage` (D1, D3).
2. New `usage_attribution.py` (D6): a `UsageAccumulator` that folds one `AnyTokensUsage`, tracking `inference_calls`, `rated_inference_calls`, merged `nb_tokens_by_category`, canonical `total_tokens`, and summed cost via `compute_tokens_usage_cost`. Plus `roll_up(nodes)` producing the subtree fields.
3. Replace `graphspec_assembler.py:197-198`:
   ```python
   elif isinstance(event, UsageReportEvent):
       self._handle_usage_report(event)
   ```
4. Attach a spec to **every** node when any usage event was seen, zeroed where nothing ran (invariant 1). Emit `GraphSpec.usage` with the run total and the `"unknown"` bucket.
5. Rollup in `pass_two()`: memoized post-order walk of `parent_node_id`. Memoize (O(n), not O(n·depth)), guard cycles with a visited set, and treat a dangling `parent_node_id` as a root rather than a `KeyError`.
6. Update the class docstring at `graphspec_assembler.py:112-119` — it enumerates pass 1 and pass 2 and goes stale the moment step 3 lands.

All new functions keyword-only per `docs/contribute/keyword-only-arguments.md`. Run `make agent-check`.

> **CHECKPOINT 1.** `pipe_output.graph_spec` now carries per-node usage, and the API, the MCP, and `vscode-pipelex` get it whether or not a card renders it. The independently valuable half — worth landing alone if the UI work stalls. Record here: whether rollup memoization held on the deepest fixture, and whether `GraphSpec.usage.unattributed` was non-zero on any real run (it should not be).

### Phase 2 — pipelex: tests

Files: new `tests/unit/pipelex/tracing/test_usage_attribution.py`, `test_graphspec_assembler.py`, `test_assembler_equivalence.py`, `tests/unit/pipelex/graph/test_graphspec_roundtrip.py`.

Full coverage per the diagram below, including the D4 equivalence assertion. Every invariant in the `NodeUsageSpec` docstring gets a named test — they are the contract.

### Phase 3 — pipelex: docs and changelog

- New page under `docs/under-the-hood/` on the two projections of one event stream and the three usage states. Sibling to `tokens-usage-wire-records.md`.
- Update `docs/features/cost-tracking.md` for per-node attribution.
- `CHANGELOG.md` under `## [Unreleased]`: breaking — `GraphSpec` nodes gained `usage`, and `NodeSpec` is `extra="forbid"`, so an older pipelex rejects the new JSON. Per workspace policy there is no transition window; the note is the deliverable.

> **CHECKPOINT 2.** pipelex is shippable here. Everything after crosses into `mthds-ui` and eventually needs an npm publish + SRI bump to reach users. Decide whether to land Phase 1-3 as its own PR.

### Phase 4 — regenerate DRY fixtures with `--mock-usage` (free)

`generate-fixtures.mjs:124-131` passes `--dry-run --mock-inputs`. Add `--mock-usage` to that DRY arg list (D5) so the corpus carries non-zero unrated tokens instead of zeros.

```bash
cd ../mthds-ui && make fixtures
```

Picks up the local `.venv` pipelex automatically (`generate-fixtures.mjs:48-50`).

**Gate — stated correctly this time.** Not "every node has `inference_calls >= 1`"; controllers, `PipeFunc`, skipped and lifted pipes legitimately have zero. The gate is:

- every node has `usage != null` (invariant 1),
- `cost == null` on every node (invariant 2 — DRY is always unrated),
- at least one LLM-bearing node has `total_tokens > 0` (proves `--mock-usage` took effect),
- every controller has `subtree_total_tokens >= ` the max of its children's,
- `graph.usage.unattributed.inference_calls == 0`.

`assertValid` (`generate-fixtures.mjs:163-177`) checks format/mode/nodes/description/domain_code only and will pass an all-null regeneration. Extend it — that is task T10, not an optional grep.

### Phase 5 — mthds-ui: validator, type, payload, card

Files: `src/graph/types.ts`, `src/graph/validateGraphSpec.ts`, `src/graph/pipeCardPayload.ts`, `src/graph/react/nodes/pipe/pipeCardTypes.ts`, `PipeCardBase.tsx`, `graph-core.css`, `react/detail/PipeDetailPanel.tsx`.

1. `types.ts` — `usage?: NodeUsage` on the node type, `usage?: GraphUsage` on the spec, mirroring the Python models.
2. `validateGraphSpec.ts` — **the boundary gate**. Types alone are a compile-time fiction; malformed `usage` from a stale or hostile spec otherwise flows through as trusted data. Validate shape and the `cost === null || typeof cost === "number"` invariant.
3. `pipeCardPayload.ts:22-23` — one line, mirroring the existing `tags` passthrough:
   ```ts
   if (node.usage !== undefined) payload.usage = node.usage;
   ```
4. `PipeCardBase.tsx` — a usage chip in the existing `pipe-card-annotations` row (`:~130`), already the established pattern for `outcome` / `batch_multiplicity`. Four render states, visually distinct:

   | State | Condition | Card shows |
   |---|---|---|
   | not collected | `usage === undefined` | nothing |
   | ran nothing | `inference_calls === 0 && subtree_inference_calls === 0` | nothing |
   | unrated | `cost === null` with calls > 0 | token count, no `$` |
   | partial | `inference_calls > rated_inference_calls > 0` | `≥ $0.0043` |
   | rated | `rated === inference_calls > 0` | `$0.0043` |

   Controllers read the `subtree_*` fields; operators read own (D2).
5. `PipeDetailPanel.tsx` — a Usage section beside the existing Metrics section, with the per-category breakdown and both own and subtree columns.

### Phase 6 — LIVE regeneration, real money

```bash
cd ../mthds-ui && make fixtures-live ONLY=pipeline_01,pipeline_09
```

Two or three pipelines, never the corpus. The script's own header (`:20-23`) warns a full sweep has no skip path and leaves a half-swept mixed-version tree on any failure; see `mthds-ui/wip/fixtures-live-corpus-regeneration.md`. `--only` reuses every other pipeline's on-disk spec so the emitted fixtures stay complete.

**Cross-check semantics, stated so the check is meaningful.** `CostRegistry.aggregate_costs` treats an unrated usage as zero-cost; `NodeUsageSpec.cost` is `None`. Comparing them naively produces a false disagreement. The check is: `graph.usage.total.cost` must equal the CSV total **when `total.rated_inference_calls == total.inference_calls`**. When they differ, the graph total is a lower bound and the CSV is the wrong comparand — compare `rated_inference_calls` against the CSV row count instead.

**Do not commit the LIVE regeneration** unless you intend to. Every regenerated live spec is real inference against whatever models are current; the diff churns far beyond the `usage` field.

> **CHECKPOINT 3.** You have looked at it. Decide whether the card treatment is right before the npm publish + `make refresh-graph-ui-sri` bump that makes it reach users.

---

## Test coverage

```
CODE PATHS                                                  USER FLOWS
[+] tracing/usage_attribution.py  (new)                     [+] Storybook, DRY corpus (default view)
  ├── UsageAccumulator.fold()                                 ├── [GAP] Unrated card: token count,
  │   ├── [GAP] first usage for a node                        │         no "$", not "$0.00"
  │   ├── [GAP] second usage, same node (accumulate)          ├── [GAP] Controller shows subtree
  │   ├── [GAP] INVARIANT 2: unrated -> cost stays None       │         tokens, not blank
  │   ├── [GAP] INVARIANT 3: mixed rated/unrated -> cost      ├── [GAP] Zero-call node (PipeFunc,
  │   │         is a lower bound, rated < calls               │         lifted) shows nothing, and
  │   └── [GAP] INVARIANT 4: total_tokens is joined+output,   │         is distinguishable from
  │             NOT sum(nb_tokens_by_category)                │         "not collected"
  └── roll_up()                                               └── [GAP] Detail panel Usage section,
      ├── [GAP] leaf: subtree == own                                    own + subtree columns
      ├── [GAP] controller: sum of children
      ├── [GAP] nested 3 deep, memoization correct           [+] Storybook, LIVE fixtures
      ├── [GAP] all-unrated subtree -> subtree_cost None       ├── [GAP] Real dollars on a card
      ├── [GAP] CRITICAL cycle in parent chain -> guard        ├── [GAP] Partial "≥ $" state
      └── [GAP] CRITICAL dangling parent -> treated as root    └── [GAP] Sequence subtree_cost ==
                                                                        sum of children's cost
[+] tracing/graphspec_assembler.py
  ├── _handle_usage_report()                                 [+] Contract consumers
  │   ├── [GAP] node_id="unknown" -> graph.usage.unattributed  ├── [GAP] [→E2E] graphspec.json
  │   └── [GAP] node_id for a node that never started          │      round-trips through
  └── build_graph_spec()                                       │      validateGraphSpec
      ├── [GAP] INVARIANT 1: usage=None on ALL nodes when      └── [GAP] vscode-pipelex adapter
      │         no usage event was seen                               renders a usage-bearing spec
      ├── [GAP] INVARIANT 1: EVERY node gets a spec when
      │         any usage event was seen (controllers,
      │         PipeFunc, skipped, lifted all zeroed)
      └── [GAP] graph.usage.total == sum over nodes' own

[+] graph/graphspec.py
  ├── [GAP] NodeUsageSpec JSON round-trip preserves cost=None
  ├── [GAP] extra="forbid" rejects an unknown usage field
  └── [★★ TESTED] NodeSpec round-trip — test_graphspec_roundtrip.py
      └── [GAP] REGRESSION: round-trip with usage populated

[+] tests/.../test_assembler_equivalence.py
  └── [GAP] CRITICAL: _normalize_node compares "metrics" (:57) but no
            scenario emits usage. Add _scenario_with_usage AND assert the
            divergence explicitly (assembler has usage, tracer has None) —
            do NOT normalize usage away (D4).

[+] mthds-ui
  ├── validateGraphSpec.ts
  │   ├── [GAP] accepts a well-formed usage object
  │   ├── [GAP] rejects cost of the wrong type
  │   └── [GAP] accepts a spec with no usage at all
  ├── pipeCardPayload.ts
  │   ├── [GAP] usage passed through when present
  │   └── [GAP] usage absent -> key omitted (mirrors tags at :23)
  └── PipeCardBase.tsx
      ├── [GAP] all five render states distinct
      └── [GAP] controller reads subtree_*, operator reads own

COVERAGE: 1/35 paths tested (3%)  |  Code: 1/22 (5%)  |  Flows: 0/13 (0%)
QUALITY:  ★★:1  |  GAPS: 34 (1 E2E, 0 eval, 3 CRITICAL)
```

Legend: ★★★ behavior + edge + error | ★★ happy path | ★ smoke | [→E2E] integration

## Failure modes

| Codepath | Realistic production failure | Test? | Error handling? | Silent? |
|---|---|---|---|---|
| `roll_up` | Cycle in `parent_node_id` (not enforced anywhere today) | planned | visited-set guard, else infinite loop | **hang, not error** |
| `roll_up` | `parent_node_id` names a node absent from `_nodes` (cross-worker partial read) | planned | treat as root, never `KeyError` | **would be silently wrong** |
| `UsageAccumulator.fold` | Mixed rated + unrated on one node renders a partial total as if complete | planned | `rated_inference_calls` + the UI "≥" marker | **would be silently wrong money** |
| UI token chip | Consumer sums `nb_tokens_by_category`, double-counting `input_cached` | planned | `total_tokens` is the only sanctioned total; docstring says so | **would be silently wrong** |
| `_handle_usage_report` | Event for a `node_id` that never emitted `PipeStartEvent` (worker died between) | planned | mirror the existing `log.warning(f"...unknown node: {event.node_id}")` used by every sibling handler | no, once handled |
| `graph.usage.unattributed` | Usage emitted outside any pipe context | planned | typed bucket, surfaced not dropped | no |
| Temporal retry | Retried activity re-emits usage at a new sequence — documented over-count R2 (`reporting_manager.py:265-270`) | not fixable here | none; inherited | yes, and now visible per-node |
| Phase 4 gate | `usage` null everywhere because Phase 1 mis-wired | T10 | none in `generate-fixtures.mjs` today | **yes without T10** |

**Critical gaps: 3.** The cycle guard (hang, no error), the dangling-parent rollup (silently wrong), and mixed rated/unrated (silently wrong *money*, the worst kind). All three are in Phase 1 and must land with it.

## NOT in scope

| Deferred | Why |
|---|---|
| Plumbing usage into the in-process `GraphTracer` | Its `GraphSpec` is discarded at all three call sites (D4). Divergence asserted instead. |
| Preserving `node_id` on `PipeOutput.tokens_usages` | Would change `TokensUsageRecord`, a shipped `extra="forbid"` client contract. The DRY win is taken via the shared module (D6) instead. |
| npm publish of `@pipelex/mthds-ui` + `make refresh-graph-ui-sri` | Local loop first. Nothing reaches users until this happens; deliberate later step. |
| Committing LIVE fixture regeneration | Real inference against current models; diff churns far past `usage`. |
| Per-model cost breakdown on a node | `NodeUsageSpec` is extensible; add `by_model` when something asks. |
| A real `GraphSpec` version field | Docs call GraphSpec "versioned" and it has no version field. Real gap, pre-existing, own change. TODO below. |
| Fixing the Temporal retry over-count (R2) | Pre-existing, documented, separate. |
| `mermaidflow` renderer | Text renderer, no cost surface planned. |
| Attributing cost to an org / debiting a balance | The deferred billing connection (`monetization-metering-already-exists`). Different consumer of the same stream. |
| `_generate_data_edges` nested-loop complexity (`graphspec_assembler.py:474-486`) | Pre-existing, flagged below, not touched. |

## Performance

Single pass over events; accumulation is O(1) per event. Rollup is O(n) memoized, O(n·depth) without — memoize. Payload grows by two small objects per node; negligible.

**Pre-existing, flagged not fixed:** `_generate_batch_item_edges` (`:474-486`) and `_generate_batch_aggregate_edges` nest a full node scan inside a per-item loop, so batch fan-out is roughly O(items × nodes × inputs). Invisible on 32 small fixtures; it will bite on a wide production batch.

## Parallelization

| Step | Modules touched | Depends on |
|---|---|---|
| Phase 1 model + attribute | `pipelex/graph/`, `pipelex/tracing/` | — |
| Phase 2 tests | `tests/unit/pipelex/` | Phase 1 |
| Phase 3 docs | `pipelex/docs/`, `CHANGELOG.md` | Phase 1 |
| Phase 4 DRY fixtures | `mthds-ui/scripts/`, `mthds-ui/data/`, `.../specs/` | Phase 1 |
| Phase 5 UI | `mthds-ui/src/graph/` | Phase 4 |
| Phase 6 LIVE fixtures | `mthds-ui/data/` | Phase 5 |

```
Lane A:  Phase 1 → Phase 2                    (sequential, shared pipelex/)
Lane B:  Phase 3                              (independent once Phase 1 lands — docs only)
Lane C:  Phase 4 → Phase 5 → Phase 6          (sequential, shared mthds-ui/)

Launch:  Phase 1 alone. Then B and C in parallel with A's remainder.
```

**Conflict flag:** Lanes B and C are clean against each other. Lane C reads the pipelex `.venv`, so do not start it until Phase 1 is committed.

## Implementation Tasks

- [x] **T1 (P1, human: ~3h / CC: ~30min)** — graphspec — `NodeUsageSpec`, `GraphUsageSpec`, and the four invariants as docstring contract
  - Surfaced by: D1/D3 — first draft overloaded `cost: None` four ways; `meta` bag was untyped
  - Files: `pipelex/graph/graphspec.py`
  - Verify: `.venv/bin/pytest tests/unit/pipelex/graph/test_graphspec_roundtrip.py`
- [x] **T2 (P1, human: ~4h / CC: ~40min)** — tracing — New `usage_attribution.py`: accumulator + rollup, one home for the invariants
  - Surfaced by: D6 — keeps a second aggregation model out of `_AssemblerState`
  - Files: `pipelex/tracing/usage_attribution.py`
  - Verify: new `tests/unit/pipelex/tracing/test_usage_attribution.py`
- [x] **T3 (P1, human: ~2h / CC: ~20min)** — assembler — Fold `UsageReportEvent`; attach a spec to EVERY node when collection was on
  - Surfaced by: `graphspec_assembler.py:197` `pass`; invariant 1 (controllers/PipeFunc/lifted nodes must not read as "not collected")
  - Files: `pipelex/tracing/graphspec_assembler.py`
  - Verify: `.venv/bin/pytest tests/unit/pipelex/tracing/test_graphspec_assembler.py`
- [x] **T4 (P1, human: ~2h / CC: ~20min)** — tracing — CRITICAL: cycle guard, dangling-parent tolerance, memoized rollup
  - Surfaced by: Failure modes — cycle hangs with no error; dangling parent is silently wrong
  - Files: `pipelex/tracing/usage_attribution.py`
  - Verify: `test_usage_attribution.py`
- [x] **T5 (P1, human: ~1h / CC: ~10min)** — assembler — `"unknown"` usage into `GraphSpec.usage.unattributed`; emit run total
  - Surfaced by: D3 — `reporting_manager.py:219` fallback would otherwise drop it
  - Files: `pipelex/tracing/graphspec_assembler.py`
  - Verify: `test_usage_attribution.py`
- [x] **T6 (P1, human: ~1h / CC: ~15min)** — tests — CRITICAL: assert the builder divergence in `test_assembler_equivalence`
  - Surfaced by: D4 — `:57` compares `metrics`, no scenario emits usage, divergence would be silent
  - Files: `tests/unit/pipelex/tracing/test_assembler_equivalence.py`
  - Verify: `.venv/bin/pytest tests/unit/pipelex/tracing/test_assembler_equivalence.py`
- [x] **T7 (P2, human: ~30min / CC: ~5min)** — assembler — Refresh the pass-1/pass-2 docstring at `:112-119`
  - Surfaced by: Code quality — docstring/diagram maintenance is part of the change
  - Files: `pipelex/tracing/graphspec_assembler.py`
  - Verify: read it
- [x] **T8 (P2, human: ~2h / CC: ~20min)** — docs — Under-the-hood page on the two projections and the three usage states
  - Surfaced by: workspace rule — document at every iteration
  - Files: `docs/under-the-hood/`, `docs/features/cost-tracking.md`, `CHANGELOG.md`
  - Verify: `make agent-check`
- [x] **T9 (P1, human: ~1h / CC: ~10min)** — mthds-ui — `usage` through `types.ts` and `pipeCardPayload.ts`
  - Surfaced by: Phase 5 — mirrors the existing `tags` passthrough at `pipeCardPayload.ts:23`
  - Files: `mthds-ui/src/graph/types.ts`, `pipeCardPayload.ts`, `pipeCardTypes.ts`
  - Verify: `npm run typecheck && npx vitest run pipeCardPayload`
- [x] **T10 (P1, human: ~1h / CC: ~15min)** — mthds-ui — Validate `usage` in `validateGraphSpec.ts`; extend `assertValid` in `generate-fixtures.mjs`
  - Surfaced by: Codex — the validator is the boundary gate; `assertValid` would pass an all-null regeneration
  - Files: `mthds-ui/src/graph/validateGraphSpec.ts`, `mthds-ui/scripts/generate-fixtures.mjs`
  - Verify: `make fixtures` fails loudly against a pre-Phase-1 pipelex
- [x] **T11 (P1, human: ~30min / CC: ~5min)** — mthds-ui — Add `--mock-usage` to the DRY arg list
  - Surfaced by: D5 — plain `--dry-run` yields zero-token usage, so the token chip is untestable for free
  - Files: `mthds-ui/scripts/generate-fixtures.mjs:124-131`
  - Verify: regenerated DRY fixtures show `total_tokens > 0` on LLM nodes
- [x] **T12 (P1, human: ~5h / CC: ~50min)** — mthds-ui — Usage chip, five distinct render states, subtree-vs-own by node kind
  - Surfaced by: D1/D2/D5 — unrated is the default view and must not look like `$0.00`; partial must not look complete
  - Files: `PipeCardBase.tsx`, `graph-core.css`, `PipeDetailPanel.tsx`
  - Verify: `make storybook`, inspect DRY and LIVE stories

## TODOs to capture

1. **`GraphSpec` has no version field** despite `graphspec.py:3` calling it "versioned" and `pipelex-hosted-envelope.md:96` calling it a strict contract. Adding `usage` under `extra="forbid"` is a hard break for any older reader with no way to detect it. Pre-existing; own change.
2. **Revive-or-delete the in-process `GraphTracer` GraphSpec.** Discarded at all three call sites. Either something consumes it or `close_tracer` stops returning it.
3. **`_generate_batch_item_edges` nested scan.** O(items × nodes × inputs) on batch fan-out. Needs a wide-batch benchmark to justify.

## Outside voice absorbed

Codex reviewed revision 1. Ten findings accepted, one partially, one noted as policy-exempt.

| Finding | Verdict |
|---|---|
| `cost: None` overloaded four ways | **Accepted** — invariants 1-3, `rated_inference_calls` |
| No subtree token rollup; controllers blank in DRY | **Accepted** — `subtree_nb_tokens_by_category`, `subtree_total_tokens` |
| Mixed rated/unrated renders a partial as complete | **Accepted** — invariant 3 + UI "≥" state |
| Summing `nb_tokens_by_category` double-counts `input_cached` | **Accepted** — canonical `total_tokens`, invariant 4 |
| `usage is None` ≠ "not collected" for zero-call nodes | **Accepted** — every node gets a spec; Phase 4 gate rewritten |
| DRY fixtures need `--mock-usage` to be meaningful | **Accepted** — T11 |
| `meta` bag is untyped; use a typed `GraphSpec.usage` | **Accepted** — D3 rewritten, `GraphUsageSpec` |
| `validateGraphSpec.ts` missing from the task list | **Accepted** — T10 |
| CSV cross-check semantics undefined (`null` vs `0`) | **Accepted** — Phase 6 states the comparison |
| Normalizing `usage` away weakens equivalence permanently | **Accepted** — D4 asserts the divergence instead |
| Preserve `node_id` on usage records, one shared rollup | **Partially** — shared module (D6) yes; changing `tokens_usages` no, it is a shipped `extra="forbid"` wire contract |
| `extra="forbid"` breaks older readers | **Noted, not acted** — workspace policy is explicitly no backward compatibility. The missing version field is a fair catch and is TODO 1. |

**No cross-model tension.** Codex did not contradict any review finding; it found gaps the review missed. The one strategic challenge (merge the two projections) was answered by taking its DRY intent without breaking a shipped contract.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | ISSUES_FOUND | 12 findings, 10 accepted, 1 partial, 1 policy-exempt |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | ISSUES_OPEN | 44 issues, 3 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **CODEX:** Outside voice ran on revision 1 and materially changed the design — the overloaded `cost: None`, the missing subtree token rollup, the double-counted `input_cached`, the untyped `meta` bag, and the missing `validateGraphSpec` gate all came from it.
- **CROSS-MODEL:** No tension. Codex found gaps rather than contradicting findings; its one strategic challenge (merge the two event-stream projections) was absorbed as a shared attribution module without changing the shipped `TokensUsageRecord` wire contract.
- **VERDICT:** ENG REVIEW COMPLETE — plan revised and ready to implement. Status is ISSUES_OPEN rather than CLEAR because 3 critical gaps (rollup cycle guard, dangling-parent tolerance, mixed rated/unrated partial cost) are planned but not yet built; they clear when T4 and T2 land.

NO UNRESOLVED DECISIONS
