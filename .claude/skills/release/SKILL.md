---
name: release
description: >
  Cut a release of pipelex, which ships the pipelex and pipelex-api packages and
  the pipelex/pipelex-api Docker image under one version: the gates, the
  migration-ledger cross-check, the CHANGELOG.md entry, the pyproject.toml bump
  with the lock and the badge, one commit, and a pull request to main that
  publishes to PyPI and Docker Hub on merge. Use when the user says "release",
  "cut a release", "bump version", "prepare a release", "make a release",
  "ship it", "create release branch",
  "promote dev to main", or any variation of shipping a new version of pipelex.
  Changelog content passed inline ("/release Added new extract backend") becomes
  the entry. The merge is landed by /ledger-land, never by this skill.
---

# Releasing pipelex

The procedure is the workspace release play, [`docs/workspace/releasing.md`](../../../../docs/workspace/releasing.md) at the workspace root — `../docs/workspace/releasing.md` from this repo's own root, which resolves the same from the main checkout and from any worktree. Read it first, then run it with what follows. The repo key is `pipelex`, the base is `dev`, and the pull request targets `main`. The release worktree is `_pipelex--release`, made with `wt add pipelex release --branch release/vX.Y.Z`.

## What ships

One version, three artifacts, all from one run of `.github/workflows/publish-pypi.yml`, in this order: the `pipelex` wheel, then the `pipelex-api` wheel and, once the GitHub Release has tagged the release commit, the image. The server in `api/` takes the library's version, so nothing of it is bumped separately.

- **PyPI: `pipelex`.** `.github/workflows/publish-pypi.yml` builds and publishes through trusted publishing. It fires on the release pull request **closing merged into `main`** (`pull_request: types: [closed]`), not on the push to `main` — so the run is keyed to the release branch and its `headSha` is that branch's last commit, never the merge commit. Where the play says "the run on the merge SHA", read it here as the run on `release/vX.Y.Z`.
- **PyPI: `pipelex-api`.** The same workflow's `build-api` job builds the server's wheel and sdist and refuses them unless `api/scripts/check_lockstep_pin.py` finds `pipelex[...]==X.Y.Z` in both, the pin `api/hatch_build.py` writes; `publish-api-to-pypi` uploads them through trusted publishing in the same `pypi` environment, only after `publish-to-pypi` has put the `pipelex` they pin on PyPI.
- **Docker Hub: `pipelex/pipelex-api:X.Y.Z`, and `latest`.** The `publish-docker-hub` job calls `.github/workflows/publish-docker-hub.yml` after `github-release`: it refuses a commit the `vX.Y.Z` tag does not name, runs `make -C api deploy-docker-hub` from the release commit (build for `linux/amd64` from the repository root, smoke-test that the image boots and reports X.Y.Z for the server and its pipelex, push the version tag, and `latest` for a stable version), confirms both tags through Docker Hub's tags API, and pushes `api/README.md` as the Docker Hub overview. A pre-release pushes its own tag and leaves `latest` alone.
- **The GitHub Release and the `vX.Y.Z` tag.** The same workflow's `github-release` job creates them, and the tag exists only as a side effect of `gh release create`. The release is created and the dists attached *before* Sigstore signing, which is allowed to fail: an unsigned release is reported as a warning, not a failure, because the tag is the record of what shipped.
- **The documentation site.** `.github/workflows/deploy-docs.yml` fires on the push to `main` and runs `make docs-deploy-stable`, which deploys the version read from `pyproject.toml` with the `latest` alias and republishes the root sitemap. The API server's pages are part of it, under `api-server/`, with the OpenAPI artifact beside them.

The landing verifies the publish from the run, the registries and the tag:

```bash
gh run list --workflow=publish-pypi.yml --branch release/vX.Y.Z --limit 3 --json name,conclusion,headSha,event,url   # success
pip index versions pipelex                                          # the registry answers X.Y.Z
pip index versions pipelex-api                                      # the registry answers X.Y.Z
curl -fsS https://hub.docker.com/v2/namespaces/pipelex/repositories/pipelex-api/tags/X.Y.Z | jq -r .digest   # Docker Hub serves the tag
curl -fsS https://hub.docker.com/v2/namespaces/pipelex/repositories/pipelex-api/tags/latest | jq -r .digest   # the same digest, for a stable version
git -C <main> fetch --tags --prune origin && git -C <main> tag --list vX.Y.Z
```

