---
name: release
description: >
  Automates the Pipelex release workflow: bumps the version in pyproject.toml,
  finalizes the CHANGELOG.md Unreleased section, runs quality checks, creates a
  release/vX.Y.Z branch, commits, pushes, and opens a PR to main. Use when user
  says "release", "cut a release", "bump version", "prepare a release", "make a
  release", "ship it", "create release branch", or any variation of shipping a
  new version of pipelex. The user can optionally provide changelog content
  inline when invoking the skill (e.g. "/release Added new extract backend"),
  which will be used as the changelog entry for this version.
---

# Pipelex Release Workflow

This skill handles the full release cycle for the `pipelex` Python package.

## Files touched

- **`pyproject.toml`** — the `version` field (line 3)
- **`CHANGELOG.md`** — add `[vX.Y.Z] - YYYY-MM-DD` entry (remove `[Unreleased]` if present)
- **`uv.lock`** — regenerated via `make li` (lock + install)
- **`.badges/tests.json`** — test count updated to match actual count
- **`.test_durations`** — regenerated via `make store-test-durations` so the CI test shards stay balanced (see step 8b)
- **`pipelex/migration/ledgers/*.toml`** and **`pipelex/migration/goldens/`** — only when step 3b finds an unaccounted schema change; written by the `add-migration` skill, never by hand

## Workflow

### 1. Pre-flight checks

- Read the current version from `pyproject.toml`.
- Read `CHANGELOG.md` to understand the current state.
- Run `git status` and `git log origin/main..HEAD` to assess the working tree:
  - If there are **uncommitted changes** (staged or unstaged), warn the user and
    ask whether to commit them as part of the release, stash them, or abort.
  - If there are **unpushed commits** on the current branch, list them so the
    user is aware — these will be included in the release branch.

### 2. Determine the bump type

Ask the user which kind of version bump they want — **patch**, **minor**, or
**major** — unless they already specified it. Show the current version and what
the new version would be for each option so the choice is concrete.

### 3. Run quality checks

Run `make agent-check`. This is the gate — if it fails, stop and report the
errors so they can be fixed before retrying. Do not proceed past this step on
failure.

### 3b. Ledger completeness

`make agent-check` does not run the coverage gate — it is a golden check and lives
in `make check` only — so a schema change that has not been accounted for reaches
here unseen. This step is what makes it impossible for a release to ship a moved
configuration schema without the migration that repairs a user's file.

Run:

```bash
make check-migration-schemas
```

- **If it fails**, the release is blocked. Invoke the **`add-migration`** skill: it
  derives the entry from the fingerprint diff the gate just printed, bumps the
  surface's schema version, regenerates the goldens and adds the changelog bullet.
  Then re-run this step. Do not proceed on a red gate, and do not regenerate the
  goldens to make it quiet — a green gate over an unaccounted removal is exactly
  the failure the gate exists to prevent.
- **If it passes**, check whether any schema version moved in this release. Diff
    the ledgers against the tag of the version read in step 1 — the previous
    release, whichever branch the skill was invoked from (`origin/main` is not a
    safe baseline: from `main` itself that diff is empty):

    ```bash
    git diff v<current version> -- pipelex/migration/ledgers/
    ```

    For each entry that is new since that release and carries `breaking = true`, confirm
    the changelog carries a matching `**Migration:**` bullet naming the entry id and
    what a user has to do. The ledger and the changelog are deliberately separate
    artifacts saying the same thing to different readers, and this is the only place
    they are checked against each other — if the bullet is missing, write it now
    (house style: bold label, then two to four complete sentences).

    **A renumbered entry shows up in that diff as two ids, and both need a mention.**
    A pre-history entry inserted below existing ones takes a version already in use
    and pushes everything above it up, so the diff reads as one id modified and one
    added — which looks like two independent breaking changes and is one insertion.
    Do not treat the pushed-up id as an unbullet-ed new entry: the changelog must
    name the new entry *and* say that the existing one was renumbered, so a reader
    who quoted the old id somewhere can find it. Confirm `introduced_in` on both.

    **A breaking ledger entry makes this a minor release**, per the house
    convention — if step 2 chose a patch bump and this step found one, go back and
    settle the bump first, because the next check writes the new version into the
    entry.

    Then confirm each such entry's `introduced_in` matches the version being cut.
    It is written when the entry is authored, before the release number is known, so
    it is routinely one bump off. Nothing branches on it, but it is what a reader
    correlates the changelog against, so fix it here rather than leaving it wrong.

### 4. Ensure we're on the right branch

