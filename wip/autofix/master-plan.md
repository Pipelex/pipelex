# Autofix — executive master plan

Deterministic auto-fixing of `.mthds` validation errors. Full rationale and architecture: [suggested-fixes-design.md](suggested-fixes-design.md). Approved decisions: fixes attach to validation diagnostics (D1), runtime-only wire first (D2), wave 1 targets agent CLI + skills (D3), pruning cut from wave 1 (D4).

**Guiding principle:** one validation engine feeds every surface. Validators state what they expected; a planner turns that into structured `suggested_fix` payloads on the report; appliers and commands are thin. Fix ops are contract, rendered diffs are presentation.

## Steps

1. **Spike — prove the chain end-to-end (NEXT).** One rule (`match-sequence-output`) through all layers: enriched typed error → planner → tomlkit applier → convergence loop, TDD, no CLI. Exit: chain proven, format preservation demonstrated by golden tests, design doc updated with findings. Detailed plan: [`TODOS.md`](../../TODOS.md) at the worktree root.
2. **Wave-1 engine.** Remaining safe rules (`sync-controller-inputs`, `strip-native-concept-redecl`; `strip-namespace` if position-preserving rename lands clean), hardened loop (fingerprint bail, multi-file targeting), `suggested_fix` on `ValidationErrorItem`. Exit: all wave-1 rules green with golden tests.
3. **Wave-1 surface — ship it.** `pipelex-agent fix bundle` + `pipelex fix` commands (two-stream output), `validate` output carrying `suggested_fix` annotations, docs page, changelog. Exit: released in a pipelex version.
4. **Skills uptake.** Update the `mthds-fix` skill (and pipelex-plugins equivalent) to run deterministic `fix` before manual LLM editing. Cross-repo, cheap, gated on step 3's release.
5. **Wave 2 — protocol promotion.** `suggested_fix` becomes a formal MTHDS protocol surface: spec sections in `docs/specs/`, conformance arm, schema sync to downstream copies (mthds, mthds-js, mthds-python).
6. **Wave 2 — remote surfaces.** API `POST /fix` on pipelex-api, MCP `mthds_fix` tool. Both thin wrappers over the same engine/report.
7. **Wave 2 — editor.** VS Code `CodeActionProvider` (first code action in the extension), quick fixes keyed on `diag.code = error_type` with fix payloads riding the existing validation backends.
8. **Later.** Pruning rules (`prune-unreachable`, `prune-unused-concepts`) resurrected as opt-in lint warnings with attached fixes; further rules as validator enrichment makes them deterministic.

Steps 2–3 are sequenced by the spike's findings; steps 5–7 are independent of each other once 3 has shipped and can be re-prioritized freely. Each step gets its own detailed plan when it starts — this document stays high-level.
