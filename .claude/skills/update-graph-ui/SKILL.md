---
name: update-graph-ui
description: >
  Update the mthds-ui graph viewer assets in pipelex to a new version.
  Bumps the version tag in package.json, runs make sync-graph-ui to rebuild
  and copy the standalone JS/CSS assets, verifies the sync and runs tests.
  Use when user says "update graph ui", "bump mthds-ui", "sync graph viewer",
  "update graph viewer", "new version of mthds-ui", or any variation of
  updating the vendored graph viewer assets.
user_invocable: true
---

# Update Graph UI Assets

Update the vendored mthds-ui graph viewer assets in pipelex to a new version.

## Prerequisites

- `node` and `npm` must be on PATH
- Git access to `github.com/Pipelex/mthds-ui`

## Workflow

### 1. Check current state

```bash
grep '@pipelex/mthds-ui' package.json
cat pipelex/graph/reactflow/assets/.graph-ui-version
```

Report the currently pinned version and the currently synced version.

### 2. Determine target version

Ask the user which version to update to, or check the latest tag:

```bash
git ls-remote --tags https://github.com/Pipelex/mthds-ui.git | grep -o 'refs/tags/v[0-9.]*' | sed 's|refs/tags/v||' | sort -V | tail -1
```

Show the user the latest available version and ask for confirmation.

### 3. Update package.json

Edit `package.json` to change the version tag and update the pinned SHA:

```bash
git ls-remote https://github.com/Pipelex/mthds-ui.git refs/tags/v<NEW_VERSION> refs/tags/v<NEW_VERSION>^{}
```

If two lines appear (annotated tag), use the `^{}` dereferenced SHA (the commit).
If one line appears (lightweight tag), use that SHA directly.
Update both fields:

```json
"dependencies": {
  "@pipelex/mthds-ui": "github:Pipelex/mthds-ui#v<NEW_VERSION>"
},
"//dependencies": {
  "@pipelex/mthds-ui": "v<NEW_VERSION> = <COMMIT_SHA>"
}
```

### 4. Sync assets

```bash
make sync-graph-ui
```

This clones mthds-ui at the pinned tag, builds the standalone JS/CSS bundles,
and copies them to `pipelex/graph/reactflow/assets/`.

If this fails, stop and report the error. Common issues:
- Tag doesn't exist on the remote (check available tags)
- npm install failure (network issue)
- Build failure (mthds-ui build broken at that tag)

### 5. Verify sync

```bash
make check-graph-ui-sync
```

Must print "up-to-date". If not, something went wrong in step 4.

### 6. Run graph tests

```bash
.venv/bin/pytest tests/unit/pipelex/graph/test_reactflow_html.py -v --no-header
```

All tests must pass. These verify:
- HTML generation with embedded GraphSpec
- Bundled JS/CSS is present
- Config JSON embedding
- HTML structure validity

### 7. Run full quality checks

```bash
make agent-check
```

Ensures the new assets don't break lint, type checking, or any other checks.

### 8. Report

Tell the user:
- Previous version and new version
- Asset sizes (JS + CSS)
- Test results
- Remind to commit: `package.json`, `graph-viewer.js`, `graph-viewer.css`, `.graph-ui-version`