The release branch must be named `release/vX.Y.Z` where X.Y.Z is the **new**
version. All file modifications (changelog, version bump, lock, badge) must
happen on this branch.

- If already on `release/vX.Y.Z` matching the new version, stay on it.
- If on `dev`, `main`, or any other branch, create and switch to
  `release/vX.Y.Z` from the current HEAD.
- If on a `release/` branch for a **different** version, warn the user and ask
  how to proceed.

### 5. Finalize the changelog

Add a new version entry at the top of the changelog for the release.

1. If there is an `## [Unreleased]` section, **remove it** (including any blank
   lines that follow it) and replace it with the new version heading. Any
   content that was under `[Unreleased]` becomes the content of the new version.
2. If there is no `[Unreleased]` section, insert the new version heading
   directly after the `# Changelog` title.
3. **Never add an `[Unreleased]` heading.** The changelog should only contain
   concrete version entries.
4. If the user provided changelog content when invoking the skill (e.g.
   `/release Added new extract backend`), **merge** that content with any
   existing `[Unreleased]` content (do not discard either source). Format the
   combined content properly under the appropriate headings (e.g. `### Added`,
   `### Changed`, `### Fixed`), inferring headings from the content when
   possible.
5. If the release has no changelog content yet (neither from an `[Unreleased]`
   section nor from inline user input), ask the user what to include before
   proceeding.
6. The result should look like:

```markdown
# Changelog

## [vX.Y.Z] - YYYY-MM-DD

### Changed
- ...

## [vPREVIOUS] - PREVIOUS-DATE
...
```

### 6. Bump the version in pyproject.toml

Edit `pyproject.toml` line 3 to the new version string. Only change the version
field — don't touch anything else.

### 7. Lock dependencies

Run `make li` to regenerate `uv.lock` and reinstall. This ensures the lockfile
reflects the new version in `pyproject.toml`. If this step fails, stop and
report the error.

### 8. Update the test count badge

Run `make test-count` to get the current number of tests. Then update
`.badges/tests.json` — set the `"message"` field to the count returned by
`make test-count`. Keep all other fields unchanged.

After updating, run `make check-test-badge` to verify the badge matches. If it
fails, re-check the count and fix the badge file.

### 8b. Refresh the test-duration map

Run `make store-test-durations`. This runs the full test suite once and rewrites
`.test_durations`, the per-test timing file `pytest-split` uses to balance the 8
CI test shards on feature PRs. It drifts as tests are added or removed, and a
stale file silently unbalances the shards (some finish in seconds, one runs
long), so a release is the natural point to refresh it.

- This runs the whole suite, so it takes a few minutes — expected, not a hang.
- If it changed the file, `.test_durations` is included in the release commit
  (step 9). If the suite hasn't changed since the last release it may be a
  no-op, which is fine — commit it if git shows a diff, skip if not.

### 9. Commit and push

Stage all release-related changes. This includes at minimum `pyproject.toml`,
`CHANGELOG.md`, `uv.lock`, and `.badges/tests.json`, plus `.test_durations` if
step 8b changed it, plus any other files the user chose to include in step 1
(e.g. previously uncommitted work that belongs in this release).

Commit with the message:

```
Release vX.Y.Z
```

Push the branch to origin with `-u` to set up tracking.

### 10. Open a PR

Create a pull request targeting `main` with:

- **Title:** `Release vX.Y.Z`
- **Body:** Include:
  - The changelog entries for this version (copied from CHANGELOG.md)
  - A note about the version bump from old to new

Use this format for the PR body:

```markdown
## Release vX.Y.Z

Bumps version from `A.B.C` to `X.Y.Z`.

### Changelog

<paste the changelog entries for this version here>
```

Report the PR URL back to the user.

## Important details

- The version follows semver: `MAJOR.MINOR.PATCH`.
- Always confirm the bump type with the user before making changes.
- If `make agent-check` fails, the release is blocked — help the user fix the
  issues rather than skipping the checks.
- If `make check-migration-schemas` fails (step 3b), the release is blocked too,
  and the fix is an entry written by the `add-migration` skill — never a golden
  regeneration that makes the gate quiet.
- The CI will validate that:
  - The `pyproject.toml` version matches the branch name (`version-check.yml`)
  - The `CHANGELOG.md` has an entry for the version (`changelog-check.yml`)
  - The `.badges/tests.json` count matches the actual test count (`check-test-badge`)
  - The `uv.lock` file is in sync with `pyproject.toml` (`uv-lock-check`)
- All checks must pass for the PR to be mergeable, so getting the changelog,
  version, test badge, and lockfile right is critical.
- Today's date for the changelog entry: use the current date in `YYYY-MM-DD`
  format.
