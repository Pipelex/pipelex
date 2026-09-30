---
name: release
description: >
  Cut a release of pipelex-api, the source-available Pipelex runner published as the
  pipelex/pipelex-api image on Docker Hub: the release/vX.Y.Z worktree, the
  pyproject.toml bump with the uv.lock and the OpenAPI artifact that follow, the
  changelog entry, the quality gates, one commit, and a pull request to main. Use
  when the user says "release", "cut a release", "bump version", "prepare a
  release", "make a release", "ship it", "create release branch", "promote dev to
  main", "tag a version", or any variation of shipping a new version of
  pipelex-api. Changelog content passed inline ("/release Added a build route")
  becomes the entry. The merge is landed by /ledger-land, never by this skill.
---

# Releasing pipelex-api

The procedure is the workspace release play, [`docs/workspace/releasing.md`](../../../../docs/workspace/releasing.md) at the workspace root — `../docs/workspace/releasing.md` from this repo's own root, which resolves the same from the main checkout and from any worktree. Read it first, then run it with what follows. The repo key is `pipelex-api`, the base is `dev`, and the pull request targets `main`: `guard-branches.yml`'s `gate-main` job refuses any head branch into `main` that is not `release/vX.Y.Z`, so there is no other way in. The release worktree is `_pipelex-api--release`, made with `wt add pipelex-api release --branch release/vX.Y.Z`. `wt` resolves the base from `origin/dev`, copies the gitignored files `.worktreeinclude` names (`.env` and the Pipelex override files), and runs the `make install` that `.worktree.toml` declares, which is what creates the `.venv` every gate below runs out of. The declaration is needed because the root `Makefile` pulls `install` in from `Makefiles/Makefile_basics.mk`, and `wt`'s own probe reads only the root `Makefile`, so without it the worktree comes up with no `.venv` at all.

## What ships

The merge to `main` publishes through a chain: `auto-release.yml` fires on the push and dispatches the two workflows that publish the artifacts, while `deploy-docs.yml` fires on the same push on its own.

- **`auto-release.yml`** fires on `push` to `main`. It reads the version out of `pyproject.toml`, and stops silently when `gh release view "v$VERSION"` already answers — so a push to `main` carrying no bump is a green no-op rather than a failure. Otherwise it refuses to go on unless `CHANGELOG.md` carries a `^## \[v$VERSION\] - ` line ("No changelog entry for v$VERSION in CHANGELOG.md — refusing to publish"), then dispatches the other two with `gh workflow run <workflow> --ref main -f version="$VERSION"`.
- **The Docker Hub image**, by `deploy.yml` — `make deploy-docker-hub` builds for `linux/amd64` and pushes `pipelex/pipelex-api:X.Y.Z` and `pipelex/pipelex-api:latest`. It re-reads `pyproject.toml` and errors out when the version it was handed disagrees with it. Besides the dispatch, both publishing workflows carry a `push: tags: 'v*'` trigger, so a hand-pushed `vX.Y.Z` tag fires the image build and the GitHub Release together — the one way into them that does not go through `auto-release.yml`.
- **The GitHub Release and the `vX.Y.Z` tag**, by `github-release.yml` — the notes are the changelog section for that version, blank lines dropped and every line's leading whitespace stripped; with no matching heading it warns, leaves the notes empty and creates the Release carrying the bare line `Release vX.Y.Z`, which on the normal path is unreachable because `auto-release.yml` already failed on the missing entry. No workflow anywhere in this repo runs `git tag`, so the tag exists only as a side effect of `gh release create` — it is lightweight, and it is created with no `--target`, so it names the head of the default branch. Read tags with `git tag --list`, and pass `--tags` to `git describe`.
- **The documentation site**, by `deploy-docs.yml`, which fires on the push to `main` and runs `uv run mkdocs gh-deploy --force --clean` onto `gh-pages`, served at <https://pipelex.github.io/pipelex-api/>. `docs/changelog.md` snippet-includes `CHANGELOG.md`, so the entry written for this release is what the site publishes as its changelog.

The landing verifies the publish — the runs, the registry's answer, the tag:

