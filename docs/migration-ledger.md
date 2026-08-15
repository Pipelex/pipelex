# The Migration Ledger

Pipelex configuration files live on users' machines and in users' repositories, and the models that read them keep changing shape. A **migration ledger** is the checked-in record of every shape change a configuration surface has ever undergone, written as data rather than as code, so that a stale file can be repaired mechanically instead of deleted and re-initialized.

This page is the contract: what a ledger may contain, what the engine may do with it, and what is guaranteed to a user whose files are migrated. It is normative. Everything asserted here has, or will have, a test behind it, and where a rule exists to prevent a specific failure the failure is named — a rule whose reason is forgotten is a rule that gets relaxed.

> **Status.** This specification was written before its implementation, deliberately: the guarantees below are what the engine is built against. The data format, the operation vocabulary and the checks land first; `pipelex migrate` and boot tolerance land last. Until the commands exist, this page is built but kept out of the documentation navigation.

## What migrates, and what does not

A **structural** change is a key renamed, moved or removed, or an enumerated value renamed. It breaks a user's file: the model rejects it, and no amount of re-reading helps. That is what the ledger describes and what the engine repairs.

A **content** change is a value or an entry in a package-managed file that should track the package — a new inference backend, a changed default in the model deck. Those files are not broken, they are behind, and merging them without destroying the user's customizations is a different problem with different machinery. Content sync is out of scope here and is not described by this contract.

Everything else this document deliberately does not specify: the language surface (`.mthds` files and the MTHDS standard version), plugin-owned ledgers, and the promotion of this contract into a cross-repository specification. Each is a project of its own, and specifying it in advance would freeze decisions nobody has had to make yet.

## Surfaces

A **surface** is one artifact family with one schema version and one ledger. The in-scope surfaces are the configuration surfaces the `pipelex` package owns:

| Surface id | Base file | Tier files | Model | Defaults layer |
|---|---|---|---|---|
| `pipelex-config` | `pipelex.toml` | `pipelex_*.toml` | `PipelexConfig` | Packaged document (`pipelex/pipelex.toml`) |
| `telemetry-config` | `telemetry.toml` | `telemetry_override.toml` | `TelemetryConfig` | Model defaults |
| `pipelex-service-config` | `pipelex_service.toml` | — | `PipelexServiceConfig` | Model defaults |

File names are relative to a configuration directory, and every surface spans exactly two of them: the global `~/.pipelex/` and the project's `.pipelex/`. `pipelex migrate` walks both, and only those. Two paths that look like configuration are outside the walk by design: the unit-testing tier `./tests/pipelex_{run_mode}.toml`, and any file reached through an explicit `load_config(config_dir=…)`, which is a repository-internal mechanism rather than a user's configuration.

The tier set is **open**. Environment and run-mode names are dynamic, so the tier filenames of `pipelex-config` cannot be enumerated in advance — `pipelex_local.toml`, `pipelex_{environment}.toml`, `pipelex_{run_mode}.toml`, `pipelex_override.toml` and `pipelex_temporary_override.toml` are a description of today, not a closed list. That is why the registry matches tiers with a glob, and the glob is what makes the resolution rule necessary:

> **Exact filenames claim before globs, across all surfaces.** A file matched by any surface's exact pattern belongs to that surface and is excluded from every surface's glob. A file claimed by two globs, or by two exact names, is a registry error and is rejected when the registry loads.

Without the rule, `pipelex_service.toml` is both the base file of one surface and a match for another's `pipelex_*.toml`, and which ledger runs over it becomes an accident of iteration order.

Each surface also declares its **defaults-layer kind**, because the checks need to know where a current-schema default value comes from: a packaged TOML document merged beneath the user's files, or model-level field defaults. The distinction matters twice — for synthesizing the complete reference document of a surface that has no packaged file, and for refusing an added path that has no default anywhere.

