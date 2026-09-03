# Deferred: pin third-party GitHub Actions to reviewed commit SHAs?

Deferred from PR [#1155](https://github.com/Pipelex/pipelex/pull/1155) review round 1 (2026-08-27). Reported by Greptile and cubic on `.github/workflows/mthds-standard-check.yml:41`:

- [Greptile thread](https://github.com/Pipelex/pipelex/pull/1155#discussion) — `PRRT_kwDOOwmMFc6cwNy5`
- [cubic thread](https://github.com/Pipelex/pipelex/pull/1155#discussion) — `PRRT_kwDOOwmMFc6cwZvg`

## The issue

The new `mthds-standard-check.yml` workflow references `actions/checkout@v4` and `astral-sh/setup-uv@v7` by mutable major-version tag. A moved tag would silently change the code executed with the workflow's workspace and token permissions. The bots recommend pinning to full commit SHAs.

## Why it deferred

This is not a defect in the PR — it is the repo's standing convention. Existing workflows reference standard actions by mutable tag throughout (`actions/checkout@v4`, `astral-sh/setup-uv@v7`, `actions/setup-python@v5`, …), and SHA pins are reserved for the credential-bearing publish path (`sigstore/gh-action-sigstore-python`, `pypa/gh-action-pypi-publish`, `actions/dependency-review-action`). Pinning three references in one new workflow would change nothing about the repo's supply-chain posture while diverging from its own style. Whether to pin is a repo-wide policy decision, not a per-workflow fix.

## Recommendation

Decide once, for the whole repo: either keep the current tags-for-standard-actions / SHAs-for-privileged-actions split as deliberate policy, or pin every third-party action to a reviewed SHA across all workflows in one sweep (with Dependabot or pin tooling such as `pinact` to keep the pins moving). If pinning wins, the sweep should cover all workflows in `.github/workflows/`, not just the new one.

## Raised again on PR #1184 (2026-09-02)

Greptile reported the identical finding on the new `Tests (ts emission gates)` job in `.github/workflows/tests-check.yml` — thread `PRRT_kwDOOwmMFc6eS72b`, flagging `actions/checkout@v4`, `astral-sh/setup-uv@v7` and `actions/setup-node@v4`. Deferred here unchanged, for the same reason and with one addition specific to that PR: the new job sits in the same file as the eight `matrix-test` shards, which already run `actions/checkout@v4` and `astral-sh/setup-uv@v7` unpinned on every pull request. Pinning only the new job would change nothing about what third-party code executes per PR, while making one job in the file disagree with the rest of it.

The recurrence is itself an argument for the recommendation above: the bots will raise this on every new workflow or job until the repo decides once and sweeps.
