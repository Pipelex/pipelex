# Switch graph viewer assets from vendored bundle to jsDelivr + SRI

## Goal

Stop vendoring `mthds-ui`'s `graph-viewer.{js,css}` into the Pipelex package and stop inlining them into every generated HTML. Instead, reference both `@pipelex/mthds-ui` and `elkjs` from `cdn.jsdelivr.net` with pinned versions and Subresource Integrity (`sha384` + `crossorigin="anonymous"`). Drop the `make sync-graph-ui` pipeline and the committed bundle files. The generated HTML stays reproducible (pinned URL + SRI) and tamper-evident, with no maintainer toolchain step.

## Why

- The current "self-contained HTML" claim is cosmetic: `elkjs` already loads from `unpkg.com/elkjs@0.11.1`, so the HTML never actually rendered offline. We pay the vendoring cost (`make sync-graph-ui`, committed ~2 MB of built JS+CSS, diff churn on every bump — cf. commit `43b758ce`) without getting the benefit it was supposed to buy.
- `@pipelex/mthds-ui` is now published on npm, so a public CDN URL pattern is available.
- SRI hashes recover the integrity property a hand-bundled inline `<script>` gives "for free" — a CDN compromise can't silently swap the bundle.
- jsDelivr is multi-CDN backed (Cloudflare + Fastly + StackPath) and publishes SRI hashes on its package pages — operationally simpler than unpkg for this design.

## Approach

- Three external assets, each pinned by version and locked by SRI:
    - `https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@<MTHDS_UI_VERSION>/dist/standalone/graph-viewer.js`
    - `https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@<MTHDS_UI_VERSION>/dist/standalone/graph-viewer.css`
    - `https://cdn.jsdelivr.net/npm/elkjs@<ELKJS_VERSION>/lib/elk.bundled.js`
- A single Python module owns versions + URLs + SRI hashes; the Jinja2 template consumes them.
- `make sync-graph-ui`, `make check-graph-ui-sync`, `package.json`, `.graph-ui-version`, and the committed `graph-viewer.{js,css}` all go away.
- A new `pipelex-dev` subcommand recomputes SRI hashes on a version bump (fetch → `sha384` → base64 → write constants).
- Strict TDD: each layer has a failing test landed first, then the change that turns it green.

## Files in scope

- `pipelex/graph/reactflow/standalone_assets.py` — replace inline-bytes helpers (`get_standalone_js`, `get_standalone_css`) with CDN URL + SRI constants.
- `pipelex/graph/reactflow/templates/reactflow.html.jinja2` — drop inline `<style>` / `<script>{{ viewer_js }}</script>`, replace with `<link>` / `<script src=>` carrying `integrity` + `crossorigin`. Keep the embedded JSON `<script type="application/json">` blocks (graphspec, config) as-is — those are data, not assets.
- `pipelex/graph/reactflow/reactflow_html.py` — `generate_reactflow_html` and `_async` variant: stop calling `get_standalone_{js,css}`, instead pass URL + SRI pairs to the template.
- `pipelex/graph/reactflow/assets/graph-viewer.js` — delete.
- `pipelex/graph/reactflow/assets/graph-viewer.css` — delete.
- `pipelex/graph/reactflow/assets/.graph-ui-version` — delete.
- `package.json` — delete (its sole purpose was driving `sync-graph-ui`).
- `Makefile` — remove `sync-graph-ui`, `sgui`, `check-graph-ui-sync` targets, plus any CI hook that depends on them.
- `tests/unit/pipelex/graph/test_reactflow_html.py` — assert the new HTML shape (external `<link>` / `<script src>` with `integrity` + `crossorigin`, no inline bundles).
- New: `pipelex/cli/dev/bump_graph_ui_assets.py` (or wherever `pipelex-dev` subcommands live) — refresh SRI hashes for a new pinned version.
- `pyproject.toml` — package-data section will lose the `assets/*` entry if it currently lists the bundle files.

## SRI computation reference

```bash
curl -sSL <url> | openssl dgst -sha384 -binary | openssl base64 -A
# wrap as: integrity="sha384-<output>"
```

jsDelivr's package page also publishes ready-to-paste `<script integrity="sha384-...">` snippets per file; either source is acceptable as long as the hash is verified against the URL we'll actually ship.

---

