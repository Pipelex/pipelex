---
title: "Temporal Deployment"
description: "What a Temporal cluster operator needs to register before running Pipelex workers — required custom search attributes and the registration runbook."
---

# Temporal Deployment

This page covers the one-time cluster-side configuration Pipelex requires before workers can dispatch workflows that filter cleanly in the Temporal dashboard. For the runtime mechanism (LibraryCrate propagation, deferred hydration, per-workflow isolation), see [Temporal Integration](./temporal-integration.md).

---

## Required custom search attributes

Pipelex sets five custom Keyword search attributes on every workflow start. They are the operator-facing surface in the Temporal dashboard — column filters, list-view queries, audit trails. Without them, workflows still run, but every filter narrows to `WorkflowType` / `WorkflowId` / `StartTime` and the Pipelex-specific dimensions are invisible.

| Attribute       | Type      | Value source                                     |
|-----------------|-----------|--------------------------------------------------|
| `PipeCode`      | `Keyword` | `pipe_job.pipe.code`                             |
| `PipelineRunId` | `Keyword` | `pipe_job.job_metadata.pipeline_run_id`          |
| `SessionId`     | `Keyword` | `TemporalManager.get_instance().session_id`     |
| `UserId`        | `Keyword` | `pipe_job.job_metadata.user_id`                  |
| `DomainCode`    | `Keyword` | `pipe_job.pipe.domain_code`                      |

All five must be registered as `Keyword` on the target Temporal namespace before workflows that set them are accepted by the cluster.

### How to register them

Run the equivalent of:

```bash
temporal operator search-attribute create \
  --namespace default \
  --name PipeCode --type Keyword \
  --name PipelineRunId --type Keyword \
  --name SessionId --type Keyword \
  --name UserId --type Keyword \
  --name DomainCode --type Keyword
```

Use the corresponding `tctl` invocation, the Temporal Cloud UI action, or the namespace bootstrap script in your deployment infrastructure. The exact incantation is shipped in the worker boot warning (see below), so a fresh operator can copy-paste it from the log.

### Worker-startup soft-fail check

Every Pipelex worker process performs a one-shot `ListSearchAttributes` call on boot against its connected namespace. The check is a *soft fail*:

- All five present → silent, worker proceeds.
- Some missing → `log.warning(...)` names the missing attributes and includes the exact registration command. Worker proceeds; dashboard filtering is degraded until the attributes are registered.
- The operator service is unreachable (`RPCError`) → `log.warning(...)` notes the namespace was not reachable. Worker proceeds; the check is best-effort.

Anything other than `RPCError` propagates and crashes the worker — that signals a real bug, not a degraded-dashboard concern.

The check runs **once per worker process at boot**. There is no caching across processes — every worker performs its own check.

### Why soft-fail

A hard-fail bootstrap would block a working dev environment whose only "problem" is a missing dashboard filter. The default Temporal in-process test server (used by CI) does not implement custom search attributes at all, so a hard-fail would also block CI without operational benefit. The warning makes the gap visible and copy-paste-fixable, without blocking the path to running pipes.

---

## Bootstrap scripts

For production environments — Pipelex Cloud, Temporal Cloud, self-hosted Temporal — the registration step belongs in the namespace bootstrap script alongside other one-time namespace setup (replication config, retention policies, audit hooks). The Pipelex side does not register the attributes automatically; the cluster admin owns that decision.