The run concludes `success` only when every job did, the image's included, so a green run already says all three artifacts shipped; the registry answers are what confirms it from the outside. `docker manifest inspect pipelex/pipelex-api:X.Y.Z` is the other way to read the image tag.

`gh release view vX.Y.Z` confirms the Release and its notes. A publish that failed *after* the merge is recovered by **re-running that run's failed jobs**, which keeps the successful ones, and that is the path to reach for. It is safe once the dists have reached PyPI: `skip-existing` opens on a re-run and on a dispatch, so the publish job no longer dies on the files already there, and the build job recovers the bytes this version published rather than rebuilding them — the artifact an attempt of the same run stored, else one an earlier run stored for the same commit, else the files PyPI serves — then refuses to go on unless what it holds is byte-for-byte what PyPI publishes. The Release step itself is idempotent: it edits an existing release rather than failing on one.

The same goes for the server's two artifacts. A failed `publish-api-to-pypi` is re-run on its own, from the build its run stored. A failed `publish-docker-hub` is re-run on its own too: pushing a tag again is harmless, and the tag check passes because the release is already tagged. When that failure needs a change to a workflow file, dispatch `publish-docker-hub.yml` alone, `gh workflow run publish-docker-hub.yml --ref main`, which publishes the image of `main`'s head and so works while that head is the commit the release is tagged at; it refuses any other commit. Docker Hub's tags API then confirms the push, as above. The overview step is allowed to fail: a warning in the run says so, usually because the token lacks the read/write/delete scope, and the cure is that scope and a re-run of the job, or pasting `api/README.md` into the overview on Docker Hub.

`workflow_dispatch` of `publish-pypi.yml` is the other path, needed when the failure calls for a change to the workflow file, since a re-run replays the file the run started with. **Once the release exists, a dispatch succeeds only from a ref whose head is the commit the release is tagged at** — the release pull request's base branch, `main` normally, while nothing further has landed on it. The tag names the merge commit, a dispatch ships the head of the ref it was dispatched from, and `github-release`'s tag guard refuses any other commit: a dispatch from `release/vX.Y.Z` is therefore always refused, although it is the ref the failed run is listed under. That dispatch recovers from PyPI rather than from an artifact, the release branch's build being keyed to a different commit, and the bytes are the same either way. A dispatch accepts `main`, `release/vX.Y.Z` and `pre-release/v*` and nothing else, and its run lists under the ref it was dispatched from rather than under the release branch.

## Version files and the lock

- **`pyproject.toml`** — the `[project]` table's `version`, the one and only place the number is written. Nothing in the package restates it: the runtime reads it back through `get_package_version()`. Keep it the file's **first** `version = ` line: `changelog-check.yml` and `publish-pypi.yml` both read it with `grep -m 1 'version = '`, and `version-check.yml` with `grep '^version'`.
- **The lock** — `make li` (lock + install) regenerates `uv.lock`. Stop and report if it fails; `uv-lock-check` in CI fails the pull request over a stale lock.
- **Also stamped:**
  - **`.badges/tests.json`** — set `"message"` to what `make test-count` prints, leaving every other field alone, then run `make check-test-badge` to confirm the two agree. A mismatch is a CI failure on the pull request.
  - **`docs/api-server/openapi/pipelex-api.openapi.yaml`** — `make -C api openapi-export`. The API server in `api/` takes the library's version, and its committed OpenAPI artifact carries it as `info.version`, so the bump moves the artifact and `make agent-check`, whose `api-agent-check` runs `openapi-check`, fails until it is re-exported. The only change it should show is that one line; anything more is a wire change that belongs in the changelog.
  - **`.test_durations`** — `make store-test-durations`, the per-test timing map `pytest-split` uses to balance the CI test shards. The refresh is incremental: it collects the suite and measures only the tests missing from the map, so it takes seconds on a quiet release and writes no diff at all when nothing was missing. Read the coverage line it prints before judging how long it should take — past roughly 40% of the suite missing it falls back to re-measuring everything, which takes minutes; treat a long run as a hang only when it reported few tests missing. Include the file in the commit only when it changed. `make store-test-durations-force` is **not** part of the release flow; it is for when recorded values are no longer comparable to each other because the machine or the suite changed shape. The rationale is `docs/contribute/test-duration-map.md`.
  - **`pipelex/migration/ledgers/*.toml` and `pipelex/migration/goldens/`** — only when the migration gate below finds an unaccounted schema change, and then written by the `add-migration` skill, never by hand.

