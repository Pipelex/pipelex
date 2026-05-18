# Batch partial failure — design notes

Status: **design scoping**, not yet a plan. Split out of [`README.md`](README.md) because it was mis-categorized as a quick win. Read the README's "direct mode vs Temporal mode" section first — this doc assumes that frame.

## Why this is its own doc

`gather_bounded` raises on the first exception (first-error-aborts): one malformed document in a 1000-document batch discards every good result. Collecting partial results instead *sounds* like a quick win — and the `gather_bounded` change really is trivial (stop raising the first exception, return results-or-exceptions).

But that part is worthless on its own. The value is entirely in what `PipeBatch` does with a partial result, and that is a cross-cutting design problem: it touches the type system, the MTHDS language contract, the reporting layer, the graph tracer, and the Temporal boundary.

This doc is **coupled to [`fan-out-scheduling.md`](fan-out-scheduling.md)**: the failure *policy* decided here (fail-fast vs collect-partial) determines whether that doc's semaphore fan-out needs sibling cancellation. The two should be decided together, or this one first.

## The constraining fact: a failed branch leaves nothing behind

Today, a failed branch produces **no `PipeOutput` at all**. The exception propagates out of `get_pipe_router().run(...)` inside `PipeBatch._run_branch`, through the factory, and would be captured by `gather_bounded` as an exception object. The branch's deep-copied `branch_memory` is discarded — the parent only ever harvests `pipe_output.main_stuff`.

So "keep the failed branch" is not free: `_run_branch` would have to *catch* and *return* a failure-carrying object instead of letting the exception raise.

## The three questions that define the design

### 1. Do we keep the failed branch's working memory?

Recommendation: **no.** Each branch has its own deep-copied `WorkingMemory`. Keeping hundreds of failed branches' working memories alive for a large batch is a memory blowup that serves no one. Keep only the **`ErrorReport`** (the error-handling branch already defines that type). The branch's memory dies with the branch.

### 2. Do we need an envelope over output stuff?

This is the central fork, and it is a *language-semantics* decision, not an implementation detail.

`PipeBatch`'s output is a `ListContent` whose items are `StuffContent` of the branch's output **concept**. Every item must be a valid instance of that concept. A failed branch has no valid instance. Three options:

- **Envelope.** Output becomes `ListContent[BatchItemOutcome]`, where `outcome = success(stuff) | failure(error_report)`. Clean and explicit — but it **changes the output concept type**. Every downstream pipe consuming a batch output now consumes envelopes; every `.mthds` file using batch is affected; the concept system and `validate_output_with_library` must accommodate it. This is an MTHDS language change.
- **Sparse list.** Drop failed items; the output list is shorter than the input list. This breaks **positional alignment** between input and output — and the graph tracer relies on it: `register_batch_item_extraction` / `register_batch_aggregation` key by `item_index`. Downstream code that zips input↔output breaks silently.
- **Side channel.** The output `ListContent` stays the plain concept (successes only), and failures go into a separate structure on `PipeOutput` / `JobMetadata`. Keeps the type contract for the happy items, but reintroduces the alignment problem and adds a parallel reporting path.

The envelope is the "solid over quick" choice (per the project dev principles), but it is genuinely a language change. It would likely be **opt-in via a `BatchParams` flag**, so default batches keep the plain `ListContent` and fail-fast, and only batches that explicitly ask for partial-tolerance produce envelopes.

### 3. How do we report?

Tie into the error-handling branch's `ErrorReport`. A batch outcome is: counts (succeeded / failed) plus a per-failed-index `ErrorReport`. That touches:

- `agent_output.py` needs a "partial batch" renderer;
- the CLI needs an exit-code policy for partial success (is 847/1000 a success or a failure?);
- under Temporal each branch is a child workflow, so failures arrive as `ChildWorkflowError` — which already carries `ErrorReport` per `wip/error-handling/track-temporal-integration.md` — and the parent batch workflow has to aggregate them.

## Blast radius

- `gather_bounded` — trivial change (return results-or-exceptions).
- `PipeBatch._live_run_controller_pipe` harvest loop — currently assumes every entry is a `PipeOutput`.
- `PipeBatch._run_branch` — must catch and return a failure object instead of raising.
- The output concept type — envelope vs sparse vs side channel.
- Concept validation (`validate_output_with_library`).
- **Every downstream batch consumer, and every `.mthds` file using batch** — if the envelope option is taken.
- Graph tracer — `register_batch_aggregation` keys per `item_index`; a failed index has no `item_stuff_code`.
- Failed-branch working-memory disposal.
- `ErrorReport` aggregation across branches.
- `agent_output.py` rendering + CLI exit code.
- Temporal — `ChildWorkflowError` aggregation in the parent batch workflow.
- A new `BatchParams` opt-in flag.

## Direct vs Temporal

The decision logic is the same in both modes — the change runs as workflow code under Temporal, is deterministic, and is compatible. It is *more* valuable under Temporal: each batch branch is a durably-executed child workflow, so first-error-aborts there discards durably-completed work. The Temporal-mode shape of the change is aggregating per-branch `ChildWorkflowError`s instead of in-process exceptions.

## Open questions for the design session

- Envelope, sparse list, or side channel? (Recommendation leans envelope, opt-in via `BatchParams`.)
- Default behavior: fail-fast (status quo) or collect-partial? If opt-in, fail-fast stays the default.
- If envelope: what is `BatchItemOutcome` exactly, and how does the concept system express "list of outcomes of concept X"?
- Exit-code / success semantics for a partially-failed batch at the CLI and agent-output layer.
- Does a downstream pipe ever need to *consume* a partial batch (branch on per-item success), or is partial failure always terminal reporting?
- Interaction with [`fan-out-scheduling.md`](fan-out-scheduling.md): the failure policy chosen here drives whether the semaphore fan-out cancels siblings on first error (fail-fast) or runs every branch (collect-partial). This design also decides who interprets the results-or-exceptions list `gather_bounded` would return, and how.

## Suggested next step

Decide question 2 (envelope vs sparse vs side channel) first — every other question and the entire blast radius depend on it. Prototype the envelope option against one real downstream batch consumer to measure the true cost of the language change before committing.
