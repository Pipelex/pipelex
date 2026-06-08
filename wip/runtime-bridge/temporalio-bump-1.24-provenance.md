# `temporalio==1.24.0` bump on the bridge branch

**Status: RESOLVED — keep `1.24.0`** (maintainer decision, 2026-06-07). The bump lands with this PR; `dev` moves from `1.23.0` to `1.24.0` on merge. No code change needed; this note is kept as the provenance record.

## What

`pyproject.toml` on `feature/Runtime-bridge-extraction` pins `temporal = ["temporalio==1.24.0", ...]`, while `dev` is on `temporalio==1.23.0`. The bump was introduced by the branch's first commit (`204cd749`, the bridge extraction carved off the `_workflows` worktree), not by any later bridge work.

## Why it's a question

The runtime bridge does not depend on a specific Temporal SDK version — `temporalio` is lazy-imported only inside the `TEMPORAL_*` branches and the existing `pipelex.temporal` glue, none of which references a 1.24-only API. So this bump looks like it rode along from the upstream `_workflows` branch rather than being required by this PR.

## Decision

Keep `1.24.0` — confirmed wanted on `dev`. The bridge itself is version-agnostic (lazy import, no 1.24-only API), but staying current is fine and CI exercises it on the in-process test server.