## Phase 1 — Verify CDN availability and capture initial SRI hashes

- [x] Confirm `@pipelex/mthds-ui@0.6.1` resolves on the npm registry: `npm view @pipelex/mthds-ui@0.6.1 dist.tarball` returns a tarball URL. **Result:** ✅ live (`https://registry.npmjs.org/@pipelex/mthds-ui/-/mthds-ui-0.6.1.tgz`).
- [x] Confirm jsDelivr serves the three target files:
    - [x] `curl -fsI https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@0.6.1/dist/standalone/graph-viewer.js` — **❌ 404**
    - [x] `curl -fsI https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@0.6.1/dist/standalone/graph-viewer.css` — **❌ 404**
    - [x] `curl -fsI https://cdn.jsdelivr.net/npm/elkjs@0.11.1/lib/elk.bundled.js` — ✅ 200
- [x] ~~Compute and record `sha384` SRI hashes~~ — done against `@pipelex/mthds-ui@0.6.3` (see below).
- [x] Sanity check: cross-reference the jsDelivr page — all three URLs return `HTTP/2 200` and hashes match the served bytes.

### Pinned versions + integrity (target: bump `MTHDS_UI_VERSION` to `0.6.3`)

| Asset | Version | Integrity |
| --- | --- | --- |
| `@pipelex/mthds-ui` js | `0.6.3` | `sha384-BS9SD/K440VwYZxJCMuOi3g0FVlFz9ugiivYvkVpRDPFRo9FMc6IXQl9EM22VCSP` |
| `@pipelex/mthds-ui` css | `0.6.3` | `sha384-Ue1fm1guW8EQGdaqrsi+8Zm5Iq5AGkxa5+UeWw+sy8vVCSYkGez6+80+p9/oxqOn` |
| `elkjs` | `0.11.1` | `sha384-k7OFwtsMfFyYU75zZhPkC8VRASnGrW1pxavUnozOiO2B5M5gv6PYGOkEYZTrVtvo` |
- [x] If the npm publish under `@pipelex/mthds-ui` is *not* yet live, pause this plan and unblock the npm publish first — the rest of the plan assumes a working package on the registry.

### ⛔ BLOCKER discovered on 2026-05-13

The published npm tarball `@pipelex/mthds-ui@0.6.1` exists, but **it does not contain `dist/standalone/graph-viewer.{js,css}`**. jsDelivr serves the contents of the npm tarball verbatim, so the two URLs the plan depends on return 404.

Root cause is in the `mthds-ui` repo:

- `package.json` defines two build scripts: `"build": "tsup"` and `"build:standalone": "node scripts/build-standalone.mjs"`.
- `tsup` produces `dist/index.js`, `dist/graph/`, `dist/shiki/`, etc. — but *not* `dist/standalone/`.
- `.github/workflows/release.yml` runs only `npm run build` before `npm publish --access public --provenance`, so the standalone bundle is never in the published tarball. jsDelivr file listing for `@pipelex/mthds-ui@0.6.1` confirms: no `dist/standalone/` directory.
- jsDelivr's `gh` mode (`cdn.jsdelivr.net/gh/Pipelex/mthds-ui@v0.6.1/...`) also 404s because the standalone bundle is a build artifact and is not committed to the git repo (`dist/` is in `.gitignore`).
- The v0.6.1 GitHub release also has no uploaded asset for the standalone bundle.

So there is no public URL today that can serve the IIFE standalone bundle, on any CDN. The plan cannot proceed past Phase 1 until a new mthds-ui version is published that includes `dist/standalone/` in the npm tarball.

### Unblock plan (action required outside this repo)

The following needs to happen in `mthds-ui`, then we resume here:

1. Edit `mthds-ui/.github/workflows/release.yml`: add a `npm run build:standalone` step after the existing `npm run build` step (or fold `build:standalone` into `build`). This is a small, reversible change.
2. Bump `mthds-ui/package.json` to a new version (e.g. `0.6.3`) and prepare a CHANGELOG entry noting that the standalone bundle is now shipped on npm (intentionally, for downstream CDN use).
3. Merge to `main` and trigger the release workflow → new tarball on npm contains `dist/standalone/graph-viewer.{js,css}`.
4. Resume Phase 1 in this plan against the new pinned version: hit jsDelivr, capture SRI hashes, land them as Python constants in Phase 2. Update `MTHDS_UI_VERSION` accordingly throughout this plan.

