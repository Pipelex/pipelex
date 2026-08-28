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
