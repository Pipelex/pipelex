# PR #1110 review — deferred items

Deferred findings from the SWE-agent review triage of PR #1110 (Migrator Phases 0–1: the migration contract, the operation vocabulary and the schema-1 cut). Each was verified against the code; the ones below are deferred as design calls or as work that belongs to a later migrator phase (see `wip/migrator-3/sequencing.md` at the workspace root), not dismissed. Everything else the bots raised was fixed on the branch: wildcard operations are now atomic on `CONFLICT`, the coverage walk detects occupied destinations and `delete_table` aimed at a key, enum-member accounting follows a path through the entry's own renames, malformed ledgers and misnamed goldens fail as migration errors, `Mapping[...]` is an open node, list items are cleaned of nulls before TOML serialization, and the dev commands escape Rich markup and follow the quiet-mode convention.

## Value-domain narrowing is classified as additive (the one to take up first)

**Reporter:** Codex (two P1 threads, `pipelex/migration/coverage.py` head-link classification and `pipelex/migration/fingerprint.py` `_strip_annotated`). **Verified:** real.

A change that keeps every path and every enum member but narrows what a value may be — `int → str`, `str → SomeEnum`, `list[int] → list[str]`, or a tightened constraint such as `Field(gt=0) → Field(gt=10)` — appears in the fingerprint diff only as a `changed_paths` entry (or, for a constraint, not at all: constraint metadata is stripped at every level). `_check_head_link` classifies that as additive and asks for a golden regeneration, so a valid old file whose value falls outside the new domain fails strict validation with a green gate.

**Why deferred:** both behaviours are stated in the contract (`docs/migration-ledger.md` → "Coverage": *a type or default changed → regenerate the golden*; → "The fingerprint": *constraint metadata is stripped … at every level*, deliberately, so a validation-library upgrade cannot move a golden). Changing them is a contract decision, and no operation in the vocabulary can repair an out-of-domain value — the only remedy is an `unsafe` entry with guidance. So the fix is a new rule, not a patch: **value-domain narrowing demands a bump and an entry, and that entry must be `unsafe`** (or carry a `remap_value` when the narrowing is `str → enum` and the old free-string spellings can be enumerated). It needs a compatibility notion the fingerprint can decide: a rendered type whose union members are a superset of the old ones is a widening (safe); `enum`/`literal → str` is a widening; anything else is a narrowing. Constraints would need a stable projection (the `annotated_types` objects — `Gt`, `Ge`, `Lt`, `Le`, `MinLen`, `MaxLen`, `MultipleOf` — are stable across pydantic versions; `Field(pattern=…)` is a string) recorded per path, with "tightened" defined per constraint kind.

**Revisit when:** Phase 2 (S5, "the checks that prove them"), after a ruling on the two contract sentences. Until then, a maintainer narrowing a type must notice the `changed_paths` line in the `umig` diff by eye — which is exactly the reliance on review the gate exists to remove, so this should not wait past S5.

## `pre_history` entries bypass coverage

**Reporter:** cubic (two P1 threads, `pipelex/migration/ledger.py:90`, `pipelex/migration/coverage.py:228`). **Verified:** the flag is accepted by the model and `check_entry_accounting` returns `[]` for it.

**Why deferred:** designed that way, for now. A pre-history entry removes paths that predate `fingerprint@1`, so no fingerprint pair describes its diff; the contract has it verified by `check-ledger` against its own `declared_removed_paths` and a hand-authored `before` document. Both `check-ledger` and the first such entry (the telemetry back-entry) are Phase 2 (S5) deliverables; no entry carries the flag today, and the coverage gate would flag any op of such an entry as dead if it were checked against `fingerprint@1`.

**Revisit when:** S5 — the check must land in the same pull request as the first `pre_history` entry, and until it does the flag is an escape hatch the contract says must not exist. If S5 slips, the cheap interim is to have coverage report a `pre_history` entry as an issue ("verified by check-ledger, which does not exist yet") so the bypass is loud.

## A required table with only optional children escapes the defaults-layer rule

**Reporter:** cubic (P1, `pipelex/migration/coverage.py:387`). **Verified:** real; `check_defaults_layer` skips `TABLE_TYPE` records, and a table's presence in the defaults document is not recorded in the fingerprint.

**Why deferred:** boot-redundant for the only packaged-document surface. `pipelex/pipelex.toml` is merged beneath every load, so a required table absent from it fails the repository's own boot (`make tb`), long before the gate. Model-defaults surfaces synthesize their reference document from the model, which cannot be built without the table. Fixing it properly means recording table presence in the fingerprint (a golden format change) or handing the defaults document to `check_defaults_layer` separately.

**Revisit when:** a second packaged-document surface appears, or the defaults layer stops being merged beneath every boot.

## Overlapping tier globs are accepted by the registry

**Reporter:** cubic (P2, `pipelex/migration/surfaces.py:159`). **Verified:** only identical glob strings are rejected; `pipelex_*.toml` and `*_local.toml` would both load.

**Why deferred:** deciding whether two glob languages overlap is not cheap in general, and the contract's sentence — *a file claimed by two globs is a registry error* — is naturally enforced where files exist: the directory walk of `pipelex migrate`. That is Phase 3 (S6). Today's registry has one glob per surface family and none overlap.

**Revisit when:** S6 builds the walk — a file matched by two globs should stop the run by name.

## Partial golden regeneration when a later surface fails

**Reporter:** cubic (P2, `pipelex/cli/dev_cli/commands/update_migration_schemas_cmd.py:35`). **Verified:** `snapshot_registry` writes per surface, so a ledger error on the second surface leaves the first's snapshot written.

**Declined:** it is a developer regeneration tool over three surfaces whose whole output is a reviewed `git diff`; a partial state is visible there and re-running after fixing the ledger converges. A stage-then-write restructure buys nothing a `git diff` does not already show.

## `sort_keys=True` on the fingerprint JSON

**Reporter:** cubic (P2, `pipelex/migration/goldens.py:65`). **Verified:** a dict-valued default copied from the packaged TOML keeps that TOML's key order, so reordering keys inside such a value moves the golden.

**Declined:** `paths` is already sorted at compute time and the record fields are fixed. The only order-sensitive material is a default copied out of `pipelex/pipelex.toml`, and any byte change to that file is already flagged by `_check_head_defaults_document` and regenerated in the same `umig` — the "false diff" is the same event seen twice, by design.

## `strip_reserved_meta` runs before `extra_overrides` are merged

**Reporter:** cubic (P3, confidence 4, `pipelex/system/configuration/config_loader.py:342`). **Verified:** a `[meta] schema_version` passed programmatically through `extra_overrides` reaches model validation.

**Declined:** `extra_overrides` is a repository-internal programmatic layer, not a configuration file the migrator ever walks or stamps. A `[meta]` table arriving that way is a caller bug and should keep failing loudly under `extra="forbid"` rather than being swallowed.
