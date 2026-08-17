---
name: add-migration
description: >
  Write a migration ledger entry for a configuration schema change in pipelex, so
  that a user's existing file can be repaired instead of thrown away. Use when
  `make check-migration-schemas` (alias `cmig`) or `make check-ledger` (alias `cl`)
  refuses a change, when the user says "add a migration", "write the ledger entry",
  "the coverage gate is failing", "bump the schema version", "migration entry",
  "the migration gate won't let me", "account for this schema change", or after any
  edit to a configuration model that removed a key, renamed one, moved one, retired
  an enum member, or tightened what a value may be. This is the only skill that
  writes a ledger.
---

# Add a Migration Entry

A configuration **surface** — `pipelex.toml` and its tiers, `telemetry.toml`,
`pipelex_service.toml`, the inference backend definitions in
`inference/backends/` — ships a checked-in ledger at
`pipelex/migration/ledgers/<surface-id>.toml` recording, as data, every shape
change it has ever undergone. A user's existing file is repaired by replaying that
ledger over it, so a schema change with no entry is a schema change that breaks
every machine in the field.

`docs/migration-ledger.md` is the normative contract. **Read it before writing an
entry** — this skill is the procedure, that document is the law, and where the two
disagree the contract wins.

## The one rule

**Derive the entry from the gate's refusal, never from memory.** The coverage
check recomputes the surface's fingerprint and names every path, every enumerated
spelling and every value domain the change moved. That output is the fingerprint
diff, already rendered. Composing an entry by hand from your own reading of the
diff is how a rename gets misspelled and every user's file is migrated onto a key
the schema rejects, with the tool reporting success.

## Step 1: See what the gate says

`make check-migration-schemas` (alias `cmig`) is deliberately **not** in
`make agent-check` — it is a golden check, and a fail-regenerate-fail cycle in the
loop agents run constantly is how a gate goes permanently green while catching
nothing. So run both gates explicitly:

```bash
make cl      # check-ledger: is the ledger legal, and is replaying it harmless?
make cmig    # check-migration-schemas: is every schema change accounted for?
```

Each failure names the surface and a `kind`, and every message says what to do. The table below is not the whole list of kinds — it is the map of which ones mean **an entry is owed**, and what it owes:

| Kind | What the change did | What the entry owes |
|---|---|---|
| `removal_needs_a_bump` | a path, an enumerated spelling or a value domain is gone from the models but still in the head golden | a version bump plus the operation that removes or repairs it |
| `unaccounted_path` | a path the diff removed that no operation in the entry acts on | an operation naming that path |
| `enum_member_not_remapped` | an enumerated spelling disappeared | a `remap_value` from the old spelling to the new one |
| `value_domain_narrowed` | the type or a bound got stricter — nothing was removed, but a legal value stopped being legal | a `remap_value` per narrowed path, or an `unsafe` entry naming them in `declared_narrowed_paths` |
| `dead_op` | an operation whose source no schema version ever removed, or a `delete_table` pointed at a key | fix the path or the kind — the applier would skip it forever while looking like an accounting |
| `destination_occupied` / `destination_not_in_new_shape` | an operation's destination is wrong | fix the destination — this is usually a typo, and it is the defect the transform goldens exist to catch |
| `over_deletion` | the entry removes a path the schema still has | narrow the operation; a parent is deleted only when the parent itself retires |
| `required_path_without_default` | an added required path has no value in the defaults layer | give it a default — an added key is absorbable only because the defaults layer carries it |
| `snapshot_pending` / `fingerprint_drifted` | the goldens predate the models | usually just step 5; if it is the only failure, no entry is owed |
| `reserved_path_reused` / `reserved_value_reused` | the new name was retired by an earlier version | **pick another name** — see step 4 |
| `convergence_broken` | replaying the ledger over a healthy reference document is not a no-op | the operation acts on live material, or on the wrong path |

**A gate that only asks for a regeneration is not asking for an entry.** An
additive change — a new optional key, a widened type, a relaxed bound — costs a
`make umig` and nothing else. Stop at step 5 in that case.

## Step 2: Decide the safety

`safety` governs whether the applier may act, and it is not a matter of taste:

- **`safe`** — the operations mechanically complete the repair. The file is
  rewritten after one confirmation. Everything structural is safe: renames, moves,
  deletions, and a `remap_value` whose old spelling is genuinely no longer legal.
