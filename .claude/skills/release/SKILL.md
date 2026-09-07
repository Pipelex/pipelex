---
name: release
description: >
  Cut a release of the pipelex Python package: the gates, the migration-ledger
  cross-check, the CHANGELOG.md entry, the pyproject.toml bump with the lock and
  the badge, one commit, and a pull request to main that publishes to PyPI on
  merge. Use when the user says "release", "cut a release", "bump version",
  "prepare a release", "make a release", "ship it", "create release branch",
  "promote dev to main", or any variation of shipping a new version of pipelex.
  Changelog content passed inline ("/release Added new extract backend") becomes
  the entry. The merge is landed by /ledger-land, never by this skill.
---

# Releasing pipelex

The procedure is the workspace release play, [`docs/releasing.md`](../../../../docs/releasing.md) at the workspace root — `../docs/releasing.md` from this repo's own root, which resolves the same from the main checkout and from any worktree. Read it first, then run it with what follows. The repo key is `pipelex`, the base is `dev`, and the pull request targets `main`. The release worktree is `_pipelex--release`, made with `wt add pipelex release --branch release/vX.Y.Z`.

## What ships

- **PyPI: `pipelex`.** `.github/workflows/publish-pypi.yml` builds and publishes through trusted publishing. It fires on the release pull request **closing merged into `main`** (`pull_request: types: [closed]`), not on the push to `main` — so the run is keyed to the release branch and its `headSha` is that branch's last commit, never the merge commit. Where the play says "the run on the merge SHA", read it here as the run on `release/vX.Y.Z`.
- **The GitHub Release and the `vX.Y.Z` tag.** The same workflow's `github-release` job creates them, and the tag exists only as a side effect of `gh release create`. The release is created and the dists attached *before* Sigstore signing, which is allowed to fail: an unsigned release is reported as a warning, not a failure, because the tag is the record of what shipped.
- **The documentation site.** `.github/workflows/deploy-docs.yml` fires on the push to `main` and runs `make docs-deploy-stable`, which deploys the version read from `pyproject.toml` with the `latest` alias and republishes the root sitemap.

The landing verifies the publish from three places:

```bash
gh run list --workflow=publish-pypi.yml --branch release/vX.Y.Z --limit 3 --json name,conclusion,headSha,event,url   # success
pip index versions pipelex                                          # the registry answers X.Y.Z
git -C <main> fetch --tags --prune origin && git -C <main> tag --list vX.Y.Z
```

`gh release view vX.Y.Z` confirms the Release and its notes. A publish that failed *after* the merge is recoverable only by hand: re-running the run replays the workflow file it started with, so use `workflow_dispatch`, which accepts `main`, `release/vX.Y.Z` and `pre-release/v*` and nothing else. The Release step is idempotent — it edits an existing release rather than failing on it.

## Version files and the lock

- **`pyproject.toml`** — the `[project]` table's `version`, the one and only place the number is written. Nothing in the package restates it: the runtime reads it back through `get_package_version()`. Keep it the file's **first** `version = ` line: `changelog-check.yml` and `publish-pypi.yml` both read it with `grep -m 1 'version = '`, and `version-check.yml` with `grep '^version'`.
- **The lock** — `make li` (lock + install) regenerates `uv.lock`. Stop and report if it fails; `uv-lock-check` in CI fails the pull request over a stale lock.
- **Also stamped:**
  - **`.badges/tests.json`** — set `"message"` to what `make test-count` prints, leaving every other field alone, then run `make check-test-badge` to confirm the two agree. A mismatch is a CI failure on the pull request.
  - **`.test_durations`** — `make store-test-durations`, the per-test timing map `pytest-split` uses to balance the CI test shards. The refresh is incremental: it collects the suite and measures only the tests missing from the map, so it takes seconds on a quiet release and writes no diff at all when nothing was missing. Read the coverage line it prints before judging how long it should take — past roughly 40% of the suite missing it falls back to re-measuring everything, which takes minutes; treat a long run as a hang only when it reported few tests missing. Include the file in the commit only when it changed. `make store-test-durations-force` is **not** part of the release flow; it is for when recorded values are no longer comparable to each other because the machine or the suite changed shape. The rationale is `docs/contribute/test-duration-map.md`.
  - **`pipelex/migration/ledgers/*.toml` and `pipelex/migration/goldens/`** — only when the migration gate below finds an unaccounted schema change, and then written by the `add-migration` skill, never by hand.

## Gates

