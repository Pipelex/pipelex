# Drift Hunt — findings SUMMARY (running scoreboard)

Accumulates as each Stage 1 part lands. Per-section defect density is the campaign's headline metric; the rejected-findings column tracks how much the adversarial-verify pass (D6) filtered. Denominators come from `wip/drift-hunt/inventory.md`.

## Per-section scoreboard

Counts are **drift** findings (after the authoring-convention carve-out, below). Convention reclassifications are tracked in the last column.

| Section | Pages | Claims checked | Drift | Convention | Rejected (D6) | Density | 🔴 breaks | 🟠 wrong | 🟡 misleading | ⚪ stale | Findings file |
|---|---|---|---|---|---|---|---|---|---|---|---|
| building-methods | 35 | 452 | 44 | 3 | 0 | 1.26 | 25 | 11 | 6 | 2 | [building-methods.md](building-methods.md) |
| under-the-hood + advanced | 26 | 435 | 42 | 0 | 0 | 1.62 | 10 | 23 | 4 | 5 | [under-the-hood-advanced.md](under-the-hood-advanced.md) |
| features + reliability | 25 | 308 | 10 | 0 | 0 | **0.40** | 2 | 7 | 1 | 0 | [features-reliability.md](features-reliability.md) |
| the tail (get-started, contribute, tools non-CLI, setup, viewpoint, root, D9 adds) | 18 | — | — | — | — | — | — | — | — | — | *(Part 4, not started)* |
| cookbook | 21 | — | — | — | — | — | — | — | — | — | *(Stage C — greenlight-gated, D7)* |
| **Total (Stage 1 so far)** | **104** | **1195** | **96** | **3** | **0** | — | 37 | 41 | 11 | 7 | |

> **Part 2 density caveat:** 42/26 = 1.62, but 5 of the 26 pages are 8-line "Under Construction" stubs (`advanced/*-injection.md`, nothing checkable). Against the 21 *substantive* pages, density is 2.0 (14 dirty / 7 clean).

> **Part 3 is the campaign's outlier — and it is a real one.** 0.40 findings/page, ~4× cleaner than the technical sections, with **all four reliability pages clean**. A clean sweep on pages seeded as high-risk is exactly where this campaign could fool itself, so the load-bearing "clean" claims were hand-verified after the run (retry config keys + defaults, telemetry enum values, the cost-tracking snippet's imports, the `deepseek-ocr` handle) — all held. **The capability/landing pages drift far less than the internals pages.**

## Top defect classes so far

1. **Renamed Python API/method never propagated into docs** — now the single biggest cross-part class. Building-methods: `PipelexRunner`→`PipelexMTHDSProtocol`, `bundle_uri`→`bundle_uris`, `execute_pipeline`→`execute`. Part 2 adds `OrchestratorProtocol.run`→`execute` (page-wide), `render_*_error()`→`render_inference_error()`, `model_class_from_json_schema`→`SchemaToModelFactory.make_from_json_schema`, `set_reporting_delegate`→`set_report_delegate`, `observe_*` protocol names, `LLM_MODEL_BACKEND_PAIRS`→`*_COMBOS`. Caught by an import-and-`getattr` check on doc-referenced Python names.
2. **Doc bundle examples that fail `pipelex validate bundle`** — the dominant class in building-methods (~18 findings). Root: examples parse as TOML but fail semantic validation (missing required `description`/`domain`, inline `@` sigil, unused inputs, native-concept redeclaration, operator constraints). *(Part-2 internals pages have no bundle examples, so this class is absent there.)*
3. **Keyword-only-convention drift in doc code snippets** (new, Part 2: F6, F9, F11, F21, F30, F32) — a doc shows a signature/call without the bare `*` the repo convention now requires; the positional form raises `TypeError`.
4. **Parameter-table / config-model requiredness & fields** — building-methods: 5 param-table requiredness inversions vs `PipeBlueprint`. Part 2: embedded `pipelex.toml` snippet drift (F13 missing required field, F31 wrong value).
5. **Stale enumerations** (native concepts, reasoning_effort, operator lists, deck files, img-gen handles; Part 2: flowchart directions, `EdgeKind`, fabricated `telemetry_mode` values). **Part 3 promotes this class to first rank for capability pages** — 4 of its 10 findings are a *closed* list that omits a shipped member or still names a retired one: native concepts 11-of-15, the operator roster 6-of-7 (`PipeStructure` missing, on two pages), and a `flux-2-pro` retired since v0.23.5 still listed under the Gateway. The failure mode is systematic: a list is written once, the registry grows, the list is never revisited.
6. **Wrong defaults / behavioral claims** (dpi 150→72, PipeFunc "async required", cwd library fallback; Part 2: 0-based vs 1-based indexing, single-mutex vs double-check locking, `find_project_root` markers, output filenames, silent-no-op observer).