- **`unsafe`** — no operation in the vocabulary can repair the file, so the entry
  is *reported and never applied*. This is the form for a tightened numeric bound,
  a completeness rule a validator expresses, anything where the tool would have to
  choose a value on the user's behalf.

An `unsafe` entry may legitimately carry no operations at all — and then
`declared_narrowed_paths` is **mandatory**, because the engine questions a
document before reporting an entry, and an entry with neither operations nor a
declaration answers "nothing to say" for every file there will ever be. The
declaration is spelled as the fingerprint at the entry's own version records the
paths, `*` segments included, and `make cl` refuses a path that version does not
have.

`guidance` is independent of `safety`: any entry may carry it, and it is the
explanation a person reads, **never the mechanism**. Anything expressible as
operations must be operations.

## Step 3: Write the entry

Two edits to `pipelex/migration/ledgers/<surface-id>.toml`, in one change:

1. In `[surface]`, raise `current_schema_version` to N.
2. Append a `[[migration]]` block. Entries are contiguous and named for their
   version — the id **must** be `<surface-id>@<N>` and `to_schema_version` **must**
   be N, or the file is refused when it is parsed.

```toml
[[migration]]
id                = "example-config@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "safe"
title             = "Short imperative summary of the shape change"
description       = "One or two sentences a release note can quote."
guidance          = """
What a user should understand or decide. Never the mechanism.
"""

[[migration.ops]]
kind       = "rename_table_key"
table_path = ["reporting"]
key        = "output_config"
new_key    = "output"
```

`introduced_in` is orientation only — nothing branches on it. A breaking entry
ships in a **minor** bump per the house convention, so write the next minor above
the current `pyproject.toml` version. `/release` step 3b confirms it against the
version actually being cut.

The operation vocabulary is structural only — `rename_table_key`, `move_key`,
`delete_key`, `delete_table`, `remap_value`. There is deliberately no operation
that writes a value into a user's file; one would be refused when the ledger is
parsed. `docs/migration-ledger.md` → "The operation vocabulary" has each kind's
fields, the `move_key` placement rule, and what the `*` wildcard segment means
(and where it is legal, which is only at an open node — and as a `remap_value`
key, which is the one shape that can repair a member renamed beneath an open
mapping).

**Operations target the narrowest path that expresses the change.** A ledger entry
is permanent data that outlives the current field census of its parent table, so
deleting a parent because it happens to hold one field today is wrong — unless the
parent itself is what retires, in which case its name becomes reserved too.

## Step 4: When the reserved-path rule fires

`make cl` refuses a name an earlier version retired:

> schema version 4 has 'reporting.output' again, but schema version 2 retired it —
> a retired path stays retired, because reusing the name makes removed material
> legal again. Pick another name

There is no escape hatch and there should not be one. Propose a replacement to the
user, and propose a *good* one: prefer a name that reads naturally for what the
field now means over a decorated variant of the retired one (`output_target`, not
`output_v2` or `output_`). The same rule applies to enumerated spellings — a value
a `remap_value` moved away from can never come back.

Renaming the field means changing the model, so the fingerprint moves again: go
back to step 1 rather than patching the entry.

## Step 5: Regenerate the goldens

```bash
make umig
```

This writes `fingerprint@N.json` and `defaults@N.toml` for every surface, at the
version its ledger now declares. Older versions are never rewritten — they are the
frozen history the chain is made of — and the new version's files are new files,
so nothing is erased.

**Read the diff.** It is the only signal this command produces: line by line,
which paths the change added, removed or renamed. Running `umig` without reading
its diff throws that away.

**If `umig` refuses**, it is the guard doing its job: you are about to overwrite a
head golden that records material the models no longer have, which would erase
exactly what the coverage gate exists to catch. Read what it names. Almost always
the answer is that step 3 has not happened yet — bump the version and write the
entry, and the refusal disappears because there is no stored golden at N to erase.
`make umigf` is **not** the general escape: it is for one situation only, a golden
that predates a change to the fingerprint *format* over a schema version that has
not been released. Never hand-edit a golden.

## Step 6: Prove it

```bash
make cl && make cmig
```

Both green means three separate claims hold: the entry is legal and replaying it
over a healthy file changes nothing (`cl`), every path the change moved is
accounted for, and — the transform goldens — the operations *actually perform* the
migration from `defaults@N-1` to `defaults@N`, and the migrated document is
accepted by the current model.

