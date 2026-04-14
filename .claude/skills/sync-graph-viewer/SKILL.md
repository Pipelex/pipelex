---
name: sync-graph-viewer
description: >
  Rebuilds the standalone React Flow graph-viewer bundle from the sibling
  `mthds-ui/` repo and syncs it into pipelex's embedded assets at
  `pipelex/graph/reactflow/assets/graph-viewer.{js,css}`. Use when the user
  says "sync graph viewer", "update graph viewer", "rebuild mthds-ui bundle",
  "refresh reactflow viewer", "update the detail panel", "pull a new mthds-ui
  version into pipelex", or any variation of pulling a fresh mthds-ui
  standalone build into pipelex. Also use whenever the user wants a change
  made to the React Flow viewer that can only be fixed upstream in `mthds-ui`
  (since pipelex's copies of `graph-viewer.js` / `graph-viewer.css` are
  generated artifacts that must never be hand-edited).
---

# Pipelex Graph Viewer Sync Workflow

This skill rebuilds the standalone `@pipelex/mthds-ui` bundle from its source
in the sibling `mthds-ui/` repo and syncs the resulting JS + CSS into pipelex.

## Background

Pipelex's standalone React Flow HTML viewer (used by `make view-graph`,
`make serve-graph`, and by any code that generates a standalone graph HTML)
embeds a prebuilt JS+CSS bundle:

- `pipelex/graph/reactflow/assets/graph-viewer.js`
- `pipelex/graph/reactflow/assets/graph-viewer.css`

These two files are loaded by `pipelex/graph/reactflow/standalone_assets.py`
and inlined into the Jinja template
`pipelex/graph/reactflow/templates/reactflow.html.jinja2`.

They are **generated artifacts** produced by the sibling repo `../mthds-ui`
via `npm run build:standalone`. They must never be hand-edited — any change
must be made in `mthds-ui` source, then re-synced with this workflow.

A Makefile target `make sync-graph-viewer` (alias `make sgv`) already handles
the mechanical rebuild+copy. This skill wraps that target with the checks and
confirmations that should happen around it.

## Files touched

- **`pipelex/graph/reactflow/assets/graph-viewer.js`** — regenerated bundle
- **`pipelex/graph/reactflow/assets/graph-viewer.css`** — regenerated bundle
- **`pipelex/CHANGELOG.md`** — single bullet under the existing
  `[Unreleased]` section. Never promote it to a versioned entry.

Files inside `../mthds-ui/` are only touched as side effects of `npm install`
and `npm run build:standalone` — never directly by this skill.

## Workflow

### 1. Pre-flight: workspace layout

Confirm `../mthds-ui` exists as a sibling of the pipelex repo (workspace
layout convention from the top-level `CLAUDE.md` — all repos are siblings
under one parent directory).

```bash
test -d ../mthds-ui
```

If missing, tell the user to clone `mthds-ui` next to `pipelex` and stop.
Do not try to install or fetch it yourself.

### 2. Inspect mthds-ui git state

Before triggering a rebuild, make sure we know what upstream code is about
to be compiled in.

```bash
git -C ../mthds-ui status
git -C ../mthds-ui log -1 --oneline
git -C ../mthds-ui branch --show-current
```

Immediately surface:

- The current branch.
- The last commit (short hash + subject).
- Whether the working tree is clean.