Sanity check before resuming:

```bash
npm view @pipelex/mthds-ui@<new_version> 2>&1 | grep -E "unpackedSize|tarball"
curl -fsI https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@<new_version>/dist/standalone/graph-viewer.js
curl -fsI https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@<new_version>/dist/standalone/graph-viewer.css
```

All three must succeed. Only then continue with Phase 2.

### Checkpoint A — CDN assets verified ✅

At this point we know exactly which URLs we'll target and what the integrity hashes are. Good handoff point: next phase is the smallest possible code change to start consuming them.

---

## Phase 2 — Introduce CDN constants module (red → green)

- [x] Add a failing unit test `tests/unit/pipelex/graph/reactflow/test_cdn_assets.py` (new class `TestCdnAssets`, single-class-per-module rule) asserting:
    - [x] Module exposes three `CDNAsset`-shaped objects (`mthds_ui_js`, `mthds_ui_css`, `elkjs`) — each with `url: str`, `integrity: str`, `crossorigin: str`.
    - [x] Each `url` starts with `https://cdn.jsdelivr.net/npm/`.
    - [x] Each `integrity` starts with `sha384-` and decodes to 48 bytes (regex + base64 decode length check).
    - [x] `crossorigin == "anonymous"`.
    - [x] URL contains the pinned version (e.g. `@0.6.3/`, `@0.11.1/`) — guards against unpinned drift.
