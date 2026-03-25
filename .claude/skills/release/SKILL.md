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

### 9. Commit and push

Stage all release-related changes. This includes at minimum `pyproject.toml`,
`CHANGELOG.md`, `uv.lock`, and `.badges/tests.json`, plus any other files the
user chose to include in step 1 (e.g. previously uncommitted work that belongs
in this release).

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
- The CI will validate that:
  - The `pyproject.toml` version matches the branch name (`version-check.yml`)
  - The `CHANGELOG.md` has an entry for the version (`changelog-check.yml`)
  - The `.badges/tests.json` count matches the actual test count (`check-test-badge`)
  - The `uv.lock` file is in sync with `pyproject.toml` (`uv-lock-check`)
- All checks must pass for the PR to be mergeable, so getting the changelog,
  version, test badge, and lockfile right is critical.
- Today's date for the changelog entry: use the current date in `YYYY-MM-DD`
  format.