Then the usual gates: `make agent-check`, and `make agent-test` before wrapping up.

## Step 7: The changelog

The ledger and the changelog are deliberately separate artifacts saying the same
thing to different readers, and `/release` step 3b is where they are checked
against each other. For each entry with `breaking = true`, add a bullet to
`## [Unreleased]` beginning with the literal label:

```markdown
- **Migration:** `telemetry-config@2` lifts the flat first-generation telemetry
  file into today's `[custom_posthog]` section, keeping every value the user
  chose. Four settings the current shape has no home for are dropped, and the
  entry says which and why. Run `pipelex migrate`.
```

House style: a bold label, then two to four complete sentences. Say what moved and
what a user has to do; do not restate the operation list.

## Special case: a change that predates the first fingerprint

An entry may carry `pre_history = true` when the change it describes happened
before the surface had a fingerprint, so no diff accounts for it. Such an entry
declares its own `declared_removed_paths` (an empty declaration is refused), none
of those paths may appear in any fingerprint at or below its version, and it ships
a hand-authored `goldens/<surface-id>/before@N.toml` so the transform check has a
pair to verify. This is rare and it is not a way past the gate — reach for it only
when there genuinely is no diff, and read
`docs/migration-ledger.md` → "Pre-history entries" first.

### Inserting a pre-history entry *below* entries that already exist

The change you are accounting for may be older than an entry already in the
ledger — a key that moved before a later entry renamed the table it lived in. The
new entry then has to run **first**, because its operations address the historical
spelling, so it takes a version the ledger already uses and everything above it is
renumbered. Ids, versions and `current_schema_version` are forced to agree, so
this is one atomic edit, and the goldens move with it:

1. Insert the entry at `@N` and renumber every entry above it (`@N` → `@N+1`, and
   so on); bump `current_schema_version` to the new top.
2. `git mv goldens/<surface-id>/fingerprint@N.json fingerprint@N+1.json`, and the
   same for `defaults@N.toml`. Repeat upwards, highest first.
3. **Copy** `fingerprint@N-1.json → fingerprint@N.json` and
   `defaults@N-1.toml → defaults@N.toml`. A pre-history entry's fingerprint pair
   must show no diff at all, and a copy makes that true by construction rather
   than by luck.
4. **Hand-edit one line per moved or copied fingerprint: the `"schema_version"` in
   its body.** A golden whose body disagrees with its filename is refused when it
   is read, and `make umig` reads the stored head *before* it writes anything — so
   a fingerprint still saying `N` under the name `@N+1` makes `umig` raise instead
   of regenerating. This is the one sanctioned exception to "never hand-edit a
   golden", and it is bounded to that single line.
5. Hand-author `goldens/<surface-id>/before@N.toml` for the new entry.
6. Run `make umig`. **It must be a byte-pure no-op on everything the moves
   produced** — verify with `shasum -c` over the directory, or by diffing each
   moved golden against its pre-move self in `HEAD` and finding only the version
   line. That no-op *is* the proof the renumber was pure; any other diff is a
   finding, not something to regenerate around.
7. Sweep the tree for the old id (`git grep -n '<surface-id>@N'` across
   `pipelex/ tests/ docs/ CHANGELOG.md .claude/`). Every hit is either the new
   entry or a stale quote of the renumbered one; there is no third kind. Where a
   test or a docstring named a golden by version but meant "the shape before the
   change", make it say so rather than bumping the number — the construct is what
   goes stale, not the value.
8. Both ids need a changelog mention: a renumber otherwise reads as a new breaking
   entry that nobody wrote a bullet for.

## What this skill must never do

- **Never hand-edit a fingerprint or defaults golden**, with the single exception
  of the `"schema_version"` line during a renumber, above. They are generated; the
  generator is `make umig` and the diff is the review artifact.
- **Never make a gate green by widening it.** If a check refuses the change,
  either the change owes an entry or the check found a real defect. Editing the
  check is a separate decision with its own review.
- **Never reuse a retired path or spelling** to make the reserved-path rule quiet.
- **Never invent a value.** A `remap_value` mapping carries the new spelling of an
  old one — a translation the user's own file determines, which is why it can be
  `safe`. What no operation may do is write a value the file does not already fix:
  a default, or a replacement for a value a tightened bound now refuses. If the
  repair needs one of those, the entry is `unsafe` and a person makes the choice.
