---
title: "Actions Allowlist"
description: "Why every action a workflow of this repository uses must be on the organization's Actions allowlist, the committed mirror of that allowlist, and the guard that checks every workflow against it on each pull request."
---

# Actions allowlist

The Pipelex organization allows only some GitHub Actions to run, under a policy its enterprise enforces: actions created by GitHub, actions owned by the enterprise's organizations, and actions matching a list of patterns. GitHub applies that policy when it creates a run, and a workflow using an action the policy refuses does not run at all. GitHub ends it in `startup_failure`, with a message such as "The action … is not allowed in Pipelex/pipelex because all actions must be from a repository owned by your enterprise, created by GitHub, or match one of the patterns: …", before any of its jobs starts.

Most workflows would show such a refusal on the pull request that introduced the action. The release workflows do not: `publish-pypi.yml` fires only when a release pull request closes into `main`, and `publish-docker-hub.yml` runs only from it or by hand, so pull-request CI never loads them. An action the policy refuses there surfaces only when a release is cut, as a release that publishes nothing. This is how a Docker Hub overview step once stopped a release.

## The mirror: `.github/actions-allowlist.toml`

The policy lives on GitHub, in the organization's Actions settings, and this repository cannot read it without an administrator's token. So the repository commits a mirror of it, `.github/actions-allowlist.toml`, with three keys:

- `github_owned_allowed`: whether actions created by GitHub, those of the `actions` and `github` owners, are allowed.
- `enterprise_owners`: the organizations the enterprise owns, whose actions are allowed without a pattern.
- `patterns_allowed`: the policy's patterns, verbatim and in the order GitHub prints them.

When the policy changes, the mirror changes with it. An administrator reads the policy with:

```bash
gh api orgs/Pipelex/actions/permissions/selected-actions
```

and copies `github_owned_allowed` and `patterns_allowed` into the mirror. The mirror only follows the policy: adding a pattern to it does not make GitHub run the action, so a new third-party action needs the policy changed first, and the mirror second.

## The guard: `make check-actions-allowlist`

```bash
make check-actions-allowlist   # alias: make caa
```

The guard (`pipelex-dev check-actions-allowlist`, core in `pipelex/cli/dev_cli/commands/actions_allowlist_guard.py`) runs in `make agent-check`, in the `make check` aggregate, and in CI as the `Lint (actions allowlist)` job, which the required `Lint (all)` aggregate waits for. It reads every workflow directly under `.github/workflows/` and every local action definition under `.github/actions/`, takes each `uses:` reference from where GitHub reads one (`jobs.<job>.steps[].uses` and `jobs.<job>.uses` in a workflow, `runs.steps[].uses` in a composite action), and allows it when it is:

1. local, starting with `./`: an action or reusable workflow of this repository;
2. created by GitHub, when `github_owned_allowed` is true;
3. owned by an organization in `enterprise_owners`;
4. matched by a pattern of `patterns_allowed`.

Anything else fails the check, with the file, the line, the reference and the reason. A `docker://` image is refused as well, since no pattern can name one.

Patterns follow GitHub's syntax, and where that syntax leaves a doubt the guard takes the stricter reading, so that a pass here is a pass on GitHub: `*` matches any run of characters except `/`, `**` matches any run at all, the owner, repository and path compare without regard to case, and the ref after `@` compares exactly. `astral-sh/setup-uv@*` therefore allows every ref of that action, and `sigstore/gh-action-sigstore-python@790bc6befb9d733738f18d8f895854b453640ec9` allows that one commit only.

The guard refuses to pass vacuously: a missing or malformed mirror, a workflow that is not valid YAML, or a scan that finds no workflow or no `uses:` reference at all fails the check instead of reporting a pass.

## When the check fails

Use an action GitHub created, one an organization of the enterprise owns, or one a pattern allows. When no allowed action does the job, a `run:` step calling the tool or the API directly usually does. When the action is worth allowing, ask an administrator to add it to the organization's policy, then mirror the new pattern in `.github/actions-allowlist.toml` in the same pull request as the workflow that uses it.