## Gates

1. **`make agent-check`** — format, lint, pyright, mypy, plus the migration-ledger legality check, the keyword-only convention, the hub-layering check and the drift contracts. It **rewrites files** (`fix-unused-imports`, `fix-keyword-only`, `format`), so whatever it touched joins the release commit — and its `drift-check` reads the git index, so a rewrite made in the same run is invisible to it: stage what the fixers changed and run the target again, because CI reads the committed tree. Red blocks the release: fix the errors, never skip the target.
2. **`make check-migration-schemas`** — the schema-coverage gate, which `make agent-check` does **not** run (it is a golden check and lives in `make check`), so without this step a moved configuration surface reaches a release with no migration to repair a user's file. Red blocks the release, and the cure is the **`add-migration`** skill: it derives the entry from the fingerprint diff the gate just printed, bumps the surface's schema version, regenerates the goldens and adds the changelog bullet. Then re-run the gate. Never run `make up-migration-schemas` to make it quiet — a green gate over an unaccounted removal is precisely the failure the gate exists to prevent.
3. **The ledger-against-changelog cross-check**, once the gate is green. Diff the ledgers against the tag of the version the pre-flight read — the previous release. `origin/main` is not a safe baseline, and from `main` itself that diff is empty:

   ```bash
   git diff v<current version> -- pipelex/migration/ledgers/
   ```

   The migration ledger and the changelog are deliberately separate artifacts saying the same thing to different readers, and this is the only place they are checked against each other. For every entry new since that release carrying `breaking = true`, confirm the changelog has a matching `**Migration:**` bullet naming the entry id and what a user has to do — house style is a bold label, then two to four complete sentences. Write it now if it is missing; the gates run before the entry is assembled, so at this point that content is what `[Unreleased]` holds.

   - **A renumbered entry reads as two ids, and both need a mention.** A pre-history entry inserted below existing ones takes a version already in use and pushes everything above it up, so the diff shows one id modified and one added — which looks like two independent breaking changes and is one insertion. The changelog must name the new entry *and* say that the existing one was renumbered, so a reader who quoted the old id somewhere can still find it.
   - **Confirm `introduced_in` on every such entry.** It is written when the entry is authored, before the release number is known, so it is routinely one bump off. Nothing branches on it, but it is what a reader correlates the changelog against: fix it here rather than leaving it wrong.
   - **A breaking ledger entry makes this a minor release**, per the pre-1.0 convention. If the bump was settled as a patch and this step finds one, go back and settle the bump again before writing the version into the entry.

   Full context: `docs/migration-ledger.md`.

## The release commit

`pyproject.toml`, `CHANGELOG.md`, `uv.lock`, `.badges/tests.json`, `docs/api-server/openapi/pipelex-api.openapi.yaml`, `.test_durations` when `make store-test-durations` changed it, whatever `make agent-check` rewrote, and the `pipelex/migration/ledgers/*.toml` and `pipelex/migration/goldens/` files the `add-migration` skill wrote when it ran. By name.

## CI on the release pull request

The checks that exist for the release:

- **`guard-branches.yml`** (`gate-main`) — refuses any head branch into `main` that is not `release/vX.Y.Z` exactly, so the release branch name is the only way in.
- **`version-check.yml`** — `pyproject.toml`'s version equals the version in the branch name. A head that does not match the release form does not slip past it: the `exit 0` in its first step ends that step alone, and the comparison that follows then fails on an empty branch version.
- **`changelog-check.yml`** — `CHANGELOG.md` carries `## [vX.Y.Z] - ` for the version in `pyproject.toml`. It asserts nothing about `[Unreleased]`: a leftover heading passes CI and ships a wrong changelog, so removing it is this skill's job, not CI's.
- **`check-test-count-badge.yml`** — `make check-test-badge` on every pull request to `main`.
- **`package-check.yml`** (`uv-lock-check`, on every pull request) — `uv lock --locked` leaves `uv.lock` unchanged, and `requires-python` still starts at `>=3.11`.

The pre-main gates a release pull request meets that a pull request to `dev` never does — they are slower, and a red here is the release stopping:

- **`lint-fresh-check.yml`** — the read-only lint suite across every supported Python version with no mypy cache, so incremental-mypy drift and version-specific breakage cannot reach `main`. Each version's leg checks the API server too.
- **`tests-full-check.yml`** — the full Python matrix, sharded and balanced by `.test_durations`, and the API server's tests on every supported version (`Tests full (api, pyX)`).
- **`doc-check.yml`** — `mkdocs build --strict`, which runs unconditionally when the base is `main` rather than only when `docs/` changed.

Everything that runs on every pull request gates it too, including the server's `Lint (api)`, `Tests (api)`, `Tests (packages)`, which builds both packages and checks the `pipelex-api` pin, and `Tests (api image)`, which builds and smoke-tests the image, and `lint-check.yml`'s `Lint (agent-rules)` and `Lint (config-sync)` jobs (`make check-rules` and `make check-config-sync`, neither of which `make agent-check` runs), `tests-check.yml`, `mthds-standard-check.yml`, and `dependency-review.yml`, which fails on a newly introduced dependency vulnerable at moderate severity or above and runs on pull requests to `dev` just the same. A red in `mthds-standard-check.yml` with no pinned-set change in the branch means the MTHDS standard moved, and the remedy is a dedicated change bringing the pinned natives to the standard's page — never a tweak to the release branch.

## Particulars

- **The first release that ships the server explains the image's version jump.** The `pipelex/pipelex-api` image was released on its own until `0.33.2`, from the `Pipelex/pipelex-api` repository; its next tag is this release's version. `[Unreleased]` already says so in its `The Pipelex API server ships with pipelex` entry: keep that sentence when folding the entry, and say it in the pull request body. Releases after that one need no such note.
- **A server change is an entry in this changelog.** `api/CHANGELOG.md` stops at `0.33.2` and is never extended.
- **The migration gate feeds back into the bump.** A breaking entry found by the cross-check above turns a patch into a minor, so the bump is not final until that gate has run.
- **The pre-release track is a different flow, not this play.** `pre-release/vX.Y.Z(a|b|rc)N` is a *base* branch that work merges into: `prerelease-version-check.yml` validates the PEP 440 form against the branch name, `publish-pypi.yml` also fires on a merge into it, marks the GitHub Release a pre-release and publishes the server's wheel and image as well, the image under its own tag with `latest` left on the last stable release, and `deploy-docs.yml` fires on the push to it as well — though its pre-release branch calls `make docs-deploy-specific-version`, a name with no recipe behind it (the recipe is `docs-deploy-specific-version-pre-release`), so that step succeeds and publishes nothing. A `release/vX.Y.Z` branch therefore never carries a pre-release version: `version-check.yml` fails on the mismatch with the branch name, and `guard-branches.yml` refuses a `release/vX.Y.Z(a|b|rc)N` head into `main` outright.
- **The changelog heading carries the `v`** — `## [vX.Y.Z] - YYYY-MM-DD`, which is exactly what `changelog-check.yml` greps for and what `publish-pypi.yml` slices the GitHub Release notes out of. No `[Unreleased]` heading is left behind; the next change re-creates one.
- **`.worktreeinclude` names the gitignored files a fresh worktree needs** — `.env`, the `.pipelex/` overrides and `.pipelex-dev/test_profiles_override.toml` — and `wt add` provisions them. A gate that fails in `_pipelex--release` on a missing local config means that file is short: add it there rather than hand-copying the file every release.