1. **`make agent-check`** — format, lint, pyright, mypy, plus the migration-ledger legality check, the keyword-only convention, the hub-layering check and the drift contracts. It **rewrites files** (`fix-unused-imports`, `fix-keyword-only`, `format`), so whatever it touched joins the release commit. Red blocks the release: fix the errors, never skip the target.
2. **`make check-migration-schemas`** — the schema-coverage gate, which `make agent-check` does **not** run (it is a golden check and lives in `make check`), so without this step a moved configuration surface reaches a release with no migration to repair a user's file. Red blocks the release, and the cure is the **`add-migration`** skill: it derives the entry from the fingerprint diff the gate just printed, bumps the surface's schema version, regenerates the goldens and adds the changelog bullet. Then re-run the gate. Never run `make up-migration-schemas` to make it quiet — a green gate over an unaccounted removal is precisely the failure the gate exists to prevent.
3. **The ledger-against-changelog cross-check**, once the gate is green. Diff the ledgers against the tag of the version the pre-flight read — the previous release. `origin/main` is not a safe baseline, and from `main` itself that diff is empty:

   ```bash
   git diff v<current version> -- pipelex/migration/ledgers/
   ```

   The migration ledger and the changelog are deliberately separate artifacts saying the same thing to different readers, and this is the only place they are checked against each other. For every entry new since that release carrying `breaking = true`, confirm the changelog has a matching `**Migration:**` bullet naming the entry id and what a user has to do — house style is a bold label, then two to four complete sentences. Write it now if it is missing.

   - **A renumbered entry reads as two ids, and both need a mention.** A pre-history entry inserted below existing ones takes a version already in use and pushes everything above it up, so the diff shows one id modified and one added — which looks like two independent breaking changes and is one insertion. The changelog must name the new entry *and* say that the existing one was renumbered, so a reader who quoted the old id somewhere can still find it.
   - **Confirm `introduced_in` on every such entry.** It is written when the entry is authored, before the release number is known, so it is routinely one bump off. Nothing branches on it, but it is what a reader correlates the changelog against: fix it here rather than leaving it wrong.
   - **A breaking ledger entry makes this a minor release**, per the pre-1.0 convention. If the bump was settled as a patch and this step finds one, go back and settle the bump again before writing the version into the entry.

   Full context: `docs/migration-ledger.md`.

## The release commit

`pyproject.toml`, `CHANGELOG.md`, `uv.lock`, `.badges/tests.json`, `.test_durations` when `make store-test-durations` changed it, whatever `make agent-check` rewrote, and the `pipelex/migration/ledgers/*.toml` and `pipelex/migration/goldens/` files the `add-migration` skill wrote when it ran. By name.

## CI on the release pull request

The checks that exist for the release:

- **`guard-branches.yml`** (`gate-main`) — refuses any head branch into `main` that is not `release/vX.Y.Z` exactly. This is what makes the two checks below unavoidable.
- **`version-check.yml`** — `pyproject.toml`'s version equals the version in the branch name. It exits 0 and skips itself when the head is not a `release/vX.Y.Z` branch, so on its own it is no gate at all; the branch guard is.
- **`changelog-check.yml`** — `CHANGELOG.md` carries `## [vX.Y.Z] - ` for the version in `pyproject.toml`. It asserts nothing about `[Unreleased]`: a leftover heading passes CI and ships a wrong changelog, so removing it is this skill's job, not CI's.
- **`check-test-count-badge.yml`** — `make check-test-badge` on every pull request to `main`.
- **`package-check.yml`** (`uv-lock-check`, on every pull request) — `uv lock --locked` leaves `uv.lock` unchanged, and `requires-python` still starts at `>=3.11`.

The pre-main gates a release pull request meets that a pull request to `dev` never does — they are slower, and a red here is the release stopping:

- **`lint-fresh-check.yml`** — the read-only lint suite across every supported Python version with no mypy cache, so incremental-mypy drift and version-specific breakage cannot reach `main`.
- **`tests-full-check.yml`** — the full Python matrix, sharded and balanced by `.test_durations`.
- **`doc-check.yml`** — `mkdocs build --strict`, which runs unconditionally when the base is `main` rather than only when `docs/` changed.
- **`dependency-review.yml`** — fails on a newly introduced dependency vulnerable at moderate severity or above.

Everything that runs on every pull request gates it too, including `lint-check.yml`'s `Lint (agent-rules)` job (`make check-rules`, which `make agent-check` does not run), `tests-check.yml` and `mthds-standard-check.yml`. A red in `mthds-standard-check.yml` with no pinned-set change in the branch means the MTHDS standard moved, and the remedy is a dedicated change bringing the pinned natives to the standard's page — never a tweak to the release branch.

## Particulars

- **The migration gate feeds back into the bump.** A breaking entry found by the cross-check above turns a patch into a minor, so the bump is not final until that gate has run.
- **The pre-release track is a different flow, not this play.** `pre-release/vX.Y.Z(a|b|rc)N` is a *base* branch that work merges into: `prerelease-version-check.yml` validates the PEP 440 form against the branch name, `publish-pypi.yml` also fires on a merge into it and marks the GitHub Release a pre-release, and `deploy-docs.yml` publishes those docs under the `pre-release` alias. A `release/vX.Y.Z` branch therefore never carries a pre-release version: `version-check.yml` would skip a non-matching head, and `guard-branches.yml` would refuse it into `main` anyway.
- **The changelog heading carries the `v`** — `## [vX.Y.Z] - YYYY-MM-DD`, which is exactly what `changelog-check.yml` greps for and what `publish-pypi.yml` slices the GitHub Release notes out of. No `[Unreleased]` heading is left behind; the next change re-creates one.
- **`.worktreeinclude` names the gitignored files a fresh worktree needs** — `.env`, the `.pipelex/` overrides and `.pipelex-dev/test_profiles_override.toml` — and `wt add` provisions them. A gate that fails in `_pipelex--release` on a missing local config means that file is short: add it there rather than hand-copying the file every release.
