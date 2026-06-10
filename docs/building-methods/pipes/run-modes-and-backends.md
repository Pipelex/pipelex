---
description: "All the ways to run a Pipelex pipeline: live, dry-run, or mock-inference — in-process or distributed on Temporal. The run mode and the execution backend are independent axes."
---

# Run Modes & Backends

Pipelex separates **what the inference leaves do** (the run mode) from **where the work executes** (the backend). The two axes are independent: any run mode works on any backend, because the run mode travels with every inference job and is honored at the leaf — the last stop before a provider would actually be called.

## Axis 1: Run Mode

| Run mode | CLI trigger | Python trigger | AI providers | Usage & cost report |
|---|---|---|---|---|
| **Live** (default) | — | — | Real calls | Real usage, report rendered |
| **Dry run** | `--dry-run` | `pipe_run_mode=PipeRunMode.DRY` | Never called — leaves build mocks | Zero tokens, report suppressed |
| **Mock inference** | `--mock-inference` | `is_mock_inference=True` | LLM calls faked at the leaf | Non-zero *synthetic* usage, report rendered |

**Live** runs call the configured AI providers for real: real cost, real latency, and storage IO for generated images and extracted pages.

**Dry run** exercises the full pipeline — controllers, working memory, data flow, execution-graph tracing — with no AI cost. Each inference leaf branches to a format-compliant mock instead of calling the provider (see [Dry Run Mock Generation](../../under-the-hood/dry-run-mock-generation.md)). A dry run needs no API keys, performs no storage IO (mocked images and pages never touch the storage provider), reports zero-token usage, and suppresses the end-of-run cost report. Add `--mock-inputs` to also synthesize any missing required inputs (it requires `--dry-run`).

**Mock inference** is a *live* run whose LLM leaves fake the call and emit non-zero synthetic usage, so the whole cost-tracking pipeline renders end-to-end without spending tokens. That's its purpose: testing usage aggregation and cost reporting, including cross-worker report assembly on Temporal. It is LLM-only — pipes that need image generation, document extraction, or web search fail loud with `MockInferenceUnsupportedError`. It cannot be combined with `--dry-run`: a dry run already mocks every leaf and suppresses its report, which would silently swallow the flag.

## Axis 2: Backend

| Backend | Trigger | What runs where |
|---|---|---|
| **Direct** (default) | — | Everything in your process |
| **Temporal** | `--temporal`, or config `[temporal] is_enabled = true` | Controllers as child workflows, inference leaves as activities on workers |

The run mode rides across the wire with every inference job, so the backend never changes *what* a leaf does — only *where* it does it. In particular, when you run a **pipeline** in dry mode on Temporal, the real inference activities are still dispatched and mock **inside** them on the worker. That's by design: it lets you test the entire distribution machinery — dispatch, scheduling, serialization, task-queue routing, cross-worker graph tracing — with zero AI spend and no credentials.

One job type deliberately opts out of this fan-out: a **validation sweep** submitted through the runner API runs as a single in-process activity instead of dispatching nested activities — see [Validation Sweeps](#validation-sweeps) below for how that fits the model.

## The Matrix

All cells below describe **pipeline runs** — `pipelex run ...` or `PipelexRunner.execute_pipeline()`. Validation sweeps have their own distribution shape, covered in the next section.

| Run mode \ Backend | Direct (in-process) | Temporal |
|---|---|---|
| **Live** | Standard local run. | Durable distributed run; real inference executes on workers. |
| **Dry run** | Leaves mock inline. Validates pipeline logic and data flow at zero cost. | Activities are genuinely dispatched and mock inside the worker — proves out the distribution machinery with no API keys, no spend, no storage IO. |
| **Mock inference** | LLM leaves fake the call; the cost report renders from synthetic usage. | Same, plus worker-side usage flows back and aggregates into the submitter's single cost report. |

```bash
# Live + direct (the default)
pipelex run bundle my_bundle.mthds

# Dry run + direct
pipelex run bundle my_bundle.mthds --dry-run --mock-inputs

# Live + Temporal
pipelex run bundle my_bundle.mthds --temporal

# Dry run + Temporal — dispatches real activities, mocks inside them
pipelex run bundle my_bundle.mthds --temporal --dry-run --mock-inputs

# Mock inference — live run mode, faked LLM calls, rendered cost report
pipelex run bundle my_bundle.mthds --mock-inference
pipelex run bundle my_bundle.mthds --temporal --mock-inference
```

From Python, the same knobs live on the runner — the backend comes from config:

```python
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexRunner

runner = PipelexRunner(
    bundle_uri="path/to/my_bundle.mthds",
    pipe_run_mode=PipeRunMode.DRY,   # or is_mock_inference=True for mock inference
)
response = await runner.execute_pipeline()
```

## Validation Sweeps

`pipelex validate` (see the [validate commands](../../tools/cli/validate.md)) combines static validation with a dry run of every pipe. It relates to the matrix in two specific ways:

- **The CLI sweep always runs in-process**, even when Temporal is enabled. The `--temporal` flag on `pipelex validate` exists precisely to verify that: it flips the boot config so you can confirm a validation sweep does not dispatch anything under a Temporal-enabled setup.
- **The runner API's `/validate` route ships the sweep to a worker — as one activity**: with Temporal enabled, it offloads the *whole* sweep as a single activity (`act_dry_validate`, wrapped in the `WfDryValidate` workflow). Inside that activity, the pipe router and the content generator are scoped to their in-process variants, so nothing nested is dispatched: every dry run in the sweep behaves exactly like the dry × direct cell of the matrix, just hosted on a worker instead of your machine. The per-pipe statuses plus the execution graph come back in one round-trip. See [Temporal integration](../../under-the-hood/temporal-integration.md) for the mechanics.

This is not a contradiction of "the run mode never changes the backend" — it's the same leaf-mock foundation with a different *backend choice* for the nested work. A `--temporal --dry-run` pipeline run picks the Temporal backend all the way down, fanning out for real to test the distribution machinery. A Temporal validation sweep picks the Temporal backend for exactly one hop (get the sweep onto a worker) and the in-process backend for everything inside, because its goal is a cheap interactive answer, not distribution testing. Two deliberate opposites built from the same parts.

## Forced Dry Mode

When a process boots without inference configured — `Pipelex.make(needs_inference=False)`, e.g. no AI provider set up — every run that process initiates is forced to dry-run mode. This is a property of the run, not of the backend: under a Temporal-enabled boot the forced-dry run still dispatches activities and mocks inside them, like any other dry run. If an explicit `--mock-inference` is swallowed by forced dry mode, a warning says so.

## See Also

- [Validation & Dry Run](../../features/validation-dry-run.md) — feature overview
- [Dry Run Configuration](../../configuration/config-pipeline-validation/dry-run-config.md) — mock list sizes, allowed-to-fail pipes
- [Cost Tracking & Reporting](../../features/cost-tracking.md) — what the usage reports contain
- [Distributed Execution](../../distributed-execution/index.md) — running on Temporal
- [Dry Run Mock Generation](../../under-the-hood/dry-run-mock-generation.md) — how format-compliant mocks are built