Every surface starts at `schema_version = 1` with an empty ledger. There is no retroactive numbering of changes that predate the ledger; the one case that genuinely needs to reach backwards has its own bounded mechanism, described under [pre-history entries](#pre-history-entries).

## The defaults layer, and why additive changes never migrate

Every in-scope surface has a **defaults layer**: a source of current-schema values that sits beneath the user's files and cannot be stale, because it ships with the package. The consequence is the rule that keeps the whole vocabulary structural:

> **A key we add is supplied by the defaults layer, so an old file that lacks it still validates and still behaves correctly. An additive schema change cannot break anyone, and therefore never has a migration operation.**

The inverse is worth stating with equal force, because it is the tempting mistake. Writing a default value into a user's file is not a neutral repair: it converts an *inherited* value into an *explicitly set* one, pinning it against every future change to that default and changing what the merge produces. That is a semantic edit dressed up as a fix. It is why the materializing operations are excluded from the migration vocabulary outright rather than restricted to some class of files — every user file overrides the packaged defaults, base files included, so an argument that keeps materialization out of an override tier keeps it out of everything.

**If a surface ever appears to need an additive migration, the defect is a missing defaults layer on that surface, and the fix is to give it one.** The rule is enforced rather than trusted: the coverage check refuses an added path that has no value in its surface's defaults layer, and names the only remedy the vocabulary allows.

## Schema versions, and why every run replays everything

Each surface carries a monotonic integer, bumped only when its shape changes. Integers rather than semantic versions, because a schema either changed or it did not. Each entry also records the package version that introduced it, for orientation against the changelog only — nothing branches on it.

Migration is **file-level**. The merged configuration cannot answer "what version is this file at", because the effective value of any key comes from whichever tier wrote last. Every migration reads, plans and rewrites one file at a time, upstream of the loader's deep merge, and tier files are migrated as ordinary members of their surface.

> **No version record ever causes work to be skipped.** Every run plans the full ledger for the surface, and the applier skips each operation whose target is already gone or whose change is already present.

The reasoning is worth keeping. Any side record of "what has already been applied" is untracked state sitting next to files that git, restores, branch switches and copies move independently of it. Anything that skips work based on such a record will eventually report "nothing to do" at the exact moment a user's boot is broken — the worst failure this tool can have. And since the record can never be allowed to cause a skip, it has no remaining reader:

> **There is no state stamp.** No state file, no per-file bookkeeping, no state-transition rules. The report describes what this run observed and did, which it knows exactly, rather than what some earlier run claims to have done.

Two reservations exist so that later projects stay free:

- **`[meta] schema_version`** is a reserved optional in-file key. Every configuration-surface reader tolerates it and strips it before validation; **nothing writes it**. The reason not to write it is not release compatibility, which our principles disclaim, but team skew on tracked files: base configuration files under a project's `.pipelex/` are shared through git right now, so one developer on a newer pipelex writing the key would break a teammate on last week's build the same afternoon.
- **`min_supported_schema_version`** on the surface block, held at zero until a ledger squash ever moves it. Without the floor, a squash silently under-migrates the oldest files in the field, because the applier skips absent targets and reports success. With it, the loader fails loudly instead.

### The downgrade direction

Always-replay covers files *older* than the running pipelex. The same branch switch that motivates it also produces files *newer* than the running pipelex: an untracked override migrated on one branch, then an older branch checked out or the package downgraded. The older model rejects the newer key, and replay finds nothing to do, because every operation's source is absent.

Under the no-backward-compatibility principle this is not repaired, but it must be **named**, because "nothing to do" beside a dead boot is precisely the failure this project exists to kill:

> When validation fails on an unknown path that no ledger entry removes, the report says so: the path is either a typo or was written by a newer pipelex than this one, and the message asks whether the user is on an older branch or build.

That diagnosis is computable from the ledger alone and needs no stamp.

## Replay neutrality

This is the central guarantee, and everything else in the contract exists to keep it true:

> **A full replay of a surface's ledger over any file already valid at the current schema is a byte-level no-op.**

Note the domain. It is not "over the packaged defaults" or "over the template" — it is every document the current models accept, including files carrying values no template ever contains. A witness document can never stand in for that domain, because it carries exactly one value per key.

The guarantee is a theorem, from two premises.

**Premise one: every migration operation's precondition mentions only removed material.** The vocabulary is purely structural — each operation acts only when its source path is present, and every source path is one that some schema version removed. A file valid at the current schema cannot contain a removed path, because the configuration models are `extra="forbid"`, so every operation skips. Two static rules make this mechanical rather than argued: [op legality](#op-legality) and the reserved-path registry, which guarantees that "removed" is permanent — a removed path is never reintroduced with a new meaning that would make it legal again.

**Premise two: the remap legality rule.** A `safe` `remap_value` is legal only when its target path is enum-typed at the current schema and every old value in its mapping falls outside the current member set. Then a current-valid file cannot carry a mapped value, and the remap skips. When an old spelling remains legal — or the path is a free string, where staleness can never be proven from the schema — the entry must be `unsafe`: the migration still exists and is still reported, but it is never applied automatically, because the applier cannot distinguish a stale value from a deliberate choice.

With both premises every operation in a full replay over a current-valid file skips; skipping mutates nothing, and [serialization adds nothing](#serialization-adds-nothing), so the output is byte-identical.

The theorem is checked anyway, twice, because proofs rot where code does not:

- **The convergence witness.** A full replay over each of a surface's reference documents — the complete defaults document and the sparse kit template — must produce zero applied operations. Both are at the current schema by construction, so there is no fixture to maintain. Cheap and exact; it runs in `agent-check`.
- **The neutrality property test.** Generated documents that are valid at the current schema — mutations of the packaged defaults within the schema: other enum members, deleted optional keys, altered scalars, tier-shaped sparse subsets — must replay to byte-identical output. This is the executable form of the theorem over the domain the theorem actually claims. It carries a **vacuity meta-test**: every generated document must validate against its surface's model, or the property is passing on garbage.

Two further properties hold and are tested with it: replay is **idempotent** (applying a ledger twice equals applying it once) and **prefix-coherent** (a file that has already absorbed some entries lands where a replay from zero lands).

## The ledger file

One checked-in TOML file per surface, shipped inside the package that owns the schema, at `pipelex/migration/ledgers/<surface-id>.toml`.

**The ledger is data and never code.** The checks must reason mechanically about what every entry does — which paths it removes, which values it remaps, whether replay converges — and executable steps defeat every one of those checks.

The example below is illustrative — it shows every part of the format on a surface that does not exist. A surface's real entries live in its own ledger file.

```toml
[surface]
id                           = "example-config"
title                        = "An example configuration surface"
base_file                    = "example.toml"
tier_glob                    = "example_*.toml"   # exact names of other surfaces are excluded by the resolver
current_schema_version       = 2
min_supported_schema_version = 0

[[migration]]
id                = "example-config@2"
to_schema_version = 2
introduced_in     = "0.46.0"      # the package version that carries this entry; orientation only
breaking          = true
safety            = "safe"
title             = "Short imperative summary of the shape change"
description       = "One or two sentences a release note can quote."
guidance          = """
Agent-facing Markdown: what a user should understand or decide. Never the mechanism.
"""

[[migration.ops]]                 # rename a nested table in place, inside its parent
kind       = "rename_table_key"
table_path = ["reporting"]
key        = "output_config"
new_key    = "output"

[[migration.ops]]                 # move a table-valued key to a parent that has to be created
kind           = "move_key"
table_path     = ["reporting"]
key            = "retention"
new_table_path = ["storage"]
new_key        = "retention"

[[migration.ops]]                 # retire a whole section, and with it its top-level name
kind       = "delete_table"
table_path = ["legacy_reporting"]
```

The rules that govern the file:

- **Entries are ordered by `to_schema_version` and replayed in that order.** Versions are contiguous and match their ids. A key renamed at version 2 and moved at version 4 lands correctly for a file coming from version 1, because the entries compose in sequence.
- **`safety` and `guidance` are independent.** `safety` governs whether the applier may act: `safe` means mechanically complete and applied after one confirmation, `unsafe` means reported and never applied. `guidance` is prose any entry may carry, whatever its safety.
- **`guidance` is the explanation, never the mechanism.** Anything expressible as operations must be operations. An entry may legitimately carry no operations at all with `safety = "unsafe"`, for a change only a human can make.
- **Operations target the narrowest path that expresses the change.** A ledger entry is permanent data that outlives the current field census of its parent table, so deleting a parent because it happens to have one field today is wrong — unless the parent itself is what retires, in which case the entry deletes the parent and the parent's name becomes reserved.
- **The parsed ledger is cached per process.** Replaying a surface over many files must not re-parse the TOML per file.

### Pre-history entries

A removal that predates the first fingerprint has no observed diff and no snapshot to compare against. Such an entry may carry `pre_history = true`, in which case it **declares its own removed paths** — the reserved-path registry records them from the declaration rather than from a fingerprint diff — and ships a hand-authored `before` document so the transform check has a pair to verify. Convergence and neutrality then verify it exactly like any other entry.

This exception is bounded to entries carrying the flag, and exists for the changes that shipped before the ledger did. It is not a way to avoid a fingerprint diff for a change that has one.

## The operation vocabulary

The ledger draws on the same operation vocabulary as the `.mthds` fix path, restricted to its structural half. The full union is published as two subsets — **fix operations** (every kind) and **migration operations** (the structural kinds only) — so a ledger containing a non-migration kind fails validation when the ledger is parsed, not later at gate time.

| Kind | In a ledger? | What it does |
|---|---|---|
| `set_key` | **no** | Writes unconditionally. Correct when derived from a typed error about that exact key; wrong under replay, where it would overwrite a user's chosen value on every run. |
| `ensure_table` | **no** | Materializing — absorbed by the defaults layer. |
| `ensure_key` | **no** | Does not exist, and is not built: additive changes never migrate. |
| `delete_key` | yes | Drops a retired key. |
| `delete_table` | yes | Drops a retired section, including every chunk of a table written out of order. |
| `rename_table_key` | yes | Renames a key, or a nested table, in place within its parent. Position is preserved. |
| `move_key` | yes | Relocates a key across tables, optionally renaming it. The moved key may be table-valued, in which case the whole subtree travels. Missing destination parents are created as block tables as part of the operation. |
| `remap_value` | yes | Rewrites a value against an explicit old-to-new mapping, and does nothing when the current value is not in the mapping. `safe` only under the remap legality rule. |

Every operation carries a `table_path`: a list of segments naming the table it acts in, empty for the document root. `delete_table` needs nothing more — its `table_path` *is* its target. Every other kind adds the `key` it acts on, and then whatever its own semantics require: `rename_table_key` a `new_key`, `move_key` a `new_table_path` and a `new_key`, `remap_value` a `mapping` of old value to new value. Each kind declares exactly its own fields, so an entry that names a field the kind does not have is refused when the ledger is parsed.

### `move_key` placement

Moving a key changes its address, and a file has to put the moved material somewhere. The rule, measured against the TOML library rather than assumed:

> **Position is preserved within a parent, never across parents.** A destination parent that already exists receives the moved key at the end of that parent's span — and, when the parent is written out of order across several chunks of the file, at the end of its *first* chunk. A destination parent that has to be created lands at the end of the file.

Both halves are deliberate and neither is wrong, but they differ, and a reviewer reading a migration diff should not be surprised by either.

### The wildcard segment

Some configuration nodes are **open dictionaries** — fields typed as a mapping from arbitrary keys to a value schema, where any key is legal, no fingerprint can enumerate the keys, and `extra="forbid"` says nothing. The keys under such a node belong to the user; the value schema belongs to us. So the fingerprint records value-schema paths beneath a `*` segment, and an operation may use `*` **exactly at an open node**, where the applier expands it over the keys the file actually contains. A field renamed inside every entry of an open mapping, or an enum member remapped across every value of one, is then an ordinary `safe` operation rather than an impossibility.

### Outcomes

The applier reports one outcome per operation:

| Outcome | Meaning |
|---|---|
| `APPLIED` | The file changed. |
| `SKIPPED` | Nothing to do — the target is absent, or the change is already present. |
| `CONFLICT` | The change cannot be made without choosing on the user's behalf. |

`SKIPPED` is the overwhelmingly common outcome under always-replay and is entirely benign; reports suppress it. `CONFLICT` is not benign and must never travel inside `SKIPPED`: it is returned when a rename or move destination is already occupied, typically because a user hand-fixed part of their file. A conflicting step writes nothing, routes into the plan's `blocked` list with the path and both names, and never undermines replay neutrality — a document carrying both names is by definition not valid at the current schema.

> **Outcomes are classified by the outcome enum, never by parsing a detail string.** Messages are presentation and are free to change; the outcome is the contract.

## Legality rules

The guarantees above hold only if entries cannot say certain things. These rules are checked statically, before any file is touched.

### Op legality

- **Every operation's source must be a path some schema version removed** — recorded as such in the reserved-path registry by the entry that removes it. An operation whose source is still a live path of the current schema would act on a valid file, and replay neutrality would be false.
- **No operation may address a concrete key beneath an open node.** Those keys are the user's, they are unbounded, and no schema change can remove one.
- **A `*` segment is legal exactly at an open node**, and nowhere else.

### Sequential path state

Legality is defined over an entry's **sequential path state**, not operation by operation in isolation. An entry's operations chain: a parent is renamed and then keys inside it are renamed, so the intermediate paths belong to neither the old fingerprint nor the new one. The check therefore walks the previous fingerprint's path set through the entry's operations symbolically, and requires that each operation's source exists in the state at that point, that each operation's *final* destination is a path of the new fingerprint, and that the end state equals the new fingerprint minus its additions.

No ordering avoids the intermediate state — a nested rename under a moved parent produces one however the operations are sorted — so this is a property of the checker, not a constraint on authors.

### Destination cross-check

Every rename and move destination is cross-checked against the paths the fingerprint diff records as **added**. A rename to a name the current schema does not know is refused at the gate, with the mismatch named. Without the cross-check, a misspelled destination passes both coverage and convergence — the removed path is accounted for, and over a current document the source is absent, so the operation skips — and then migrates every user file to a key `extra="forbid"` rejects, with the tool reporting success.

### Reserved paths and names

The **reserved-path registry** is an append-only record of every path, and every remapped-away enumerated value, that a ledger entry has ever removed. Reuse is refused outright, with no escape-hatch marker: an author who hits the rule picks another name.

The registry is diagnostic as much as preventive. When convergence or a transform golden fails, it is what turns the failure into a sentence naming the path and the schema version that reserved it.

> **A retired top-level table name is reserved permanently** (until a ledger squash, which drops entries and the reservations they own together). Reuse would make a removed path legal again and break premise one of replay neutrality directly.

## The fingerprint

The fingerprint is a normalized projection of a surface's model tree, checked in as a golden and recomputed on every pull request. Per TOML-addressable path it records:

- the type;
- whether the path is required;
- the enum member set, where the type is enumerated;
- the value in the surface's defaults layer, where one exists;
- an open-node marker, with the value-schema paths beneath it recorded under a `*` segment.

It is serialized in a stable order and is **deliberately not raw `model_json_schema()` output**, which moves for reasons that have nothing to do with our schema — reference layout, titles, ordering, the validation library's own version. A gate that cries wolf gets regenerated reflexively, and that is how a gate dies.

What each recorded field is for: requiredness and enum members are load-bearing for coverage and for remap legality; defaults are recorded so that a flipped default is *visible in the regeneration diff*, but a default value **never gates on its own** — it changes no shape and no operation can address it. The one place a default is decisive is an added path that has none, which is breaking.

## The checks

Checks with distinct failure meanings, so that a red gate says which guarantee broke. Placement follows the house rule: anything that regenerates and diffs lives in `make check` only, and anything with one obvious fix per failure joins `make agent-check`.

### Coverage — every schema change is accounted for

Recompute the fingerprint and diff it against the golden:

| Diff | Verdict |
|---|---|
| Unchanged | Pass. |
| Paths or enum members added only | Regenerate the golden. No version bump and no entry are demanded, because additive changes are absorbed by the defaults layer — **unless** an added path has no value in its surface's defaults layer, which is breaking and is refused with "give it a default". |
| Any path or enum member removed or renamed | Require a schema version bump, an operation accounting for every removed path (wildcard paths included), and a remap or an `unsafe` entry for every removed enum member. Destinations are cross-checked against added paths. |

> **There is no escape hatch.** No `no_migration_needed` marker exists. A path that was never shipped to anyone still carries a one-line `delete_key`, which always skips and costs nothing — because "this one does not need an entry" is a judgment the next person cannot re-derive, and one such marker teaches everyone that the gate is negotiable.

### Convergence — replay is neutral on the witnesses

A full replay of a surface's ledger over each of its reference documents produces zero applied operations. The same target checks what else is cheap and unambiguous: the ledger parses into the migration-operation subset, versions are contiguous and match ids, every `safe` remap satisfies the legality rule, and no entry reintroduces a reserved path.

### Transform goldens — the operations say what the schema change did

Coverage proves an entry *exists* for every removal. Convergence proves replay is *harmless* on current files. Neither proves the entry is *right*, which is what the transform goldens close.

When a surface bumps to version N, the regenerator freezes the reference documents and the fingerprint as `defaults@N`, `template@N` and `fingerprint@N`. The check then asserts, pairwise over the complete-defaults family:

> `paths(apply(entry N, defaults@N−1)) == paths(defaults@N) − added_at_N`, where `added_at_N` is `fingerprint@N` minus `fingerprint@N−1`; plus value equality on every path an operation wrote; plus validation of the last link against the current model.

The comparator is **not byte-exact and not a subset test**, and both exclusions are deliberate. Byte-exactness fails on any honest version bump, because the same commit adds keys, edits comments and flips unrelated defaults. A subset test is blind to over-deletion — deleting a parent table where the entry meant to delete one child would pass. What survives is a comparator that tolerates additions, comment edits and default flips, and is red on wrong destinations, wrong remap targets, wrong order and over-deletion.

The sparse kit template is **not** in the chain: starter-template edits between bumps would go red under equality, and it exercises no operation the complete document does not. It remains a convergence and neutrality witness.

Pairwise checks compose by induction into the full chain — a replay from any historical snapshot lands on the current shape, because prefix entries skip on any snapshot at or past their version, their sources being permanently removed material.

### Testing the gates without coupling them to the configuration models

The surface registry is an **injected parameter, never a module constant**. The gates' own tests point it at small synthetic models with fixture ledgers, fixture fingerprints and fixture golden chains, so gate *behaviour* is tested against something that never moves; a single smoke test asserts that the real registry loads, the real goldens match and the real convergence holds.

Without this, every legitimate configuration change turns the gate's own suite red alongside the gate, and the fix everyone learns is "regenerate the goldens" — which is how a gate goes permanently green while catching nothing.

### The targets, and where the data lives

| Target | Alias | Aggregates | What it does |
|---|---|---|---|
| `make check-ledger` | `cl` | `check`, `agent-check` | The ledger parses into migration operations, versions are contiguous and match ids, legality and remap legality hold, no entry reintroduces a reserved path, and replay over both reference documents applies nothing. Reads checked-in data and regenerates nothing. |
| `make check-migration-schemas` | `cmig` | `check` | Fingerprints every surface, diffs against the goldens, demands a bump and full accounting for every removal, cross-checks destinations, and verifies the pairwise transform-golden chain. |
| `make up-migration-schemas` | `umig` | `up` | Regenerates the fingerprint goldens, and snapshots the reference documents into the transform-golden chain when a schema version bumped. |

Only `check-ledger` joins `agent-check`: it regenerates nothing and each failure has one obvious next action. `check-migration-schemas` is a golden check, and in the loop agents run constantly it would produce a fail-regenerate-fail cycle with no single right answer, so it stays in `check` alone.

The checked-in data it all reads:

```
pipelex/migration/ledgers/<surface-id>.toml     the ledgers
pipelex/migration/schemas/<surface-id>.json     fingerprint goldens and the reserved-path registry
pipelex/migration/goldens/<surface-id>/         the transform-golden chain: defaults@N, template@N, fingerprint@N
```

## What the engine reports

Every surface produces the same plan model:

```
MigrationReport
  └── MigrationPlan (per file)
        surface, file_path
        blocked_reason → set when the file itself could not be processed at all
        steps[]        → id, to_schema_version, title, breaking, safety, ops[], changelog
        blocked[]      → id, reason, guidance
        unexplained[]  → path, note
```

There is no `from_version` and no trusted-version concept: nothing skips, so nothing needs one. Because a replay walks every entry while usually changing little, the report renders what actually changed — it filters on `APPLIED`, routes `CONFLICT` into `blocked`, and carries the downgrade diagnosis in `unexplained`.

Two different things can be blocked, and the report keeps them apart. An **entry** is blocked when it cannot be applied — it is `unsafe`, or one of its operations came back `CONFLICT` — and it lands in `blocked[]` with the reason and its guidance, while the rest of the file's entries proceed. A **file** is blocked when it cannot be processed at all: it is unparseable, it is unwritable, or it changed on disk between the read and the write. That reason sits on the plan itself, and a blocked file never stops its siblings — every other file in the surface is migrated and reported normally.

> **No value read from a user's file is ever rendered** — not in the command's output, not in the structured plan, not in an error. Paths, operation kinds and ledger-supplied values carry everything a plan needs to say.

That is a mechanical rule rather than a list of credential-shaped key names, because such a list is a guess that eventually misses one. The single deliberate exception is the backup file, which contains the user's values by definition and is protected by inheriting the source file's mode rather than the process umask.

When migration is reported through a validation error, the error keeps `error_domain: "config"` and gains a structured `migration` block carrying the plan, the remedy and the diagnosis. Consumers branch on the presence of that block, never on wording. Following the workspace convention: the structured fields are the contract, and Markdown, exit codes and HTTP statuses are presentation.

## Boot tolerance

A stale configuration should warn, not stop the world — but only when the ledger can explain it.

```
load user files  →  deep-merge  →  validate (extra="forbid")
    ok                              → boot; no ledger touched, no tomlkit loaded
    fails, surface S
      → re-load S's user files with tomlkit
      → replay S's `safe` entries in memory, per file (writes nothing)
      → re-merge → re-validate
           ok    → WARNING naming the file and the `pipelex migrate` remedy → boot
           fails → unsafe entries, CONFLICT, or unexplained paths → validation error
                   with error_domain "config" and the `migration` block
```

The rules this encodes:

- **Boot never writes.** Nothing writes except the explicit `migrate` command; boot, `doctor` and validation detect and report.
- **Boot tolerates only what the ledger explains.** `unsafe` entries, conflicts and unexplained paths still fail the boot. Tolerance widens what starts, never what is silently accepted.
- **The healthy path is untouched.** The replay runs only on the failure path, so a current configuration never loads tomlkit and never reads a ledger. Replay neutrality is what makes the retry free when it does run.
- **One shared helper**, called by each configuration-surface loader — and that helper is also where `[meta] schema_version` is stripped. The strip belongs there and **not** in the generic TOML reader, which also reads `.mthds` files, backend definitions and the kit index, none of which reserve that key.

## Applying

> **Operations apply to the user's file, and a template is never the remedy.** "Delete your configuration and re-initialize it" is the failure this project exists to remove, not a fallback it may reach for: re-initializing throws away every choice the user made, and it is exactly what a structural change should not cost them.

### Serialization adds nothing

> **Migration serializes with `tomlkit.dumps` of the mutated document, and nothing else.**

The `.mthds` fix path follows its applier with a canonical reflow of the whole file. That is right for `.mthds` files, which are canonically formatted by CI, and wrong for a user-owned configuration, where a one-key rename must not also rewrite the user's spacing and layout. It is also load-bearing for the guarantees: byte-level replay neutrality only holds if serialization contributes no changes of its own.

### Backups

Always back up, before writing. Exactly one backup per file — a successful run replaces the previous one — named with a UTC timestamp, inheriting the source file's mode rather than the default umask, and with its path printed in the report. For files tracked in git, git remains the durable history; the backup covers the untracked ones and the moment between two commits.

### Per-file transactions

Each file is written transactionally and independently: snapshot, stage, atomic replace, restore on failure. A file that is unparseable, unwritable or changed during the run is reported as blocked while its siblings proceed. No run leaves a partially rewritten file behind.

## Limits you will meet

These are measured properties of the TOML library the engine uses, not aspirations. They are stated here because a user or an author will run into them, and being surprised by them is worse than being told.

- **Arrays of tables are unaddressable, and reserved.** An `[[entry]]` node is a list, and no `table_path` segment syntax reaches it or anything under it; the `*` wildcard has no array form. No configuration surface contains one today. If one ever appears, addressing it needs a new segment kind and a decision on the day — until then, an operation pointed at one resolves nothing and is reported as a guarded skip rather than raising.
- **A moved table loses its introducing comment.** A comment block written above a table is stored as trailing trivia of the *previous* sibling, not as part of the table it appears to introduce, so it does not travel with a move. Comments *inside* a moved table travel intact, including trailing comments on individual keys. The consequence is real: a file seeded from a heavily-commented template and then migrated ends up with banner comments labelling sections that have moved away. Nothing in the engine may rely on comment fidelity across a move, and the package's own files are corrected by hand rather than by migration.
- **A migration is not byte-minimal.** A rename adds a small amount of whitespace, and a renamed table that was written out of order across several chunks loses its own bare header while a plain table keeps it. Both forms are semantically identical, both are stable under replay, and neither accumulates — but a migration diff is not the minimal diff a human would have written.
- **A guarded skip is never an error.** Every operation whose target does not resolve reports itself skipped rather than raising. That guard is what makes always-replay possible, and it is why a misdirected operation is caught by the checks rather than by a crash on a user's machine.

## Authoring an entry

The gate says what is missing; you should not be composing entries by hand from a diff. The intended loop:

1. Make the schema change.
2. Run the coverage check. It refuses the change and names every removed path and enum member that lacks accounting, every destination that does not match an added path, and every added path that has no default.
3. Write the entry — or have the migration-authoring skill derive it from the fingerprint diff, bump the surface's schema version, regenerate the fingerprint golden and snapshot the transform goldens.
4. Add the changelog entry. The changelog and the ledger are deliberately separate artifacts saying the same thing to different readers; the release process is where they are checked against each other.

A release can never ship a moved schema without its entry: the release procedure runs the coverage check before the version bump, and refuses a bumped schema whose ledger has not moved with it.

## Related

- [Configuration Internals](contribute/configuration-defaults-and-overrides.md) — how the configuration layers merge, which this contract sits upstream of.
- [Drift Contracts](contribute/drift-contracts.md) — why the checks here are derived checks rather than review obligations: anything mechanizable becomes a derived check, and coverage, convergence, transform goldens and reserved-path checking all are.
