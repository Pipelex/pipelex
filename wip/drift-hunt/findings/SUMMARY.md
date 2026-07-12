# Drift Hunt — findings SUMMARY (running scoreboard)

Accumulates as each Stage 1 part lands. Per-section defect density is the campaign's headline metric; the rejected-findings column tracks how much the adversarial-verify pass (D6) filtered. Denominators come from `wip/drift-hunt/inventory.md`.

## Per-section scoreboard

| Section | Pages | Claims checked | Confirmed | Rejected (D6) | Density (find/page) | 🔴 breaks | 🟠 wrong | 🟡 misleading | ⚪ stale | Findings file |
|---|---|---|---|---|---|---|---|---|---|---|
| building-methods | 35 | 452 | 47 | 0 | 1.34 | 28 | 11 | 6 | 2 | [building-methods.md](building-methods.md) |
| under-the-hood + advanced | 26 | — | — | — | — | — | — | — | — | *(Part 2, not started)* |
| features + reliability | 25 | — | — | — | — | — | — | — | — | *(Part 3, not started)* |
| the tail (get-started, contribute, tools non-CLI, setup, viewpoint, root, D9 adds) | 18 | — | — | — | — | — | — | — | — | *(Part 4, not started)* |
| cookbook | 21 | — | — | — | — | — | — | — | — | *(Stage C — greenlight-gated, D7)* |
| **Total (Stage 1 so far)** | **104** | **452** | **47** | **0** | — | 28 | 11 | 6 | 2 | |

## Top defect classes so far

1. **Doc bundle examples that fail `pipelex validate bundle`** — the dominant class in building-methods (~18 findings). Root: examples parse as TOML but fail semantic validation (missing required `description`/`domain`, inline `@` sigil, unused inputs, native-concept redeclaration, operator constraints).
2. **Parameter-table requiredness inverted vs `PipeBlueprint`** (5 in building-methods).
3. **Renamed Python API never propagated** (`PipelexRunner`→`PipelexMTHDSProtocol`, `bundle_uri`→`bundle_uris`, `execute_pipeline`→`execute`).
4. **Stale enumerations** (native concepts, reasoning_effort, operator lists, deck files, img-gen handles).
5. **Wrong defaults / behavioral claims** (dpi 150→72, PipeFunc "async required", cwd library fallback, etc.).

## Drift-contract candidates (evidence for Phase 3 verdict, per D5)

- **`validate-doc-bundle-examples`** — a derived check that extracts every fenced `toml`/`mthds` bundle example under `docs/` and runs it through `pipelex validate bundle`. Would have caught the majority of building-methods' breaks-a-user severity. Strongest candidate so far.
- **`doc-python-snippets-import`** — import-and-construct smoke check for Python snippets in docs (catches the renamed-API class).
- **`operator-param-table-vs-blueprint`** — diff each operator doc's parameter table against its pydantic model's required/optional fields (catches requiredness inversions). Needs a table parser.

## Rejected findings (audit trail)

- **building-methods:** none — all 47 review-stage findings survived independent adversarial re-verification.

## Cross-part / cross-repo carry-overs

- **`docs/under-the-hood/execution-graph-tracing.md:269`** — stale `execute_pipeline()` symbol (same class as building-methods F44). Fold into **Part 2**'s fix batch.

## Cookbook-repo defects (handoff, not fixed here)

- *(none yet — Stage C not run)*
