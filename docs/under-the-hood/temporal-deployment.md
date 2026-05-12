---
title: "Temporal Deployment"
description: "What a Temporal cluster operator needs to register before running Pipelex workers — the strict-prerequisite custom search attributes, the configurable surface, and the registration runbook."
---

# Temporal Deployment

This page covers the one-time cluster-side configuration Pipelex requires before workers can dispatch workflows on a real Temporal cluster. For the runtime mechanism (LibraryCrate propagation, deferred hydration, per-workflow isolation), see [Temporal Integration](./temporal-integration.md).

---

## Custom search attributes are a strict prerequisite

Pipelex attaches a fixed set of custom `Keyword` search attributes on every workflow start. They are the operator-facing surface in the Temporal dashboard — column filters, list-view queries, audit trails. They are also a **strict prerequisite**: a real Temporal cluster rejects every `StartWorkflowExecution` RPC that references an unregistered custom search attribute with `Namespace ... has no mapping defined for search attribute ...`. Workflows do not silently run with a degraded dashboard — they do not run at all.

The five built-in attributes Pipelex can populate:

| Attribute       | Type      | Value source                                |
|-----------------|-----------|---------------------------------------------|
| `PipeCode`      | `Keyword` | `pipe_job.pipe.code`                        |
| `PipelineRunId` | `Keyword` | `pipe_job.job_metadata.pipeline_run_id`     |
| `SessionId`     | `Keyword` | `TemporalManager.get_instance().session_id` |
| `UserId`        | `Keyword` | `pipe_job.job_metadata.user_id`             |
| `DomainCode`    | `Keyword` | `pipe_job.pipe.domain_code`                 |

Pipelex only knows how to populate these five built-ins. Arbitrary custom names are out of scope — they would require code that knows the value source.

---

## Configurable surface

The `[temporal.search_attributes]` block in `pipelex.toml` controls both what the workflow-start side attaches AND what the worker-boot check requires. The two stay in lockstep by construction.

```toml
[temporal.search_attributes]
# Master toggle. When false, workflow starts don't attach any custom search
# attributes, the worker-boot check is skipped, and the dashboard view falls
# back to WorkflowType / WorkflowId / StartTime only.
enabled = true

# Subset of the five built-in attributes to populate. Names not in this list
# are skipped at workflow-start time AND not required at worker boot. Names
# that are not built-ins are rejected by the config validator with a
# helpful error message.
attributes = ["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"]
```

Two operational modes:

- **`enabled = true` (default).** Every workflow start attaches the listed subset. The worker-boot check refuses to start the worker unless those names are registered on the namespace. Use this when the deployment owns its Temporal namespace and can register attributes once.
- **`enabled = false`.** No custom search attributes are attached at workflow start; the worker-boot check is skipped. Use this when the namespace policy is managed by a third party who will not register attributes for you, or in restricted dev/sandbox setups where the dashboard view does not matter.

---

## Hard-fail at worker boot

Every Pipelex worker process performs a one-shot `ListSearchAttributes` call on boot against its connected namespace. The contract:

- **All configured attributes present** → silent, worker proceeds.
- **Some configured attributes missing on a reachable namespace** → worker boot aborts with `SearchAttributeRegistrationError`. The exception message names the missing attributes and includes **both** the Pipelex CLI invocation and the equivalent raw `temporal` CLI command, so operators on either side of the fence can fix the gap.
- **Operator service unreachable (`RPCError`)** → `log.warning(...)` notes the namespace was not reachable. Worker proceeds; the cluster will reject workflow starts at dispatch time if the attributes are not registered, but blocking worker boot during a control-plane outage would be more harmful than helpful.
- **`enabled = false`** → the check is skipped entirely. No `ListSearchAttributes` call is made.
- **Any other exception** → propagates and crashes the worker (real bug).

Failing fast at worker boot — rather than at every workflow dispatch — is the design point of this phase. The previous warn-and-continue behavior produced thousands of unactionable `RPCError`s in the activity logs, one per dispatch, instead of one loud, copy-paste-fixable error at boot.