- [x] Run, confirm failure (module doesn't exist yet).
- [x] Rewrite `pipelex/graph/reactflow/standalone_assets.py`:
    - [x] Remove `get_standalone_js` and `get_standalone_css`.
    - [x] Define a small `CDNAsset` `BaseModel` with `frozen=True` (`BaseModel` matches existing house style) with `url`, `integrity`, `crossorigin` fields.
    - [x] Export module-level constants `MTHDS_UI_JS`, `MTHDS_UI_CSS`, `ELKJS` with the values captured in Phase 1.
    - [x] Add version constants `MTHDS_UI_VERSION = "0.6.3"`, `ELKJS_VERSION = "0.11.1"` and derive the URLs from them so the version appears in exactly one place.
- [x] Re-run; green. Run `make agent-check`.

## Phase 3 — Template + HTML generator wire-up (red → green)

- [x] Add failing test cases in `tests/unit/pipelex/graph/test_reactflow_html.py` (extend the existing class, follow its style) asserting that the rendered HTML:
    - [x] Contains the `<link rel="stylesheet">` for mthds-ui CSS with full SRI attributes.
    - [x] Contains the `<script src="…elkjs…">` with full SRI attributes (and no `unpkg.com/elkjs`).
    - [x] Contains the `<script src="…mthds-ui js…">` with full SRI attributes.
    - [x] Does **not** contain `"use strict"`, `.react-flow`, or `<style>` — proves we're no longer inlining.
    - [x] Still contains the two `<script type="application/json" id="pipelex-…">` blocks — those carry data, not code.
- [x] Run, confirm failure (template still inlines).
- [x] Update `pipelex/graph/reactflow/templates/reactflow.html.jinja2`:
    - [x] Replace `<style>{{ viewer_css | safe }}</style>` with `<link rel="stylesheet" href="{{ mthds_ui_css.url }}" integrity="{{ mthds_ui_css.integrity }}" crossorigin="{{ mthds_ui_css.crossorigin }}">`.
    - [x] Replace the hard-coded unpkg elkjs `<script>` with the jsDelivr+SRI variant.
    - [x] Replace `<script>{{ viewer_js | escape_script_tag | safe }}</script>` with `<script src="…" integrity="…" crossorigin="…"></script>`. Kept `escape_script_tag` on the JSON data blocks only.
    - [x] Refreshed the licensing comment to call out that *all* viewer code loads from jsDelivr with SRI, so the EPL-2.0 split for elkjs is no longer a special case.
- [x] Update `pipelex/graph/reactflow/reactflow_html.py`:
    - [x] Drop the import of `get_standalone_css` / `get_standalone_js` (they no longer exist).
    - [x] Import the three `CDNAsset` constants.
    - [x] In both `generate_reactflow_html` and `generate_reactflow_html_async`, replace `"viewer_js"` / `"viewer_css"` with `"mthds_ui_js": MTHDS_UI_JS`, `"mthds_ui_css": MTHDS_UI_CSS`, `"elkjs": ELKJS`. Factored shared dict construction into `_build_templating_context`.
- [x] Re-run the new tests; green. Run `make agent-check`.

### Checkpoint B — HTML now externalizes all code ✅

At this point the generated HTML is small, externally linked, integrity-protected. Vendored files are still on disk but no longer read. Next phase removes them.

---

## Phase 4 — Remove vendored bundle and sync pipeline

- [x] Delete `pipelex/graph/reactflow/assets/graph-viewer.js`.
- [x] Delete `pipelex/graph/reactflow/assets/graph-viewer.css`.
- [x] Delete `pipelex/graph/reactflow/assets/.graph-ui-version`.
- [x] `pipelex/graph/reactflow/assets/` directory deleted (only held the dropped assets + an empty `__init__.py`; no Python code imported the package).
- [x] Delete `package.json` (verified it was the sync-pipeline manifest, not a real Node package config).
- [x] In `Makefile`, removed `sync-graph-ui`, `sgui`, `check-graph-ui-sync`, `cguis` targets and their `.PHONY` listing + help section.
- [x] `pyproject.toml` did not list assets in any `package-data` entry — `hatch` already excluded `dev_cli`; nothing else to drop.
- [x] `grep -rn "sync-graph-ui\|standalone_assets\|graph-ui-version\|get_standalone_css\|get_standalone_js" .` swept — remaining hits are the new imports (`standalone_assets` constants), the historical CHANGELOG entry (intentionally left as accurate history), and this plan doc. Pay attention to:
    - [x] CI YAML (`.github/workflows/*.yml`) — `graph-ui-check.yml` deleted.
    - [x] Other Makefiles — only the root Makefile referenced it.
    - [x] Skill / agent docs (`mthds-plugins/`, local `.claude/skills/`) — `.claude/skills/update-graph-ui/SKILL.md` rewritten for the new CDN+SRI flow.
    - [x] Top-level `README.md` / `CLAUDE.md` — no references in `README.md`; `_ui/CLAUDE.md` updated under Phase 5 with the new `pipelex-dev` command.
- [x] Run `make agent-check` and `make agent-test`; both green.

## Phase 5 — Bump helper (`pipelex-dev refresh-graph-ui-sri`)

- [x] Add a failing test under `tests/unit/pipelex/cli/dev/test_refresh_graph_ui_sri.py`:
    - [x] Patches `urlopen` (re-exported into the command module) to return fixed bytes.
    - [x] Invokes the command with target versions for mthds-ui and elkjs.
    - [x] Asserts the written constants include the expected `sha384-<base64>` hashes computed from the fixture bytes.
    - [x] Additional test compiles and executes the regenerated module, then checks that `MTHDS_UI_JS.integrity` / `MTHDS_UI_CSS.integrity` / `ELKJS.integrity` match expectations (round-trip).
- [x] Run, confirm failure.
- [x] Implement `pipelex/cli/dev_cli/commands/refresh_graph_ui_sri_cmd.py`:
    - [x] Accepts `--mthds-ui-version` and `--elkjs-version` (default to the currently pinned values via `pipelex.graph.reactflow.standalone_assets`, so "rehash without bumping" works too).
    - [x] Fetches each of the three jsDelivr URLs over HTTPS via `urlopen`, with an explicit `_ALLOWED_URL_PREFIX` guard so it can never be tricked into hitting a non-jsDelivr scheme.
    - [x] Computes `sha384` and standard base64 (matches the SRI spec).
    - [x] Writes the regenerated module text into `pipelex/graph/reactflow/standalone_assets.py` from a `_MODULE_TEMPLATE`; the template is the single source of truth for the file's shape, so refresh runs are deterministic and diff-stable.
    - [x] Wired into the `pipelex-dev` Typer app and into `PipelexDevCLI.list_commands` (alphabetic order).
- [x] Added an entry to `_ui/CLAUDE.md` under "Pipelex Dev CLI" documenting the new command.
- [x] Re-run; green.

## Phase 6 — Documentation + changelog

- [x] CHANGELOG entry under `## [Unreleased]` → `### Changed` (per memory `feedback_no_unreleased_header`). Reframed as a single `Changed` bullet because the user-visible impact is a behavior change at view time, not a bug fix.
- [x] `docs/` was checked — no page directly covers reactflow rendering setup; the in-template comment and CHANGELOG cover the new state for now.
- [x] In-template `<!-- External (loaded from jsDelivr with SRI): … -->` comment updated to reflect that all viewer code now loads from jsDelivr with SRI.

## Phase 7 — Quality gates + smoke test

- [x] `make agent-check` — clean.
- [x] `make agent-test` — green.
- [x] Added `tests/unit/pipelex/graph/test_smoke_html_render.py` as a permanent bounded-size smoke (`len(html) < 10_000`); the rendered output is now **~2.2 kB** vs. the prior ~530 kB+ (drop of ~99.6%). The full live-browser checklist below stays as a manual gate the operator should run once before merging:
    - [ ] Open the generated HTML in a real browser; confirm the graph renders correctly.
    - [ ] DevTools → Network shows three external requests to `cdn.jsdelivr.net` (or cache hits).
    - [ ] DevTools → Console is free of SRI mismatch errors (`Failed to find a valid digest in the 'integrity' attribute for resource …`).
    - [ ] Tamper with one byte of the published asset (local HTTP proxy or hand-edit the SRI string) and confirm the browser refuses to execute the script — proves SRI is engaged.
- [x] Generated HTML size before/after on the same fixture: ~530 kB → 2.2 kB (≥99% shrink, matching the plan's "roughly 2 MB shrink").

### Checkpoint C — feature complete ✅

Touched code (expected on completion):

- `pipelex/graph/reactflow/standalone_assets.py` — rewritten to expose `CDNAsset` constants
- `pipelex/graph/reactflow/templates/reactflow.html.jinja2` — external `<link>` + `<script src>` with SRI
- `pipelex/graph/reactflow/reactflow_html.py` — passes URL+SRI pairs into the template
- `pipelex/graph/reactflow/assets/` — deleted
- `package.json` — deleted
- `Makefile` — `sync-graph-ui` / `sgui` / `check-graph-ui-sync` removed
- `pipelex/cli/dev/bump_graph_ui_assets.py` — new
- `tests/unit/pipelex/graph/reactflow/test_cdn_assets.py` — new
- `tests/unit/pipelex/graph/test_reactflow_html.py` — extended
- `tests/unit/pipelex/cli/dev/test_refresh_graph_ui_sri.py` — new
- `CHANGELOG.md` — entry under `[Unreleased]`
- `_ui/CLAUDE.md` — documents the new `pipelex-dev` subcommand

---

## Out of scope

- Self-hosting a CDN (decided against in conversation — jsDelivr suffices).
- Moving back to fully inlined / truly offline. If we ever want that, it's a separate plan that also has to deal with elkjs's EPL-2.0 distribution conditions.
- Migrating the mermaid renderer; this plan only touches the reactflow path.
- Changes to `mthds-ui` itself (e.g. trimming bundle size). The CDN model makes bundle size less critical anyway since the CDN compresses + the browser caches.

## Risks + mitigations

- **jsDelivr outage** → graph viewer doesn't render. Mitigation: pinned version means we can advise users to side-load the bundle from npm into a local file: URL if needed; we accept this tradeoff explicitly. The same risk already existed for elkjs on unpkg.
- **SRI hash drift on the CDN side** → browsers refuse to execute. Highly unlikely (npm tarballs are immutable, jsDelivr caches them), but if it ever happens, bump the version or rehash via the new `pipelex-dev` command. Document this in the bump command's `--help`.
- **`@pipelex/mthds-ui` not actually published yet** → caught in Phase 1; this plan is gated on it.

## Decisions taken

- jsDelivr over unpkg (multi-CDN backing, native SRI publishing).
- `sha384` (the SRI recommendation; longer than sha256, browser-supported, future-proof).
- `crossorigin="anonymous"` (required for SRI to engage on cross-origin script/link elements).
- Versions pinned in one Python module, not in the template or in `package.json` — single source of truth.
- Delete `package.json` outright rather than keep it as a "documentation" file — its only role was driving the sync pipeline, which is gone.
- Loaded-licenses comment in the HTML template is kept (and updated), since it remains the right place to attribute upstream code shipped to the viewer.