If the tree is **dirty**, or the branch isn't the one the user expected
(for example they expected `main` but it's on a feature branch), ask the
user whether to proceed. We do not want to silently ship uncommitted
upstream work into pipelex.

### 3. Check the node toolchain

Verify `node` and `npm` are on `PATH`:

```bash
node --version
npm --version
```

If `../mthds-ui/node_modules` is missing, mention that `npm install` will
run automatically as part of the make target (no need to pre-run it).

### 4. Run the sync

From the pipelex repo root:

```bash
make sync-graph-viewer
```

Stream the output. This target will:

1. Run `npm install` in `mthds-ui/` if `node_modules` is missing.
2. Run `npm run build:standalone` in `mthds-ui/` to regenerate
   `mthds-ui/dist/standalone/graph-viewer.{js,css}`.
3. Copy those two files into `pipelex/graph/reactflow/assets/`.

If the target fails (missing sibling repo, npm install error, build error,
missing output files), stop and surface the exact error to the user. Do
not hand-roll a workaround that edits the assets directly.

### 5. Post-sync sanity checks

After each command below, immediately report the result in text — the user
shouldn't have to dig through silent tool output to know what happened.

Show exactly which bytes changed:

```bash
git -C . diff --stat pipelex/graph/reactflow/assets/
```

If the user was syncing to pick up a specific upstream feature, spot-check
for a class or symbol they care about. For example, if the upstream change
was the draggable detail panel:

```bash
grep -c detail-panel-resize-handle pipelex/graph/reactflow/assets/graph-viewer.css
grep -c detail-panel-resize-handle pipelex/graph/reactflow/assets/graph-viewer.js
```

Both should return a non-zero count. Adapt the grep target to whatever the
user was syncing for — do not hardcode a single class name across
invocations.

### 6. Scan the diff for surprises

Run a fuller diff and read it:

```bash
git -C . diff pipelex/graph/reactflow/assets/
```

Skim the summary of what changed. If the sync pulled in changes unrelated to
what the user asked for (other refactors, unrelated class renames, package
updates), flag them and ask the user whether to:

- **Proceed** — accept the full upstream delta.
- **Split** — keep only the intended change (usually means going back to
  `mthds-ui` to land a narrower upstream change first, then re-syncing).
- **Hold** — revert the sync with `git checkout -- pipelex/graph/reactflow/assets/`
  and come back later.

### 7. Manual visual verification

The asset bundle cannot be fully verified automatically — the UI must be
looked at. Suggest:

```bash
make view-graph
```

(or `make serve-graph` if the user wants to keep the server running) and
tell the user to click through a node, exercise the feature they were
syncing for, and confirm it behaves as expected. Document this as a
**manual** step, not an automated check.

### 8. Update CHANGELOG.md

Append a single bullet under the existing `## [Unreleased]` section in
`pipelex/CHANGELOG.md` describing what upstream change was pulled in. For
example:

```markdown
## [Unreleased]

### Changed
- Detail panel in the standalone React Flow viewer is now draggable to
  resize (synced from mthds-ui).
```

Rules:

- Keep the entry under `[Unreleased]`. **Never** promote it to a versioned
  `[vX.Y.Z] - YYYY-MM-DD` heading — that happens at release time, in the
  separate `release` skill.
- If `[Unreleased]` doesn't exist, create it directly below the `# Changelog`
  title.
- Do not hardcode counts (e.g. "fixes 3 bugs") — they go stale.
- Write the entry from the user's perspective, not pipelex-internal
  terminology. "Detail panel is now resizable" is better than "bumped
  mthds-ui dist bundle".

### 9. Lint

Run quality checks from the pipelex repo:

```bash
make agent-check
```

This is silent on success. On failure, surface the error and help the
user fix it before proceeding. No Python source is touched by this
workflow, but `agent-check` also catches issues with the Makefile edits
and other derived artifacts.

### 10. Summarize and hand off

Print a short summary of what changed:

- The two asset files (with line-count delta from step 5).
- The `CHANGELOG.md` entry that was added.
- The upstream commit that was compiled in (from step 2).

Then suggest the user run `/commit-commands:commit` when they're ready to commit the
changes. **Do not create commits, push branches, or open PRs on the user's
behalf** unless they explicitly ask for it.

## Important details

- **Never hand-edit** `pipelex/graph/reactflow/assets/graph-viewer.js` or
  `graph-viewer.css`. They are generated artifacts. Any change must be
  made in `mthds-ui` source first and then re-synced through this skill.
- **Never modify files inside `mthds-ui/`** from this skill except as a
  side effect of `npm install` and `npm run build:standalone`. If upstream
  source needs editing, make that a separate, explicit step the user drives
  (ideally in a different Claude session working inside the `mthds-ui`
  repo), then come back and run this skill.
- **Never promote** the `[Unreleased]` CHANGELOG heading to a versioned
  release heading. That is exclusively the `release` skill's job.
- If `make sync-graph-viewer` is missing from the pipelex `Makefile`, stop
  and tell the user — don't reimplement the rebuild+copy inline.
- If the user just wants to visually smoke-test an existing sync without
  rebuilding, they should run `make view-graph` directly. This skill is for
  the rebuild+sync flow, not for serving existing assets.