The check runs **once per worker process at boot**. There is no caching across processes — every worker performs its own check.

---

## Registering the attributes

Two equivalent registration paths. Pick whichever fits your operator topology.

### Path 1 — `pipelex setup-temporal-namespace`

Run this on the same host (and same `pipelex.toml`) the worker will use. It reads `[temporal.search_attributes].attributes` and `[temporal.temporal_config]`, connects via the same `connect_to_temporal_selected_server` helper as the worker, and registers the missing attributes via `OperatorService.AddSearchAttributes`. Idempotent — re-running after success is a no-op.

```bash
# Default: register against the selected server profile
pipelex setup-temporal-namespace

# Print the equivalent `temporal operator search-attribute create` invocation
# without executing — useful when the namespace admin needs to register on
# the operator's behalf.
pipelex setup-temporal-namespace --dry-run

# Target a non-default server profile from temporal_server_configs.
pipelex setup-temporal-namespace --server testing
```

Use this when the API key your worker uses has the `OperatorService.AddSearchAttributes` permission. On self-hosted Temporal that is usually the case. On Temporal Cloud, worker API keys typically do **not** have this permission — see Path 2.

### Path 2 — Temporal CLI / Cloud admin

Run by a namespace admin (someone whose credentials carry `Namespace Admin` or equivalent permission). The worker API key is not used.

```bash
temporal operator search-attribute create \
  --namespace <namespace> \
  --name PipeCode --type Keyword \
  --name PipelineRunId --type Keyword \
  --name SessionId --type Keyword \
  --name UserId --type Keyword \
  --name DomainCode --type Keyword
```

For Temporal Cloud, the admin can also use:

```bash
tcld namespace search-attributes add \
  --namespace <namespace> \
  --search-attribute PipeCode=Keyword \
  --search-attribute PipelineRunId=Keyword \
  --search-attribute SessionId=Keyword \
  --search-attribute UserId=Keyword \
  --search-attribute DomainCode=Keyword
```

or the Cloud UI: **Namespace → Custom Search Attributes**.

### Path 3 — `pipelex setup-temporal-namespace` falls back to the runbook

When `pipelex setup-temporal-namespace` runs against a Temporal Cloud namespace and the worker API key lacks `OperatorService.AddSearchAttributes` permission, the command catches the `PERMISSION_DENIED` RPC error and prints the exact Path 2 commands. Forward the output to your namespace admin — they can copy-paste it.

---

## Permission model for Temporal Cloud self-managed workers

If you run Pipelex workers against a Temporal Cloud namespace your own customer (or your customer's IT team) administers, the practical model is:

- The customer issues you an API key scoped to "workflow start / activity execution" — enough to dispatch workflows but **not** to register search attributes.
- The first time you stand up a worker against a fresh namespace, worker boot will fail with `SearchAttributeRegistrationError` listing the five attribute names.
- You run `pipelex setup-temporal-namespace --dry-run` and send the output to the customer's namespace admin.
- The admin runs `tcld namespace search-attributes add ...` (or uses the Cloud UI) — a one-time setup.
- Subsequent worker boots are silent.

Set `[temporal.search_attributes] enabled = false` if the customer refuses to register the attributes and you accept losing the Pipelex-specific dashboard filters.

---

## Bootstrap scripts for production

For production environments — Pipelex Cloud, Temporal Cloud, self-hosted Temporal — the registration step belongs in the namespace bootstrap script alongside other one-time namespace setup (replication config, retention policies, audit hooks). `pipelex setup-temporal-namespace` is a fine choice for that script; it shares the worker's `pipelex.toml` so the names registered there can never drift from the names the worker will dispatch with.

---

## In-process test server

The Temporal in-process test server (`WorkflowEnvironment.start_local()`, used by CI and unit tests) starts with no custom attributes registered. The integration test conftest registers them up front via `ensure_required_search_attributes_registered(..., configured_attributes=BUILTIN_SEARCH_ATTRIBUTES)` so all temporal tests can start workflows without per-test bootstrap. There is no need to set `enabled = false` for tests — the conftest covers it.
