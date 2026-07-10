# Deferred follow-ups from Checkpoint A′ (format_mthds backend)

Two forward-looking items surfaced during Phase A′ and its review, both concerning **`pipelex-tools-py`** — which is ours (`vscode-pipelex/crates/pipelex-py`), so both are upstream-fixable. Neither blocks Phase A′; recorded here to revisit at the noted trigger.

## 1. Simplify the `Diagnostic` import workaround once the fixed `pipelex-tools-py` ships

Louis is fixing the stub/runtime drift in the package.

**What we hit:** `pipelex_tools`' PEP 561 stub declares `Diagnostic` / `Range` / `FormatResult` / `LintResult` in `__all__`, but those TypedDicts are type-only — not runtime exports of the compiled module. So `from pipelex_tools import Diagnostic` type-checks (pyright/mypy read the stub) yet raises `ImportError` at runtime.

**Current workaround** (`pipelex/pipeline/fixes/applier.py`): import only the real callable `format_mthds` at module top, and pull `Diagnostic` in under a `TYPE_CHECKING` guard with a quoted annotation on `_render_syntax_diagnostic(diagnostic: "Diagnostic")`.

**Follow-up (gated on the fix shipping + our pin bump):** once `pipelex-tools-py` exports the TypedDicts at runtime (or is otherwise fixed so the advertised import works), delete the `TYPE_CHECKING` block and the quoted annotation, and import `Diagnostic` at the top beside `format_mthds`. Bump the `pipelex-tools-py` pin in `pyproject.toml` to the fixed version in the same change. Purely a cleanup — no behavior change.

## 2. Explore an upstream rename / canonical-ordering primitive for Phase C (`strip-namespace`)

**Do not dig into this now** — it's a note for when Phase C is actually attempted (Phase C is a gated stretch; dropping it is a valid outcome).

**Context:** Phase C's `strip-namespace` fix needs a **position-preserving rename** of a `[pipe.<domain>.<code>]` table key. The known trap (from the old `feature/Bundle-fixer` branch) is that a tomlkit `del` + re-add sends the renamed pipe to the bottom of `[pipe]`. Phase A′ does **not** rescue this: `format_mthds` reflows spacing and alignment but does **not reorder** tables or keys, so a reordered pipe stays reordered after the format pass.

**Possible upstream angle:** since `pipelex-tools-py` is ours, `format_mthds` (or a sibling function) could expose either a position-preserving table-key **rename primitive** or a **canonical table-ordering** option. Either would let Phase C sidestep the fiddly tomlkit rename mechanics that currently gate the whole rule. Weigh this against just solving it in tomlkit when Phase C's go/no-go spike (TODOS.md C.1) runs.