```bash
gh run list --workflow=auto-release.yml --branch main --limit 3 --json conclusion,headSha,url  # the run whose headSha is the merge SHA: success
gh run list --workflow=deploy.yml --limit 3 --json conclusion,event,url                        # the workflow_dispatch run it triggered
gh run list --workflow=github-release.yml --limit 3 --json conclusion,event,url
curl -s https://hub.docker.com/v2/repositories/pipelex/pipelex-api/tags/X.Y.Z | jq -r .name    # the registry's answer
git fetch --tags --prune origin && git tag --list vX.Y.Z                                       # the tag
gh release view vX.Y.Z                                                                          # the Release and its notes
```

`docker manifest inspect pipelex/pipelex-api:X.Y.Z` reads the registry without pulling the image, where a Docker daemon is available. The two publishing runs list under `main` with event `workflow_dispatch`, not under the release branch, because that is how `auto-release.yml` starts them.

**Recovery is by hand, not by re-pushing.** Once the GitHub Release exists, `auto-release.yml` skips everything on any later push to `main`, so a run that created the Release but failed to push the image cannot be repaired by another push. Dispatch the failed workflow yourself with the same version — `gh workflow run deploy.yml --ref main -f version=X.Y.Z` — or re-run its failed jobs.

## Version files and the lock

- **`pyproject.toml`** — the `[project]` table's `version`, and nothing else in the file. Keep it the file's **first** `version = ` line: `version-check.yml` and the root Makefile both read it with `grep '^version'`, and `auto-release.yml` and `deploy.yml` with `sed -n 's/^[[:space:]]*version = "\(.*\)"/\1/p'`.
- **The lock** — `make li` (`lock` then `install`) regenerates `uv.lock` and syncs the venv. Stop and report if it fails rather than committing a stale lock: `lint-check.yml` runs `uv lock --check` and fails the pull request over one.
- **Also stamped:** `docs/openapi/pipelex-api.openapi.yaml`, regenerated by `make openapi-export`. The artifact embeds the app version in `info.version`, so bumping `pyproject.toml` **always** makes it stale. That is why the export is a gate marked after the bump below, and why a release that skips it opens a pull request that `make openapi-check` fails in CI.

## Gates

Run in the worktree, in this order:

1. **`make check`** — `cleanderived`, ruff format, `ruff check --fix`, pyright, mypy, then `check-unused-imports`, `pylint`, `openapi-check` and `kit-check`. **Use this target and no lighter one.** `make agent-check`, `make c` and `make cc` all stop short of it: none of them runs `openapi-check` or `kit-check`, the two drift gates CI runs, so a green shorthand says nothing about the artifact or about the vendored `.pipelex/inference/` tree matching the pinned `pipelex`. It **rewrites files** (ruff format and `ruff check --fix`), so whatever it touches joins the release commit. Red blocks the release: fix the code, never loosen the target.
2. **`make agent-test`** — the pytest suite over the usual marker set, quiet unless it fails. `tests-check.yml` runs `make gha-tests` on the pull request across its Python matrix, and the two marker sets are not nested in either direction: CI additionally excludes `gha_disabled`, the local set additionally excludes `needs_output` and every non-`dry_runnable` test marked `llm`, `img_gen` or `ocr`, and CI adds `--disable-inference` and `--exitfirst`. A green here is a strong signal rather than a promise — `make gha-tests` is the target that reproduces the CI leg exactly.
3. **After the bump: `make openapi-export`, then `make check` again.** The bump in the play's step 7 is what invalidates the committed artifact, and this is the only place that is caught — the pre-bump `make check` structurally cannot see version-driven drift. Confirm the diff is the expected `info.version` change plus any genuine schema change this release carries; anything else means the artifact had already drifted before the release and wants investigating. Both `openapi-export` and `openapi-check` depend on the Makefile's `install` rather than `env`, on purpose: the schema is generated from what is actually installed in `.venv`, and syncing first is what makes the local result match CI, which installs from the lock.
4. **`make docs-check`** — `mkdocs build --strict`. It is unconditional for a release here, unlike in most repos: `doc-check.yml` filters on `docs/**` and `mkdocs.yml`, and the regenerated OpenAPI artifact lives under `docs/`, so a release pull request always trips that workflow. The changelog is in the same build, through `docs/changelog.md`'s snippet include of `CHANGELOG.md`.
5. **`pipelex` resolves from PyPI** — `grep -n '^\[tool\.uv\.sources\]' pyproject.toml` prints nothing, and the `source` line under `name = "pipelex"` in `uv.lock` reads `{ registry = … }`. A git or path override is how a branch builds against an unreleased `pipelex`, and the image is built from the lock with `uv sync --frozen`, so a release carrying one ships that commit under the pinned version's number. `version-check.yml` refuses the pull request on the same condition. The cure is `bump-pipelex` onto a published release before the release, never a hand edit inside it — and when no published release carries what the branch needs yet, the release waits.

