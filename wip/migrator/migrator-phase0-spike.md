# Migrator Phase 0 — the spike result

> Session S0 of the Migrator v3 runbook (`wip/migrator-3/sequencing.md` in the workspace-root repo). Read-only investigation: nothing in `pipelex/` was changed. Measured on 2026-08-15 against `dev` at `d2d666419` (v0.45.0 plus #1104/#1106/#1109), tomlkit 0.14.0, Python 3.12.
>
> Everything below is a measurement, not a prediction. Each one is pinned by a checked-in test in `tests/unit/pipelex/pipeline/fixes/test_fix_applier_config_surface_shapes.py`, which replaces the throwaway probe the plan carried (`wip/migrator-3/probe_tomlkit_reshape_shapes.py` in the workspace repo) — so a tomlkit bump that changes any of it fails CI instead of silently corrupting somebody's configuration file.

## The answer Phase 1 was waiting for: extend, do not widen

**Phase 1 extends the applier's op vocabulary. It does not need to widen the addressing model first.**

The charter's premise was that `table_path` might not reach what our configuration files actually contain, because `_resolve_table` walks dict-likes only. Measured across every configuration file this repository tracks, that premise does not hold: every table in every file is addressable today. The one shape the model cannot reach — an element of an array of tables — appears in exactly one tracked file, `plxt.toml`, which is not a migration surface and is not in any surface's file glob. It is also handled safely rather than dangerously: the path simply fails to resolve and the op is reported as skipped, never raised.

So the work in Phase 1 is what the plan already lists — the `FixOp` discriminated union, `move_key` and `remap_value`, the `*` wildcard, the `CONFLICT` outcome, the `ensure_table` fixes — with no addressing-model detour ahead of it.

## The charter, item by item

### The path model against real configuration files

Every table in every tracked configuration file is reachable by its `table_path`. This was measured through the public applier rather than by calling the private resolver: a `delete_key` for a key no configuration file declares always skips, and the *reason* it gives is the measurement — "table … not found in document" means the path model could not walk there, "key … not found in table …" means it could. Every table path in every file reports the latter.

The exotic shapes, each measured:

- **Inline tables are ordinary tables to the path model.** `default_templating_style = { tag_style = "xml" }` and the `quality_to_steps_maps` entries resolve and accept a rename, and the rename touches exactly the one line it should. tomlkit drops the quoting on the key it rewrites (`flux = { lowest = 14, "medium" = 28, … }`), which is harmless because the key is changing anyway.
- **Dotted-key assignments are tables.** `nested.leaf = 1` gives a real table node at `nested`, so `["section", "nested"]` addresses it, and a rename of `leaf` re-renders as a dotted key rather than exploding into a block table.
- **A quoted key containing a dot is one path segment.** `["outer.inner"]` is addressed as the single segment `outer.inner`, and a renamed key that needs quoting keeps it.
- **Arrays of tables are invisible to the model, and that is safe.** An `[[rule]]` node is a `list`, so no `table_path` reaches it or anything under it. The guarded-skip contract turns this into a report rather than a crash. No migration surface contains one; if one ever appears, the `*` wildcard has no array syntax and the ledger would need a new segment kind — a decision for that day, not this one.
- **Comment attachment is the one real limitation.** See its own section below.

### Byte-identity of an untouched round trip

`tomlkit.dumps(tomlkit.parse(text)) == text` holds for every tracked configuration file: the packaged defaults, all the kit templates, the repository's own `.pipelex/` files, and the unit-test config. Replay neutrality and the transform goldens are byte-level claims that rest entirely on this, so it is now a parametrized test rather than an assumption.

### The out-of-order table proxy

The packaged defaults document is written out of order, and this is worse than the plan recorded: **two** root tables resolve to `OutOfOrderTableProxy`, not one. `pipelex` is split into three chunks and `migration` into two, because `[pipelex.kit_config]` and `[migration.migration_maps.telemetry]` sit near the end of the file after `[cogt]` and each other. Every proxy question the plan left open is now answered, and all of them answer favourably:

- **`delete_table` works on a proxy**, both for a table nested inside one (`pipelex.log_config`) and for a whole multi-chunk proxy addressed at the root (`migration`, `pipelex`). Every chunk goes; no orphaned header is left behind; the result reparses.
- **A root-level rename of a proxy works.** Renaming `pipelex` to `interpreter` rewrote every child header across all three chunks and the content compares equal to the original subtree. This is the configuration reshape's hardest shape and it goes through `Container._replace`, a tomlkit internal — which is precisely why it now has a dedicated test.
- **Inserting a new block table into a proxy lands it at the end of the proxy's first chunk**, not at the end of the file. Inserting into a plain table lands it at the end of that table's span. Neither placement is wrong, but they differ, and `move_key`'s placement rule has to describe both.
- **`ensure_table` still emits `key = {}`**, an inline table, confirmed on a proxy as well. That is the known `.mthds` bug the plan already schedules for Phase 1; it is pinned by a test now so the fix is a visible change to an expectation rather than a silent one.

### The reshape's three shapes, and then the whole entry

The three shapes the reshape needs — a root super-table rename, a table-valued cross-parent move, and renames inside the out-of-order proxy — all behave. Rather than stop there, the spike ran **the reshape's complete ledger entry as written in `reshape.md`**, in order, with a throwaway `move_key` built the obvious way (pop the value, create missing destination parents as block tables, re-add), over the packaged defaults, the kit template, the repository's project config and override, and the unit-test config.

It works. On the packaged defaults nearly every op applies; the two that skip are the two the entry itself predicts will skip on a file that never set them (`plugins.boot_orchestrator` and the root `session_id`). The result reparses, the root tables are exactly `runtime`, `inference`, `interpreter` and `kit`, and on the sparser files each op skips or applies exactly according to what that file happens to contain. Most importantly: **replaying the whole entry over the already-migrated document applies nothing and changes no bytes**, on every file tried. Replay neutrality — the engine's central guarantee — holds against the real entry on real documents, before a line of the engine exists.

This does not retire any of Phase 2's checks; it is one witness, not the convergence check, and the ledger entry it exercised is still hand-written prose in a plan document. What it does is remove the risk that the reshape turns out to be unexpressible in the vocabulary Phase 1 is about to build.

### Repeated application and whitespace

Applying an op twice to the same DOM, and re-applying it to the reparsed output, both leave the bytes unchanged; the second application reports itself skipped because its source is gone. So the blank line the earlier probe noticed does not accumulate.

It is worth being exact about what a *first* application does to whitespace, because a migrated file will not be byte-minimal and users will notice:

- Renaming a plain root table adds one line.
- Renaming a three-chunk proxy adds four lines and **drops the table's own bare header** — the empty `[pipelex]` line at the top of the packaged file has no `[interpreter]` counterpart afterwards. A plain table keeps its bare header (`[cogt]` renames to a still-present `[inference]`). Both are semantically identical, since a parent with only sub-tables is implicit in TOML, but the asymmetry should not surprise a reviewer reading a migration diff.
- Renaming inside a proxy adds one line.

All three are stable under replay.

### Comment attachment on moved nodes — the one thing that does not work

**A comment block preceding a table does not travel when the table moves, and this cannot be fixed by being cleverer with the move.** tomlkit does not attach such a block to the table it appears to introduce; it stores it as trailing trivia of the *previous sibling*, inside that sibling's serialized string. Measured directly: in the kit template, the `# Storage Config` banner is part of `tracing_config`'s rendering, not of `storage_config`'s. Carrying it would mean string surgery on a neighbour's tail plus a heuristic for which comments "belong" to what follows.

The consequence is real and user-visible. `ensure_global_config_exists` seeds every `~/.pipelex/pipelex.toml` as a full copy of the kit template, and that template is heavily commented — a banner block per section plus per-key explanations. Running the reshape entry over it leaves the banners in place while their sections move away, so the migrated file ends up with `# Log Config` above `[inference.model_deck]` and `# Plugins` above `[runtime.storage]`. The TOML is correct; the comments now lie.

Comments *inside* a moved table are fine — the whole body travels, including trailing inline comments on individual keys. It is only the introducing banner that stays behind.

Three things follow, and they are for S1 and S4 rather than for this session:

1. **The contract must state it** (S1): a moved table arrives without its introducing comment, and comments near a move may end up labelling the wrong section. Nothing in the engine may rely on comment fidelity across a move.
2. **The reshape should not inherit the damage in the files it owns** (S4): `reshape.md` already rewrites the packaged defaults by hand and regenerates the kit template through the sync, so both come out correctly commented. That is now a requirement rather than a convenience.
3. **The `migrate` command should say so** (S6): a user whose global config was seeded from the template will see mislabelled banners, and the report is the place to tell them, since we will not be rewriting their comments for them.

### The tomlkit-bump tripwire

The existing golden byte-compare in the `.mthds` fix tests is a real tripwire but not a sufficient one for this project: it exercises `set_key` and `delete_key` on one `.mthds` fixture, downstream of the MTHDS formatter's whole-file reflow — which is exactly the step migration does not use. It would not notice a tomlkit change to proxy handling, to header re-rendering under `Container._replace`, or to comment attachment.

The recommendation is not to make the transform goldens byte-exact — `design.md` is right that they compare paths and op-written values, and a byte-exact golden over a reflowing dependency would be a maintenance tax that teaches nothing. Put the byte-level tripwire where byte-level behaviour is actually claimed:

- The characterization test added by this spike, which pins round-trip identity, proxy behaviour, the root-level proxy rename and the comment limitation against the real files.
- The convergence check (Phase 2), which replays each entry over the real reference documents and asserts the bytes do not move — the strongest byte-level signal in the project, because it runs on real documents rather than a fixture.

Together those two fail loudly on a tomlkit change; the transform goldens stay parsed-level, as designed.

## What this changes downstream

Nothing in the plan needs restructuring. Three items get sharper:

- **S1, the contract.** Add: arrays of tables are unaddressable and reserved (no `table_path` segment syntax reaches them, and no surface has one today); a moved table loses its introducing comment; a migration is not byte-minimal — expect small whitespace growth and possibly a dropped empty parent header; and the placement rule needs both halves measured here (a created root parent lands at the end of the file, while a table inserted into an existing out-of-order parent lands at the end of that parent's first chunk).
- **S2, Phase 1.** No addressing work. The `ensure_table` block-table fix now has a failing-on-change expectation waiting for it in the new test module.
- **S4, the reshape.** The hand-written packaged defaults and the regenerated kit template are the mechanism that keeps our own files correctly commented; the entry as written in `reshape.md` needs no changes — it was executed end to end here.
