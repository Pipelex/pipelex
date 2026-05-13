---
name: update-graph-ui
description: >
  Bump the pinned `@pipelex/mthds-ui` (and `elkjs`) version that the generated
  ReactFlow HTML loads from jsDelivr. Re-fetches the bundle, recomputes SRI
  hashes, and updates the Python constants in `standalone_assets.py`.
  Use when user says "update graph ui", "bump mthds-ui", "update graph viewer",
  "new version of mthds-ui", or any variation of updating the CDN-pinned graph
  viewer assets.
user_invocable: true
---

# Update Graph UI Assets (CDN + SRI)

Bump the pinned `@pipelex/mthds-ui` version that the generated ReactFlow HTML
loads from `cdn.jsdelivr.net`, refresh the Subresource Integrity hashes, and
verify everything still renders.

There is no vendored bundle anymore. Assets are loaded from jsDelivr at view
time; the only things stored in this repo are the version strings and the
matching `sha384` SRI hashes in
`pipelex/graph/reactflow/standalone_assets.py`.

## Prerequisites

- `curl` and `openssl` on PATH (used by the refresh command and the sanity
  check below).
- The target `@pipelex/mthds-ui` version must already be published on npm
  **with `dist/standalone/graph-viewer.{js,css}` in the tarball**. If it
  isn't, jsDelivr will 404 — fix the publish in the `mthds-ui` repo first.

## Workflow

### 1. Check current pin

```bash
grep -E 'MTHDS_UI_VERSION|ELKJS_VERSION' pipelex/graph/reactflow/standalone_assets.py
```

Report the currently pinned versions.

### 2. Pick the target version

Latest published version on npm:

```bash
npm view @pipelex/mthds-ui version
```

Confirm with the user.

### 3. Verify the target is reachable on jsDelivr

```bash
curl -fsI https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@<NEW_VERSION>/dist/standalone/graph-viewer.js
curl -fsI https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@<NEW_VERSION>/dist/standalone/graph-viewer.css
```

Both must return `HTTP/2 200`. If either 404s, the npm publish for that
version did not include the standalone bundle — stop and ask the maintainer
to re-publish properly before proceeding.

### 4. Refresh the SRI hashes

```bash
.venv/bin/pipelex-dev refresh-graph-ui-sri --mthds-ui-version <NEW_VERSION>
```

This re-fetches each URL, computes `sha384`, and rewrites the constants in
`pipelex/graph/reactflow/standalone_assets.py`.

To rotate `elkjs` at the same time, pass `--elkjs-version <NEW_ELKJS_VERSION>`.

### 5. Run graph tests

```bash
.venv/bin/pytest tests/unit/pipelex/graph/reactflow tests/unit/pipelex/graph/test_reactflow_html.py -q
```

All tests must pass. These verify:

- CDN constants are well-formed (`sha384-…` decoding to 48 bytes, URLs pinned to declared versions).
- Generated HTML references `cdn.jsdelivr.net` with the new integrity hashes.
- HTML structure (DOCTYPE, root div, embedded JSON data scripts) is intact.

### 6. Run full quality checks

```bash
make agent-check
```

### 7. Smoke test the rendered HTML (recommended)

Generate one graph and open it in a browser:

```bash
make serve-graph
```

In DevTools → Network, confirm three external requests to `cdn.jsdelivr.net`
succeed with no `Failed to find a valid digest in the 'integrity' attribute`
errors in the console.

### 8. Report

Tell the user:

- Previous and new versions for `mthds-ui` (and `elkjs` if bumped).
- New SRI hashes.
- Test results.
- Remind to commit `pipelex/graph/reactflow/standalone_assets.py` and any
  CHANGELOG entry.