## Authoring-convention carve-out (Louis, 2026-07-12)

A ruling that shapes both the fix triage and the check design. Omitting *scaffolding* in a focused teaching example is convention, not drift: a missing top-level `domain`, a missing pipe `description`, and an omitted `prompt` body are all things a reader fills in (with a placeholder) before running. **Still drift** (survives scaffolding): a written prompt that ignores its own declared input; wrong field names / output types / enum / default values. In building-methods this reclassified 3 findings out (all breaks-a-user: 28→25).

## Drift-contract candidates (evidence for Phase 3 verdict, per D5)

- **`validate-doc-bundle-examples`** (strongest for building-methods) — extract every fenced `toml`/`mthds` bundle example under `docs/`, **inject placeholder `description`/`domain` and tolerate an omitted prompt**, then run `pipelex validate bundle`. The placeholder-injection step (Louis's insight) is what makes it precise — it isolates the ~18 genuine breaks and skips every teaching fragment. Stage 0's prescreen missed all of these because it only checked TOML *parses*, not that the bundle *validates*.
- **`doc-python-snippets-import`** (strongest for under-the-hood/advanced — Part 2 vindicates it hard) — import-and-`getattr` smoke check for Python symbols referenced in doc snippets. Catches the renamed-API class, which is the #1 defect class across both parts (F3/F8/F10/F27/F35/F37/F38 + the F30 invented param, plus building-methods' `PipelexRunner`/`bundle_uri`/`execute_pipeline`).
- **`doc-python-signatures-vs-live`** (new, Part 2) — parse fenced `python` blocks in `docs/under-the-hood/*.md`, resolve each documented call/signature against live `inspect.signature`, flag positional uses of keyword-only params. Catches the whole keyword-only-drift class (F6/F9/F11/F21/F30/F32). Sibling to the existing `check-keyword-only` source guard.
- **`doc-toml-config-vs-shipped`** (new, Part 2) — line-diff every fenced `toml` block labelled as `pipelex.toml` against the real shipped config (fields present + values). Catches F13 (missing required field) and F31 (wrong value); the `reasoning-controls.md` reviewer independently proposed exactly this.
- **`operator-param-table-vs-blueprint`** — diff each operator doc's parameter table against its pydantic model's required/optional fields (catches the 5 requiredness inversions in building-methods). Needs a table parser.
- **`doc-enumerations-vs-registry`** (new, Part 3 — the strongest candidate for the capability sections) — diff documented **closed** lists against the code's registries: `NativeConceptCode`, the `pipe_operators/` package (blueprints carrying `pipe_category="PipeOperator"`), the pipe controllers, and the shipped model deck. Catches F2/F7/F8/F9. The diff is trivial; **the hard part is deciding which lists are closed** — the exhaustive-vs-illustrative rule Part 3 had to invent would need encoding (only check lists with no "such as" / "including" / "and more" hedge), otherwise the check drowns in false positives on deliberately-partial teaching lists.

## Rejected / reclassified findings (audit trail)

- **building-methods:** 0 rejected by adversarial verify (all 47 review-stage findings held up). 3 later reclassified as authoring convention (missing `domain`, missing `description`, omitted prompt body) → 44 counted as drift. See `building-methods.md` → "Reclassified as authoring convention".
- **under-the-hood + advanced:** 0 rejected (all 42 held; 6 carried minor evidence corrections folded into the findings file). 0 reclassified — the D11 carve-out doesn't apply to internals/injection pages (no bundle-teaching examples).
- **features + reliability:** 0 rejected (all 10 held). 0 reclassified — D11 doesn't apply (capability pages carry no bundle-teaching examples). The suppression risk here ran the *other* way (false negatives from the new exhaustive-vs-illustrative and floor-count rules), so the high-risk clean pages were hand-verified post-run; see the findings file's spot-check note.

## Cross-part / cross-repo carry-overs

- **`docs/under-the-hood/execution-graph-tracing.md:269`** — RESOLVED as Part 2 F10 (`execute_pipeline`→`execute`, confirmed). Fold into Stage 2's fix batch.
- **`docs/tools/cli/agent-cli.md:38`** — NEW, from Part 3 F1. The agent-CLI page documents `--mock-inputs` as just "Use mock inputs", omitting the **`(requires --dry-run)`** qualifier that `docs/tools/cli/run.md` states correctly three times. `docs/tools/cli/` is out of Stage-1 scope (D2, freshly reviewed) — but D2 reopens it precisely when a Stage 1 finding points back in, and this one does. One-line fix; fold into Stage 2.
- *(No outgoing carry-overs from Part 2 — its findings are self-contained to their pages.)*

## Cookbook-repo defects (handoff, not fixed here)

- *(none yet — Stage C not run)*
