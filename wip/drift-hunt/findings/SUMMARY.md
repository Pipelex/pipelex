# Drift Hunt — findings SUMMARY (running scoreboard)

Accumulates as each Stage 1 part lands. Per-section defect density is the campaign's headline metric; the rejected-findings column tracks how much the adversarial-verify pass (D6) filtered. Denominators come from `wip/drift-hunt/inventory.md`.

## Per-section scoreboard

Counts are **drift** findings (after the authoring-convention carve-out, below). Convention reclassifications are tracked in the last column.

| Section | Pages | Claims checked | Drift | Convention | Rejected (D6) | Density | 🔴 breaks | 🟠 wrong | 🟡 misleading | ⚪ stale | Findings file |
|---|---|---|---|---|---|---|---|---|---|---|---|
| building-methods | 35 | 452 | 44 | 3 | 0 | 1.26 | 25 | 11 | 6 | 2 | [building-methods.md](building-methods.md) |
| under-the-hood + advanced | 26 | — | — | — | — | — | — | — | — | — | *(Part 2, not started)* |
| features + reliability | 25 | — | — | — | — | — | — | — | — | — | *(Part 3, not started)* |
| the tail (get-started, contribute, tools non-CLI, setup, viewpoint, root, D9 adds) | 18 | — | — | — | — | — | — | — | — | — | *(Part 4, not started)* |
| cookbook | 21 | — | — | — | — | — | — | — | — | — | *(Stage C — greenlight-gated, D7)* |
| **Total (Stage 1 so far)** | **104** | **452** | **44** | **3** | **0** | — | 25 | 11 | 6 | 2 | |

## Top defect classes so far

1. **Doc bundle examples that fail `pipelex validate bundle`** — the dominant class in building-methods (~18 findings). Root: examples parse as TOML but fail semantic validation (missing required `description`/`domain`, inline `@` sigil, unused inputs, native-concept redeclaration, operator constraints).
2. **Parameter-table requiredness inverted vs `PipeBlueprint`** (5 in building-methods).
3. **Renamed Python API never propagated** (`PipelexRunner`→`PipelexMTHDSProtocol`, `bundle_uri`→`bundle_uris`, `execute_pipeline`→`execute`).
4. **Stale enumerations** (native concepts, reasoning_effort, operator lists, deck files, img-gen handles).
5. **Wrong defaults / behavioral claims** (dpi 150→72, PipeFunc "async required", cwd library fallback, etc.).

## Authoring-convention carve-out (Louis, 2026-07-12)

A ruling that shapes both the fix triage and the check design. Omitting *scaffolding* in a focused teaching example is convention, not drift: a missing top-level `domain`, a missing pipe `description`, and an omitted `prompt` body are all things a reader fills in (with a placeholder) before running. **Still drift** (survives scaffolding): a written prompt that ignores its own declared input; wrong field names / output types / enum / default values. In building-methods this reclassified 3 findings out (all breaks-a-user: 28→25).

## Drift-contract candidates (evidence for Phase 3 verdict, per D5)

- **`validate-doc-bundle-examples`** (strongest) — extract every fenced `toml`/`mthds` bundle example under `docs/`, **inject placeholder `description`/`domain` and tolerate an omitted prompt**, then run `pipelex validate bundle`. The placeholder-injection step (Louis's insight) is what makes it precise — it isolates the ~18 genuine breaks and skips every teaching fragment. Stage 0's prescreen missed all of these because it only checked TOML *parses*, not that the bundle *validates*.
- **`operator-param-table-vs-blueprint`** — diff each operator doc's parameter table against its pydantic model's required/optional fields (catches the 5 requiredness inversions). Needs a table parser.
- **`doc-python-snippets-import`** — import-and-construct smoke check for Python snippets in docs (catches the renamed-API class).

## Rejected / reclassified findings (audit trail)

- **building-methods:** 0 rejected by adversarial verify (all 47 review-stage findings held up). 3 later reclassified as authoring convention (missing `domain`, missing `description`, omitted prompt body) → 44 counted as drift. See `building-methods.md` → "Reclassified as authoring convention".

## Cross-part / cross-repo carry-overs

- **`docs/under-the-hood/execution-graph-tracing.md:269`** — stale `execute_pipeline()` symbol (same class as building-methods F44). Fold into **Part 2**'s fix batch.

## Cookbook-repo defects (handoff, not fixed here)

- *(none yet — Stage C not run)*
