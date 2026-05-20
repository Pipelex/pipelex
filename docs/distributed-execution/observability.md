---
title: "Workflow Observability"
description: "What Pipelex shows in the Temporal Web UI — workflow ids, activity ids, static summaries, per-activity summaries, and custom search-attribute filters."
---

# Workflow Observability

Every Pipelex workflow carries human-readable identity into the Temporal Web UI: a workflow id derived from your pipeline run id, a Markdown summary of the pipe and its inputs, per-activity summary lines that explain what each LLM or extract call is doing, and a set of custom search attributes for filtering. This page is the reference for everything you'll see in the dashboard.

For the cluster-side registration that enables search attributes, see [Cluster Setup](cluster-setup.md).

---

## Why this matters

Operators triage incidents from the Temporal dashboard. They sort by start time, filter by user or session, drill into a specific workflow, and read the activity history to see where things went wrong. Opaque ids and bytes-style summaries make that work fast or slow. Pipelex chooses verbosity at the dashboard boundary so the operator never has to leave it to identify a workflow.

---

## Workflow IDs

### Top-level workflows

Pipelex derives the workflow id from `JobMetadata.pipeline_run_id` with a short prefix that identifies the run environment:

```
{env_prefix}{pipeline_run_id}
```

Example: `ut-3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c`.

Environment prefixes:

| Prefix | Run mode            | When                              |
|--------|---------------------|-----------------------------------|
| `ut-`  | `UNIT_TEST`         | Unit test suites                  |
| `ci-`  | `CI_TEST`           | GitHub Actions / CI               |
| `cc-`  | `CODEX_CLOUD`       | Codex Cloud agent runs            |
| `cct-` | `CODEX_CLOUD_TEST`  | Codex Cloud test runs             |
| `` (none) | `NORMAL`         | Production / local development    |

Because the workflow id is derived from `pipeline_run_id`, a caller that controls that id (via `PipelineFactory.make_pipeline(pipeline_run_id=...)`) can replay onto the same Temporal **Workflow Execution Chain**. Each replay produces a fresh `run_id` under the SDK-default `ALLOW_DUPLICATE` reuse policy. This is documented behavior — the previous releases produced fresh workflow ids per execution by accident, via truncated session-id and random-shortuuid components, not by design.

### Child workflows

Pipelex builds child workflow ids as slash-separated paths off the parent's workflow id:

```
{parent_workflow_id}/pipe-router               # the fixed WfPipeRouter child of WfPipeRun
{parent_workflow_id}/{pipe_code}-{8-hex}       # a sub-pipe spawned by a router
```

The 8-hex suffix comes from `workflow.uuid4()` — Temporal's replay-safe UUID generator — so child workflow ids stay deterministic across worker restarts.

Operational tooling that parsed the previous nested-id format (which used `-` as the separator) must update to handle `/`.

---

## Activity IDs

Pipelex does not customize activity ids. The Temporal Python SDK auto-assigns deterministic sequential integers (`"1"`, `"2"`, …) per workflow run. This guarantees per-`(workflow_id, run_id)` uniqueness by construction and is replay-safe — the SDK assigns ids by history position.

Per-call semantic meaning lives in the per-activity `summary=` field instead. Examples:

```
LLM text · pipe=translate_doc · model=openai-gpt-4o
LLM object · pipe=invoice_extractor · class=Invoice
LLM object list · pipe=extract_line_items · class=LineItem
Img gen N× · pipe=cover · model=fal-flux-dev · n=3
Render page views · pipe=extract_doc
Extract pages · pipe=extract_doc · handle=azure-document-intelligence-extract
Templated text · pipe=summary
```

Anything that previously filtered or grouped Event History by the old semantic activity-id strings (`"craft-text"`, `"craft-object-direct"`, `"jinja2-text"`, `"extract-pages"`, etc.) must now read the per-activity `summary` field or the Activity Type.

---

## Static summary and details

Every top-level workflow start sets two fields the Temporal dashboard renders as Markdown:

### `static_summary`

A 200-byte one-liner shown in the workflow list view. Shape:

```
{pipe_code} — {description}
```

Example: `translate_doc — Translate a document from English to French`. The description is the optional `description` field on the pipe; when empty, only the pipe code is shown.

### `static_details`

A 20 KB Markdown table shown in the workflow detail view. Always includes:

| Field        | Value                              |
|--------------|------------------------------------|
| Pipe         | `translate_doc`                    |
| Domain       | `documents`                        |
| Pipeline run | `3f9c8b2a-...`                     |
| User         | `user-42`                          |
| Session      | `session-abc`                      |

Two optional rows are appended when the data is available:

- **Library crate** — the first 12 characters of the bundled `LibraryCrate.fingerprint`, when the workflow's `PipeJob` carries a crate.
- **Input** — comma-separated input stuff names, when the pipe declares inputs.

The formatting policy for both fields lives in `pipelex/temporal/tprl/observability.py`. Length caps follow Temporal's documented limits.

---

## Filtering and grouping with search attributes

Every workflow start attaches up to five custom `Keyword` search attributes:

| Attribute       | Value                                                              |
|-----------------|--------------------------------------------------------------------|
| `PipeCode`      | The pipe being executed                                            |
| `PipelineRunId` | The pipeline run id (= the workflow id, minus env prefix)          |
| `SessionId`     | The submitter session id (stamped at the top-level dispatch)       |
| `UserId`        | The user id from `JobMetadata`                                     |
| `DomainCode`    | The pipe's domain                                                  |

The set is configurable — only the attributes listed in `[temporal.search_attributes].attributes` are attached, and setting `enabled = false` skips them entirely. See [Cluster Setup](cluster-setup.md) for the registration steps the cluster needs before these can be used.

In the Temporal Web UI, use the **List Workflows** search bar with queries like:

```
PipeCode = "translate_doc"
UserId = "user-42" AND DomainCode = "documents"
PipelineRunId = "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"
```

Child workflows inherit `PipelineRunId`, `UserId`, and `SessionId` from their parent's `PipeJob`; `PipeCode` and `DomainCode` reflect the child's own pipe. Reading every field off the `PipeJob` (the workflow input) keeps the attribute build deterministic across replays.

---

## What's next

- **[Cluster Setup](cluster-setup.md)** — register the five search attributes before workers can dispatch workflows that use them.
- **[Worker Deployment](workers.md)** — run the workers that produce these events.
- **[Task-Queue Routing](task-routing.md)** — control which worker pool each activity lands on; the dashboard shows the resolved queue per call.
