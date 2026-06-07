# Open question: `temporalio==1.24.0` bump on the bridge branch

**Status:** flagged for review, not resolved. Low risk; left in place pending intent confirmation.

## What

`pyproject.toml` on `feature/Runtime-bridge-extraction` pins `temporal = ["temporalio==1.24.0", ...]`, while `dev` is on `temporalio==1.23.0`. The bump was introduced by the branch's first commit (`204cd749`, the bridge extraction carved off the `_workflows` worktree), not by any later bridge work.

## Why it's a question

The runtime bridge does not depend on a specific Temporal SDK version — `temporalio` is lazy-imported only inside the `TEMPORAL_*` branches and the existing `pipelex.temporal` glue, none of which references a 1.24-only API. So this bump looks like it rode along from the upstream `_workflows` branch rather than being required by this PR.

## Options

1. **Keep `1.24.0`** — if the bump is intentional (e.g. a fix we want, or to stay aligned with the worker image). Harmless if CI's in-process test server is happy on 1.24.0.
2. **Revert to `1.23.0`** to match `dev` and keep the PR free of unrelated dep changes. Requires `uv lock` regen + a temporal-integration test pass.

## Recommendation

Confirm with the dep owner whether 1.24.0 is wanted on `dev`. If there's no concrete reason, revert to `1.23.0` so the bridge PR carries only bridge changes. Either way it should be a deliberate decision, not an accidental carry-over.
