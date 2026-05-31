# Keyword-only arguments — track

This track makes non-subject function parameters keyword-only across the `pipelex/` source tree so call sites are self-documenting: a reader (human or SWE agent) can tell what every argument means without opening the definition. An AST guard (`check-keyword-only`) is built first and wired into the `make check` family; it ships red-to-green against a committed baseline and drives the package-by-package burn-down so new code is held to the convention immediately while the existing population is converted.

## Files in this track

- [`../../TODOS.md`](../../TODOS.md) — the master tracker: locked decisions, phases, waves, checkpoint protocol, and the per-checkpoint cold-start snapshots.
- [`convention.md`](convention.md) — the canonical human-readable rule: the two exceptions, the carve-out list, the symmetric-tuple allowlist, the `# kw-only: ignore` escape hatch, and worked examples.
- [`state.md`](state.md) — the running cold-start log: current status, guard command and baseline path, the per-package violation inventory, the decisions log, the current position, and the exact resume commands.
- [`inventory.json`](inventory.json) — the machine-readable violation inventory: `total`, `per_package_counts`, and `violations_by_package` (each entry carries `relative_path`, `qualified_name`, `lineno`, and the stable `key`).
- [`violations-baseline.txt`](violations-baseline.txt) — the committed baseline the guard reads: newline-delimited `relpath::qualified_name` keys, no line numbers, sorted lexicographically. The guard fails only on NEW violations not present here; this file strictly shrinks as waves land and is removed once the tree is fully compliant.

## Wave ordering

The burn-down lands one wave at a time, each wave its own PR (or a couple of small PRs), reviewed and merged before the next, lowest-risk leaf packages first and the framework-sensitive / public-API surface last. The waves below mirror Phases 2–6 of the master tracker.

- Wave 1 — low-risk leaf packages: `tools/`, `reporting/`, `observer/`, `tracing/` (plus the root modules `types.py`, `config.py`, `urls.py`, `errors/`, `base_exceptions.py`, `exceptions.py`).
- Wave 2 — domain core: `core/`, `language/`, `kit/`, `libraries/`.
- Wave 3 — inference layer: `cogt/`, `plugins/`.
- Wave 4 — execution path: `pipe_operators/`, `pipe_controllers/`, `pipe_run/`, `pipeline/`, `graph/`.
- Wave 5 — framework-sensitive & public API (most care, last): `builder/`, `temporal/`, `system/`, `cli/`, and the public surface `hub.py`, `config.py`, `pipelex.py`.