## The release commit

`pyproject.toml`, `CHANGELOG.md`, `uv.lock`, `docs/openapi/pipelex-api.openapi.yaml`, and each file `make check` rewrote — staged by name.

## CI on the release pull request

- **`guard-branches.yml`** (`pull_request_target`) — `gate-main` refuses any head into `main` that does not match `^release/v[0-9]+\.[0-9]+\.[0-9]+$`, so the release branch name is the only way in. Its `protect-workflows` job additionally blocks workflow-file changes from authors whose association is `CONTRIBUTOR`.
- **`version-check.yml`** — on every pull request to `main`: `pipelex` resolves from PyPI (gate 5 above), and the `pyproject.toml` version equals the version in the branch name. A head that is not a release branch does not slip past it — the first step's `exit 0` ends that step alone, and the comparison that follows then fails against an empty branch version.
- **`changelog-check.yml`** — gated on `startsWith(github.head_ref, 'release/v')`: `CHANGELOG.md` carries a `## [vX.Y.Z] -` heading for the version in the branch name. It asserts nothing about `[Unreleased]`; leaving none behind is the play's rule, not CI's.
- **`lint-check.yml`** — on every pull request, a matrix of Python versions: `uv lock --check`, the merge-checks (ruff format, ruff lint, pyright, mypy), `make openapi-check` and `make kit-check`. The aggregator job `Lint (all versions)` is the single required status.
- **`tests-check.yml`** — on every pull request, `make gha-tests` across the same matrix.
- **`doc-check.yml`** — `mkdocs build --strict` whenever `docs/**` or `mkdocs.yml` changed, which a release always does.
- **`cla.yml`** — the CLA assistant, allowlisted for maintainers.

## Particulars

- **No pre-release form.** `changelog-check.yml` fires on any head starting with `release/v` and then demands `^release/v([0-9]+\.[0-9]+\.[0-9]+)$`, so `release/v0.23.0-rc.1` does not skip the check the way it would elsewhere — it fails it. `guard-branches.yml` refuses such a head into `main` outright. The root Makefile also defines `check-version-format`, which holds the same line on the number itself — `^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$` against the `pyproject.toml` version — but nothing invokes it: no target depends on it and no workflow calls it, so it is a helper to run by hand rather than a gate the release passes through. Ship a plain `X.Y.Z`.
- **The changelog heading carries the `v`** — `## [vX.Y.Z] - YYYY-MM-DD`, which is exactly what `changelog-check.yml` greps for, what `auto-release.yml` refuses to publish without, and what `github-release.yml` slices the Release notes out of. No `[Unreleased]` heading is left behind; the next change re-creates one.
- **`pipelex` is pinned exactly.** `pyproject.toml` carries `pipelex[mistralai,anthropic,google,google-genai,bedrock,fal]==A.B.C`, not a floor, so the published image ships that one runtime version and a `pipelex` release reaches this server only when the pin moves. Moving it is the **`bump-pipelex`** skill, which re-locks, migrates `.pipelex/` config when the schema moved and can legitimately move the OpenAPI artifact — never a hand edit inside the release. A release that carries a pin move says so in its changelog entry.
- **The back-merge is a merge commit.** `dev` carries a `Merge branch 'main' into dev` after each release rather than a fast-forward; `/ledger-land` makes it, and the changelog is the one conflict it expects.
