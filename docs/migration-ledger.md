# The Migration Ledger

Pipelex configuration files live on users' machines and in users' repositories, and the models that read them keep changing shape. A **migration ledger** is the checked-in record of every shape change a configuration surface has ever undergone, written as data rather than as code, so that a stale file can be repaired mechanically instead of deleted and re-initialized.

This page is the contract: what a ledger may contain, what the engine may do with it, and what is guaranteed to a user whose files are migrated. It is normative. Everything asserted here has, or will have, a test behind it, and where a rule exists to prevent a specific failure the failure is named — a rule whose reason is forgotten is a rule that gets relaxed.

## What migrates, and what does not

A **structural** change is a key renamed, moved or removed, or an enumerated value renamed. It breaks a user's file: the model rejects it, and no amount of re-reading helps. That is what the ledger describes and what the engine repairs.

A **content** change is a value or an entry in a package-managed file that should track the package — a model the kit added to an inference backend, a changed default in the model deck. Those files are not broken, they are behind, and merging them without destroying the user's customizations is a different problem with different machinery. Content sync is out of scope here and is not described by this contract.

The two run along the same file, and an inference backend definition is where the split is easiest to see. *Which* models a backend declares, and what each of them costs, is content: no ledger will ever add a model to a user's file, and the kit's own copy moving ahead of theirs is not something this contract repairs. *Which keys a model table may carry* is structure, and that half is a surface with a ledger of its own. A key we deleted from the schema is repaired; a model we added to the kit is not.

Everything else this document deliberately does not specify: the language surface (`.mthds` files and the MTHDS standard version), plugin-owned ledgers, and the promotion of this contract into a cross-repository specification. Each is a project of its own, and specifying it in advance would freeze decisions nobody has had to make yet.

## Surfaces

A **surface** is one artifact family with one schema version and one ledger. The in-scope surfaces are the configuration surfaces the `pipelex` package owns:

| Surface id | Directory | Base file | Tier files | Model | Defaults layer |
|---|---|---|---|---|---|
| `pipelex-config` | — | `pipelex.toml` | `pipelex_*.toml` | `PipelexConfig` | Packaged document (`pipelex/pipelex.toml`) |
| `telemetry-config` | — | `telemetry.toml` | `telemetry_*.toml` | `TelemetryConfig` | Model defaults |
| `pipelex-service-config` | — | `pipelex_service.toml` | — | `PipelexServiceConfig` | Model defaults |
| `inference-backend` | `inference/backends/` | — | `*.toml` | `InferenceModelSpecFileNode`, one root table at a time | Copied document (the kit's `inference/backends/portkey.toml`) |

Paths are relative to a configuration directory, and every surface spans exactly two of them: the global `~/.pipelex/` and the project's `.pipelex/`. `pipelex migrate` walks both, and only those. Two paths that look like configuration are outside the walk by design: the unit-testing tier `./tests/pipelex_{run_mode}.toml`, and a directory an embedder hands `Pipelex.make(config_dir=…)` that is neither of the two. Boot tolerance and the error-path diagnosis still read such a directory (see [Boot tolerance](#boot-tolerance)), but its files are the embedder's to bring up to date: `pipelex migrate` has no way to be pointed at them, and does not pretend otherwise.

A surface's **directory** is where its files sit *within* a configuration directory. Most surfaces have none and live directly in it; a surface may instead own a subdirectory, and then it owns that subdirectory one level deep and to the exclusion of every other surface. A subdirectory no surface owns is never walked at all.

The tier set is **open**. Environment and run-mode names are dynamic, so the tier filenames of `pipelex-config` cannot be enumerated in advance — `pipelex_local.toml`, `pipelex_{environment}.toml`, `pipelex_{run_mode}.toml`, `pipelex_override.toml` and `pipelex_temporary_override.toml` are a description of today, not a closed list. That is why the registry matches tiers with a glob, and the glob is what makes the resolution rule necessary:

> **A file is claimed by the pair (directory, name).** Only the surfaces that own the directory a file sits in may claim it; among those, exact filenames claim before globs, and a file matched by any of their exact patterns is excluded from all of their globs. A file claimed by two globs, or by two exact names, in the same directory, is a registry error.

Both halves earn their place on a real file. Without the name half, `pipelex_service.toml` is both the base file of one surface and a match for another's `pipelex_*.toml`. Without the directory half, `inference/backends/pipelex_gateway.toml` is a `pipelex_*.toml` match as well — and it is an inference backend definition, so the main configuration's ledger would be replayed over it and rewrite it. Either way, which ledger runs over a file would become an accident of iteration order.

The same scoping applies to what the registry refuses. A base file and a glob are claims over one directory's listing, so two surfaces collide on a spelling only when they own the same directory — `*.toml` is the natural glob for any surface that owns a directory of its own, and the second such surface must not have to narrow it for the registry's bookkeeping.

The registry error is raised at the two moments it is decidable, and no earlier. Two surfaces sharing an id, or sharing a base file or a *literal* glob string within one directory, are refused when the registry loads. Two surfaces whose globs merely *could* overlap are not: whether two glob languages intersect is not cheaply decidable, and a registry has no files to look at. That one is refused the moment a real file proves it — resolution stops by name, on the file, rather than picking whichever surface came first.

Each surface also declares its **defaults-layer kind**, because the checks need to know where a current-schema default value comes from: a packaged TOML document merged beneath the user's files, model-level field defaults, or — where the kit *copies* a document instead of layering one beneath it — nothing at all beneath the file, which is sound only for a surface no path of which is required (see [the defaults layer](#the-defaults-layer-and-why-additive-changes-never-migrate)). The distinction matters twice — for synthesizing the complete reference document of a surface that has no packaged file, and for refusing an added path that has no default anywhere. A model-defaults surface whose model cannot be built with nothing set has no defaults layer at all, and says so when its reference document is asked for rather than surfacing later as a missing value.

The registry and each ledger's `[surface]` block both describe the same thing, and both are read as truth — the ledger's when a migration walks a directory, the registry's when a gate fingerprints a model. A disagreement between them is therefore checked, not trusted: it would otherwise wait silently for the day the two readers meet. The directory is the field with a reader on the boot path as well: a stale-configuration warning names `pipelex migrate` only for a file the walk would reach, and it works out where the walk reaches from the **ledger**, because the module that composes that warning may not import the registry — the registry names every configuration model, and the warning is composed in the layer that loads none of them. One derivation, read from both ends.

Every surface starts at `schema_version = 1` with an empty ledger. There is no retroactive numbering of changes that predate the ledger; the one case that genuinely needs to reach backwards has its own bounded mechanism, described under [pre-history entries](#pre-history-entries).

## The defaults layer, and why additive changes never migrate

Every in-scope surface has a **defaults layer**: a source of current-schema values that sits beneath the user's files and cannot be stale, because it ships with the package. The consequence is the rule that keeps the whole vocabulary structural:

> **A key we add is supplied by the defaults layer, so an old file that lacks it still validates and still behaves correctly. An additive schema change cannot break anyone, and therefore never has a migration operation.**

The inverse is worth stating with equal force, because it is the tempting mistake. Writing a default value into a user's file is not a neutral repair: it converts an *inherited* value into an *explicitly set* one, pinning it against every future change to that default and changing what the merge produces. That is a semantic edit dressed up as a fix. It is why the materializing operations are excluded from the migration vocabulary outright rather than restricted to some class of files — every user file overrides the packaged defaults, base files included, so an argument that keeps materialization out of an override tier keeps it out of everything.

**If a surface ever appears to need an additive migration, the defect is a missing defaults layer on that surface, and the fix is to give it one.** The rule is enforced rather than trusted: the coverage check refuses an added path that has no value in its surface's defaults layer, and names the only remedy the vocabulary allows.

**One surface's files are copied rather than layered, and it keeps the rule for a different reason.** `pipelex init` copies the kit's backend definitions into a configuration directory, and nothing merges beneath them afterwards: what a backend file does not say, no packaged document supplies. That surface therefore has no defaults layer under the user's file, and none is synthesized — a document nothing reads would be a fiction the gates then went on to depend on. What absorbs an additive change there is the shape of the file. A backend file is `[defaults]` plus one root table per model, and no single root table has to carry anything, because only the *merge* of `[defaults]` with a model's own table is a complete model specification. A key we add is therefore a key every existing file was already free to omit, and the required-path rule is satisfied by a surface that has no required path rather than by a value sitting beneath one — which is the same fact that makes [the fingerprint's document root an open node](#the-fingerprint). The kit document such a surface names is still read, for two purposes that are not this one: it is the starting document a transform golden replays an entry over, and it and its neighbours in that directory are [convergence witnesses](#convergence-replay-is-neutral-on-the-witnesses).

## Schema versions, and why every run replays everything

Each surface carries a monotonic integer, bumped only when its shape changes. Integers rather than semantic versions, because a schema either changed or it did not. Each entry also records the package version that introduced it, for orientation against the changelog only — nothing branches on it.

Migration is **file-level**. The merged configuration cannot answer "what version is this file at", because the effective value of any key comes from whichever tier wrote last. Every migration reads, plans and rewrites one file at a time, upstream of the loader's deep merge, and tier files are migrated as ordinary members of their surface.

> **No version record ever causes work to be skipped.** Every run plans the full ledger for the surface, and the applier skips each operation whose target is already gone or whose change is already present.

The reasoning is worth keeping. Any side record of "what has already been applied" is untracked state sitting next to files that git, restores, branch switches and copies move independently of it. Anything that skips work based on such a record will eventually report "nothing to do" at the exact moment a user's boot is broken — the worst failure this tool can have. And since the record can never be allowed to cause a skip, it has no remaining reader:

> **There is no state stamp.** No state file, no per-file bookkeeping, no state-transition rules. The report describes what this run observed and did, which it knows exactly, rather than what some earlier run claims to have done.

Two reservations exist so that later projects stay free:

- **`[meta] schema_version`** is a reserved optional in-file key. Every configuration-surface reader tolerates it and strips it before validation; **nothing writes it**. The reason not to write it is not release compatibility, which our principles disclaim, but team skew on tracked files: base configuration files under a project's `.pipelex/` are shared through git right now, so one developer on a newer pipelex writing the key would break a teammate on last week's build the same afternoon.
- **`min_supported_schema_version`** on the surface block, held at zero until a ledger squash ever moves it. Without the floor, a squash silently under-migrates the oldest files in the field, because the applier skips absent targets and reports success. With it, a file that *declares* where it stands is refused by name — `unsupported_schema_version`, nothing written — instead of being run over and reported clean. The two reservations are one mechanism: a document's declaration is the only evidence a floor can act on, which is why the migration reads the reserved key exactly as tolerantly as the loader strips it. A file declaring nothing, which is every file in the field, is migrated as always.

### The downgrade direction

Always-replay covers files *older* than the running pipelex. The same branch switch that motivates it also produces files *newer* than the running pipelex: an untracked override migrated on one branch, then an older branch checked out or the package downgraded. The older model rejects the newer key, and replay finds nothing to do, because every operation's source is absent.

Under the no-backward-compatibility principle this is not repaired, but it must be **named**, because "nothing to do" beside a dead boot is precisely the failure this project exists to kill:

> When validation fails on an unknown path that no ledger entry removes, the report says so: the path is either a typo or was written by a newer pipelex than this one, and the message asks whether the user is on an older branch or build.

That diagnosis needs no stamp, and every run produces it — it lands in a plan's `unexplained[]`. Four rules make its answer worth reading:

- **It is the one part of a migration that needs the model.** Whether the current schema knows a path cannot be answered from a ledger, so the question goes to the surface's [fingerprint](#the-fingerprint) — the same projection the coverage gate diffs. The engine stays model-free, and the diagnosis sits beside the runner, which has a surface.
- **The document diagnosed is the one the run leaves behind.** Everything the ledger explains has been carried forward by then, so what is left over is genuinely left over. On a dry run that document exists only in memory, which is why the diagnosis belongs to the run and not to a later pass over the file.
- **A blocked entry answers for its own material.** An `unsafe` entry is never applied, so the old shape it is about is still in the file — already reported, by name, with the entry's guidance. Saying the same key is an unexplained typo would contradict that. The subtraction deliberately over-covers: every path it removes is one the same report names in `blocked[]`.
- **A key the user chose is reported as the schema spells it.** Beneath an open mapping the schema says `levels.*` where the file says `levels.my_package`, and a typo *inside* such an entry is reported at `queues.*.retries` — the same rule that governs a blocked entry's `narrowed_paths[]`. Only the segment the schema does not know is named, because naming it is the whole point.

Two things are deliberately not reported. An unknown *table* is named once instead of once per key inside it, since the shallowest name is the one to fix. And a document that nests below a path the schema says is a scalar is left alone: that is a type error, which the model reports far better, and descending would invent unknown paths beneath a path the schema knows perfectly well.

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
- **The neutrality property test.** Generated documents that are valid at the current schema must replay to byte-identical output. This is the executable form of the theorem over the domain the theorem actually claims, and the sampler is what makes it worth anything.

The sampler mutates the surface's defaults three ways — dropping a path, swapping an enumerated spelling for another member of its recorded set, flipping a boolean — and **proposes each mutation from the fingerprint while letting the models decide whether it lands**: a proposal the models reject is simply not made and the document keeps the value it had. That division is forced, because [schema membership is decided by validators the fingerprint cannot see](#the-fingerprint). A sampler that consults only the projection can do nothing but drop keys — sound over every surface, since the defaults layer restores whatever a file omits, but never able to reach a different *value*, which is the whole reason a property beats a witness. A sampler that mutates whatever the annotation allows and checks nothing is red only when it happens to pick the wrong path, and the remedy everyone learns for that is to grow an exclusion list. Numbers and free strings are not perturbed at all, and that costs the property nothing: no operation's precondition mentions either, so perturbing one cannot separate a neutral replay from a non-neutral one.

It carries a **vacuity meta-test**: every generated document must validate against its surface's model, or the property is passing on garbage. Under a propose-and-decide sampler that assertion guards what the per-mutation decisions do not — the assembly around them, and any later model change that breaks it — and it is made against the emitted text, which is the artifact the property is quantified over. The other direction needs guarding too, because a sampler that quietly re-emitted the reference document every time would satisfy every property on this page: each mutation kind must be shown to be reachable.

Two further properties hold and are tested with it: replay is **idempotent** (applying a ledger twice equals applying it once) and **prefix-coherent** (a file that has already absorbed some entries lands where a replay from zero lands). Both are claims about files that still have something to migrate, so they are quantified over a second generator — within-schema documents with retired material put back — which needs a vacuity check of its own: a ledger that acts on nothing satisfies both.

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
# unsafe entries only — the paths whose value domain this version narrowed:
# declared_narrowed_paths = ["reporting.retries"]

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
- **`guidance` is the explanation, never the mechanism.** Anything expressible as operations must be operations. An entry may legitimately carry no operations at all with `safety = "unsafe"`, for a change only a human can make — and then it must say which paths it is about, in `declared_narrowed_paths`. See [What an `unsafe` entry promises](#what-an-unsafe-entry-promises).
- **`declared_narrowed_paths` belongs to an `unsafe` entry and nowhere else.** A narrowing a `remap_value` can repair is accounted for by that remap; one it cannot repair is precisely what makes an entry `unsafe`, so the field on a `safe` entry is a contradiction and is refused when the file is parsed.
- **Operations target the narrowest path that expresses the change.** A ledger entry is permanent data that outlives the current field census of its parent table, so deleting a parent because it happens to have one field today is wrong — unless the parent itself is what retires, in which case the entry deletes the parent and the parent's name becomes reserved.
- **The parsed ledger is cached per process.** Replaying a surface over many files must not re-parse the TOML per file.

### Pre-history entries

A removal that predates the first fingerprint has no observed diff and no snapshot to compare against. Such an entry may carry `pre_history = true`, in which case it **declares its own removed paths** — the reserved-path registry records them from the declaration rather than from a fingerprint diff — and ships a hand-authored `before` document so the transform check has a pair to verify. Convergence and neutrality then verify it exactly like any other entry.

This exception is bounded to entries carrying the flag, and exists for the changes that shipped before the ledger did. It is not a way to avoid a fingerprint diff for a change that has one — and because that is the whole risk of the flag, it is what the four rules below check rather than trust. A pre-history entry buys an exemption from one accounting and pays for it with another.

> **The declaration is not optional.** An entry carrying the flag and declaring nothing is refused when the ledger is parsed: the declaration is what stands in for the diff, so without one the flag exempts the entry from every accounting there is.

> **No declared path may appear in a fingerprint at or below the entry's own version.** A path some snapshot records is material whose removal *is* observable, so it is accounted against that snapshot like any other change. (A *later* version bringing a declared path back is a different failure with a different remedy, and [the reserved-path rule](#reserved-paths-and-names) reports it in those terms.)

> **The fingerprint pair the entry sits between must show no removal and no narrowing.** Stated from the other side by the coverage gate, which is the gate the flag exempts: if something did go away between those two snapshots — a path, a spelling, or the values a path accepts — the entry is not pre-history and the flag would be exempting a real change from the accounting it needs.

> **Every operation's source must be declared material, or lie beneath some.** The ordinary op-legality rule reads the reserved-path registry, which a pre-history entry feeds by declaration; the effect is the same rule and the same refusal. Beneath, because a declaration names the shape that retired and an operation may address one key inside it. The rule reads each source at its literal, pre-entry path — it does not follow the entry's own renames the way [sequential path state](#sequential-path-state) does — so an operation that would address a declared table under a name an earlier operation of the same entry gave it is refused; address the material first, then rename it.

The `before` document lives beside the golden chain as `before@N.toml`, and it is the one file there that is neither snapshotted nor regenerated — a regenerated one would describe today's models, which is exactly what it is not about. Write it as a faithful representative of the old shape, carrying every path the entry's operations address, so that the transform check exercises each of them rather than taking them on the entry's word. The link then runs from that document instead of from `defaults@N-1`, and nothing else about the check changes: the same three claims verify it.

## What an `unsafe` entry promises

`safe` means the applier acts. `unsafe` means it does not — and everything an `unsafe` entry is worth rests on one sentence:

> **An `unsafe` entry is reported on every run, to every file that still carries the material it is about — at whatever spelling that material has reached — and to no other file.**

Both halves are load-bearing, and they pull against each other. Report too little and the entry is a note nobody reads; report too much and every user with a perfectly current file is warned, at every boot, forever, which teaches everyone to ignore the one warning that mattered. So the entry is **questioned** against each document before it is reported, and what makes that question answerable is what the entry declares.

**The material an entry is about** is its operations' sources, plus its `declared_narrowed_paths`.

- **Operations are questioned by rehearsing them** against the document and throwing the result away. This is value-sensitive by construction, which is the point: a `remap_value` is about a stale *spelling*, not about a path, so a user whose value was never stale hears nothing.
- **Declared narrowed paths are questioned by looking them up.** No operation can express a value the new schema refuses, so there is nothing to rehearse. Presence is the whole predicate — the engine is model-free by design, and cannot tell a value the narrowed domain rejects from one it accepts. What it reports is therefore *check this key*, not *this value is wrong*.

> **An entry with no operations must declare at least one narrowed path, and the ledger refuses one that does not.** No operations *and* one declaration is the contract's own form for "a change only a human can make", and the [coverage table](#coverage-every-schema-change-is-accounted-for)'s only remedy for a tightened numeric bound. What the refusal rules out is the shape one step below it — no operations *and* no declaration — which has nothing to rehearse and nothing to look up, and so answers "nothing to say" for every file there will ever be. The accounting would take that entry at its word; the engine would then guarantee it reaches nobody.

> **`unsafe` on its own accounts for nothing.** The coverage gate lets an `unsafe` entry leave a narrowing unremapped and an enumerated spelling unmapped — that is what `unsafe` is for — but it demands the path be named in `declared_narrowed_paths`. Otherwise the word satisfies a reader while the user whose value the new schema refuses is left with a failing boot and no message.

> **Declared paths are spelled as the fingerprint at the entry's own version records them**, `*` segments included, and [`make check-ledger`](#the-targets-and-where-the-data-lives) refuses one that version does not have. A narrowing keeps its path and shrinks what it accepts — that is exactly what separates it from a removal, which is accounted for by the operation that removes it. A path no version records is looked for in every file and found in none.

**Whatever spelling the material has reached.** An `unsafe` entry is never applied, so a file it blocks keeps the old shape while later `safe` entries go on renaming the tables around it. Questioning only the entry's own spelling makes an entry that reported on the first run go silent on the second, with the file still broken:

```
unsafe@2 is about  [reporting] mode      safe@3 renames  reporting → output
run 1: reports unsafe@2, then applies the rename → the file now says [output] mode
run 2: no reporting.mode anywhere → silent, while the boot still fails on output.mode
```

So the material is traced through the ledger before the document is questioned: **back** through the entry's own operations, because the entry never applied them, and **forward** through every later `safe` entry, for a file that has been migrated past this one. A later `unsafe` entry moves nothing, since it is never applied either; material a later entry *deletes* stops being traced, because a file migrated that far no longer carries anything the entry is about. All of it is ledger arithmetic — an operation says which path it moves where — so the engine stays the model-free, filesystem-free function the gates replay.

> **What gets reported is the spelling the file this run *wrote* uses.** Questioning happens where the replay reaches the entry; the later `safe` entries of the same run then rename the material before the file is written. So `narrowed_paths[]` names the end of that forward trace rather than the spelling that matched — otherwise a run that reports `reporting.retries` hands back a file that calls it `output.retries`, and sends the user looking for a key it no longer has.

> **A rehearsal may guess; an application may not.** Forward tracing applies to `unsafe` entries only, because their operations are rehearsed against a copy and discarded: the worst a wrong guess costs is one report too many. A `safe` entry silenced the same way — by its own `CONFLICT`, after which a later entry renames the table around it — is left alone deliberately, because repairing it would mean *writing* at a spelling its author never wrote. That is a different promise and wants its own decision.

> **Convergence exempts a reported narrowing, and nothing else.** The reference documents set the narrowed path exactly as every healthy file does, so an entry reported for that reason must not fail [convergence](#convergence-replay-is-neutral-on-the-witnesses) — otherwise the one remedy for a tightened bound could never be written. An `unsafe` entry whose *operations* fire on a witness is a different matter and still fails: that says the checked-in reference document carries retired material.

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

> **`move_key` takes no wildcard on either side.** A wildcard destination names no target: "move each entry's key into *some* entry" has no rule for which entry receives it. A wildcard *source* with the fixed destination that leaves it is many-to-one: on any file where two matched entries carry the key, the second lands on the destination the first just occupied and the whole operation conflicts. Both are refused when the ledger is parsed. The other kinds act on each matched entry in place, which is what makes a wildcard mean something for them.

> **A `key` may be `*` on `remap_value` and nowhere else.** In a `table_path` the segment expands over the tables at an open node; as a *key* it means "each key of the addressed table", and only a remap has a per-key answer to give. That reading is not a convenience: a mapping from the user's own keys to an enumerated value — `dict[str, LogLevel]` — keeps its spellings under keys only the document can enumerate, so no fixed key reaches them and this is the only shape in which a member renamed beneath an open mapping can be repaired at all. On the other kinds it is refused when the ledger is parsed: deleting every key of a table is `delete_table`, and renaming or moving every key onto one fixed name is the same many-to-one that rules the wildcard out of a `move_key`. Refused rather than tolerated, because an unrefused one is a *dead* operation — the applier looks up a key literally spelled `*`, never finds it, and reports a guarded skip forever.

> **A remap only reaches a path whose own value is a string.** A `list[enum]` holds a list, so a remap on it is a guarded skip on every run: the coverage gate does not credit one there, and names `unsafe` as the only remedy rather than sending an author to write an operation they will never see fire.

### Outcomes

The applier reports one outcome per operation:

| Outcome | Meaning |
|---|---|
| `APPLIED` | The file changed. |
| `SKIPPED` | Nothing to do — the target is absent, or the change is already present. |
| `CONFLICT` | The change cannot be made without choosing on the user's behalf. |

`SKIPPED` is the overwhelmingly common outcome under always-replay and is entirely benign; reports suppress it. `CONFLICT` is not benign and must never travel inside `SKIPPED`: it is returned when a rename or move destination is already occupied, typically because a user hand-fixed part of their file. A conflicting step writes nothing, routes into the plan's `blocked` list with the path and both names, and never undermines replay neutrality — a document carrying both names is by definition not valid at the current schema. An operation is one step whatever it expands to: a wildcard operation is checked across every entry it matches before any of them is written, so a conflict in the last matched entry leaves the first untouched.

> **Outcomes are classified by the outcome enum, never by parsing a detail string.** Messages are presentation and are free to change; the outcome is the contract.

## Legality rules

The guarantees above hold only if entries cannot say certain things. These rules are checked statically, before any file is touched.

### Op legality

Enforced by [`make check-ledger`](#the-targets-and-where-the-data-lives), against the entry's [sequential path state](#sequential-path-state) rather than against the literal path an operation spells — an operation acting inside a table an earlier operation of the same entry renamed is judged on the node it really addresses.

- **Every operation's source must be a path some schema version removed** — recorded as such in the reserved-path registry by the entry that removes it. An operation whose source is still a live path of the current schema would act on a valid file, and replay neutrality would be false. A `remap_value` is exempt by construction: what it retires is an enumerated *spelling*, not the path, which survives into the new schema — the remap legality rule is what governs it instead.
- **No operation may address a concrete key beneath an open node.** Those keys are the user's, they are unbounded, and no schema change can remove one.
- **A `*` segment is legal exactly at an open node**, and nowhere else.
- **Every `declared_narrowed_path` must be a path the fingerprint at the entry's own version records.** The declaration is what the engine questions a document about, so one no version records reaches nobody — and a path that version has *lost* is a removal, which the operation that removes it accounts for. See [What an `unsafe` entry promises](#what-an-unsafe-entry-promises).

### Sequential path state

Legality is defined over an entry's **sequential path state**, not operation by operation in isolation. An entry's operations chain: a parent is renamed and then keys inside it are renamed, so the intermediate paths belong to neither the old fingerprint nor the new one. The check therefore walks the previous fingerprint's path set through the entry's operations symbolically, carrying each surviving path together with the path it originated from, and then compares the end state with the new fingerprint in three ways:

- **Every operation's source must exist in the state when the operation runs, and must be what the operation acts on.** One whose source is absent — or a `delete_table` aimed at a key, which the applier's guarded skip refuses — is a **dead operation**: it skips on every file forever and reports success, which is the quietest way for a migration to be wrong.
- **A `safe` rename or move must not land on a path the state already has.** The applier refuses to clobber an occupied destination, so a file carrying both keys — a perfectly valid file at the previous schema — would come back `CONFLICT` on every run. Such an entry is refused as **destination occupied**; it can be `unsafe`, or choose a destination the previous schema did not have.
- **Every path surviving the walk must be a path of the new fingerprint.** A survivor that is not is either an unaccounted removal or a misspelled destination; the two are the same defect seen from either end, and one containment check catches both.
- **Every path of the new fingerprint that the walk removed must be a genuine addition** — that is, absent from the previous fingerprint. One that was present is **over-deletion**: an entry that dropped a parent table where it meant to drop one child.
- **Every enumerated spelling lost between the two fingerprints must be remapped, following the path through the entry's own renames.** Members are compared by origin — an enumerated path of the previous schema is looked up at the path the walk carried it to — so a member lost by a path the same entry renamed still demands its `remap_value`, and the remap that supplies it addresses the key by its new name. An `unsafe` entry may leave one unmapped and answers for it by naming the path in `declared_narrowed_paths`.
- **Every path whose value domain narrowed must carry a remap, or be named in an `unsafe` entry's `declared_narrowed_paths`.** Compared by origin like the spellings, and for the same reason: a narrowing hidden behind a rename would otherwise read as an unrelated addition and removal. The remedies are the two the [coverage table](#coverage-every-schema-change-is-accounted-for) names, and they are fewer than a removal has, because no structural operation can repair a value. `unsafe` without the declaration is not one of them — see [what an `unsafe` entry promises](#what-an-unsafe-entry-promises).

The end state is deliberately *not* compared as "the new fingerprint minus its additions". That formulation reads a rename's destination as an addition and its source as a removal, so it demands that the destination be absent from the end state — which is exactly where a correct rename puts it. Containment plus the over-deletion check is the same guarantee stated in a form renames satisfy.

No ordering avoids the intermediate state — a nested rename under a moved parent produces one however the operations are sorted — so this is a property of the checker, not a constraint on authors. The `*` wildcard needs no special handling either: the fingerprint records value-schema paths under a literal `*` segment, so an operation addressing an open node matches it by name like any other.

### Destination cross-check

The containment half of the walk above *is* the destination cross-check: a rename to a name the current schema does not know leaves a path the new fingerprint lacks, and is refused with the mismatch named. Without it, a misspelled destination passes both coverage and convergence — the removed path is accounted for, and over a current document the source is absent, so the operation skips — and then migrates every user file to a key `extra="forbid"` rejects, with the tool reporting success.

### Reserved paths and names

The **reserved-path registry** is the record of every path, and every remapped-away enumerated value, that a ledger entry has ever removed. Reuse is refused outright, with no escape-hatch marker: an author who hits the rule picks another name.

**The registry is derived, not stored.** Every path a schema version removed is `fingerprint@N-1` minus `fingerprint@N`, so the whole registry is a walk of the golden chain, plus the declarations of any [pre-history entry](#pre-history-entries). A stored copy would be a second source of truth that could disagree with the chain it summarizes, and the only way to check it would be to recompute it — at which point the stored copy has no reader left.

The registry is diagnostic as much as preventive. When convergence or a transform golden fails, it is what turns the failure into a sentence naming the path and the schema version that reserved it.

> **A retired top-level table name is reserved permanently** (until a ledger squash, which drops entries and the reservations they own together). Reuse would make a removed path legal again and break premise one of replay neutrality directly.

## The fingerprint

The fingerprint is a normalized projection of a surface's model tree, checked in as a golden and recomputed on every pull request. Per TOML-addressable path it records:

- the type;
- whether the path is required;
- the enum member set, where the type is enumerated;
- the value in the surface's defaults layer, where one exists;
- an open-node marker, with the value-schema paths beneath it recorded under a `*` segment;
- the numeric and length bounds on the value, where there are any.

It is serialized in a stable order and is **deliberately not raw `model_json_schema()` output**, which moves for reasons that have nothing to do with our schema — reference layout, titles, ordering, the validation library's own version. A gate that cries wolf gets regenerated reflexively, and that is how a gate dies.

The same reasoning drives two normalizations that look like information loss and are not. A nested model records its type as `table` and an enumerated one as `enum`, with no class name anywhere: renaming a *Python class* changes nothing in anybody's file and must move nothing, while renaming a *field* or an enum *member* — the things a file actually contains — moves the fingerprint and is caught. Constraint objects are stripped out of the recorded *type* for the same reason, at every level of an annotation rather than only the outermost one, so a validation-library upgrade that reshapes one cannot move a rendered type.

The bounds are recorded beside the type instead, and the same principle decides what a bound may be: the projection is a **closed whitelist** over `gt`, `ge`, `lt`, `le`, `min_length`, `max_length` and `multiple_of`, read from `annotated_types` — a zero-dependency interchange vocabulary rather than validation-library internals — and **anything unrecognized is dropped rather than serialized**. A strictness flag, a before-validator, a pattern object, a bound expressed over dates, a constraint kind a future release invents: none of them reach the golden. What lands there is a function of our schema, not of the library's representation of it, which is the property the strip above defends.

> **`pattern` is excluded, permanently.** Regex containment is not decidable for real expressions, so a gate that compared patterns would read every pattern edit as a tightening, produce false positives on changes that break nobody, and be waved through until it caught nothing. There are no `pattern` constraints on any surface today, so saying so costs nothing.

A bound is read from two places, because a bound written the ordinary way appears in neither the other: pydantic folds a top-level `Field(ge=1)` into the field's *metadata*, leaving the annotation bare, while a bound inside a union member (`Annotated[int, Field(ge=1)] | Literal["unbounded"]`) stays in the annotation. A generic container's arguments are deliberately not descended into — a bound inside `list[Annotated[int, Field(ge=1)]]` binds the items, not the list.

> **The two sources do not merge the same way, because they do not mean the same thing.** A bound in the field's metadata **binds**: pydantic applies it to the whole field, on top of whatever a member declares, so several of one kind intersect and the strictest is what a file meets. A bound inside a union member binds that member alone, so across members the widest wins — a union accepts a value if any member does. The two merged maps are then intersected, because a value must satisfy the binding bound *and* land inside some member's domain. Merging them into one pool and taking the widest recorded `le=100` for a field whose own `Field(le=6)` was the real ceiling, and a later tightening of that ceiling then read as a change to an already-looser one: the gate going quiet on exactly the values that stop validating.

Across members one overclaim is deliberate: a kind present on some members and not others is kept rather than dropped, though the honest union of an `int` bounded below with an unbounded member is unbounded. Dropping it would blind the gate to a tightening on the common `Annotated[int, Field(ge=1)] | Literal["auto"]` shape, where the literal member can carry no numeric bound at all. It is symmetric on both fingerprints, so it can report a tightening that is not one only if the *shape* of the union changes, never invent one out of a bound that moved.

An enumerated member set is collected from both sources that produce one: an enum class and a string literal type. To a TOML file they are the same thing — a closed set of legal spellings — and either can lose one. A member is only *lost*, though, when the new shape stops accepting it — that is, when the new type does not admit `str`: an enumerated type relaxed into a free string records no members afterwards, and reading that raw set difference as the loss of every spelling would demand a bump and a remap for the most benign loosening a configuration model can undergo. The exemption is exactly that shape and not "the type did not change": `Literal['a']` becoming `Literal[1]` renders the same type on both sides and records no members after, and it loses `'a'`. A literal over non-string values records no members at all — its domain is one more thing the projection does not see.

> **Members beneath an open mapping are recorded on the wildcard record, not on the mapping.** `dict[str, LogLevel]` records its spellings at `levels.*`, whose own value is the enumerated one, and records none at `levels`, whose value is a table. Recording them twice made the coverage gate demand a `remap_value` at the mapping's own path as well, and a remap of a table value is a guarded skip on every run — a demand with no legal answer. Every *other* container is still descended into, because it has no such child record: a `list[enum]` keeps its members on the list's own path, where they are the only thing that makes a member lost inside one visible at all.

> **A document's own root can be the open node, and one surface's is.** An open node is ordinarily a `dict[str, X]` *field*, recorded under the name it has — but a backend file has no such field: its root keys are model names, and the model beneath each of them is the value schema. Making one up would put a segment in every path (`models.*.sdk`) that no TOML document has, and a `RootModel` puts `root.` there for the same reason. So the surface declares that its root itself is open, and the projection is seeded at `*` rather than at the root: the recorded paths are `*`, `*.sdk`, `*.max_tokens`, and so on, which are exactly the paths an operation can address — `delete_key` with `table_path = ["*"]` reaches one key of every model table, and no entry can name one machine's model. `[defaults]` is simply one of those keys, and the projection has nothing to say about which root keys a file happens to hold. Whether a root was open is recorded **on the fingerprint** rather than read from the surface, because a frozen link has to answer for its own version, and the live registry can only answer for today's.

Two shapes are recorded as terminal rather than descended into, because no operation can address what lies beneath them: an array of tables, which has no path segment syntax and no wildcard form, and a model reachable from itself, which has no finite path set at all. Terminal means blind: a change to the model beneath an array of tables leaves the fingerprint unchanged, and the telemetry surface's `otlp` exporters are that shape today (see [Limits you will meet](#limits-you-will-meet)).

> **The array-of-tables blind spot stays, and the reason is that closing it would produce a demand nothing can answer.** Recording an item model's fields under a synthetic segment would make a renamed field inside an exporter entry visible to the coverage gate — and then demanded, with no operation in the vocabulary able to reach it and no remedy an author could write. A gate whose refusal has no legal answer is worse than a blind spot the contract names. Revisit on the day an addressing syntax for arrays of tables exists, and not before: the two are one change.

**What the fingerprint records is what the types say, and a validator can say something else.** Every recorded field is read from an annotation or from the metadata beside it, so a constraint expressed as a validator instead is invisible here — and that is not a corner case, it reaches the enum member set and the open-node marker alike. A telemetry mode is a member of the recorded set and is still rejected unless the document also carries the user id that mode requires. Several nodes typed `dict[str, X]` on the main configuration surface reject any key outside a fixed set, so the open-node marker claims a key space that is not the user's after all. A pair of validators demands every member of an enum as a key of every entry of an open mapping, which makes *adding* an enum member break a user's file — additively, as far as any projection can tell. Nothing here can be made to see any of it.

> **The gate does not claim what it cannot see.** Domain narrowing expressed in a validator — a non-empty check, a cross-field invariant, a completeness rule over user-supplied keys — is not visible from the schema and stays the author's responsibility. The [coverage gate](#coverage-every-schema-change-is-accounted-for) catches the mechanical subset: types and the whitelisted bounds. It does not catch the rest, and the coverage table would overclaim without this sentence. **The responsibility is declared rather than left to memory:** the `config-docs` drift contract ([`docs/contribute/drift-contracts.md`](contribute/drift-contracts.md)) carries the migration ledgers and the two modules holding the four live validator sites in its review list, so a change to any configuration model opens an obligation to ask whether a validator narrowed a domain and, if one did, whether an `unsafe` entry carrying `declared_narrowed_paths` is owed.

The consequence for the gates is mild where they compare a fingerprint against a fingerprint, because a blind spot on both sides cancels. The consequence for anything that tries to *decide schema membership* from a fingerprint is total, and it is why [the neutrality property test](#replay-neutrality) asks the models rather than the projection.

What each recorded field is for: requiredness and enum members are load-bearing for coverage and for remap legality; defaults are recorded so that a flipped default is *visible in the regeneration diff*, but a default value **never gates on its own** — it changes no shape and no operation can address it. The one place a default is decisive is [a required path that has none](#coverage-every-schema-change-is-accounted-for).

## The checks

Checks with distinct failure meanings, so that a red gate says which guarantee broke. Placement follows the house rule: anything that regenerates and diffs lives in `make check` only, and anything with one obvious fix per failure joins `make agent-check`.

### Coverage — every schema change is accounted for

Recompute the fingerprint and diff it against the golden for the surface's current schema version:

The verdict turns on **direction**, not on whether something moved: a change that leaves a user's file valid asks for a regeneration, and one that does not asks for a bump. That distinction is what the last row exists for — a narrowing removes no path and no spelling, so read as a raw diff it looks exactly like an addition.

| Diff | Verdict |
|---|---|
| Unchanged | Pass. |
| Paths or enum members added, a default changed, or a type or bound **widened** | Regenerate the golden. No version bump and no entry are demanded, because additive changes are absorbed by the defaults layer and a widened domain still accepts every value a file already carries. Widening is defined so the fingerprint can decide it: a union whose members are a superset of the old ones, an enumerated type becoming `str`, and a bound dropped or relaxed. |
| Any path or enum member removed or renamed | Require a schema version bump, an operation accounting for every removed path (wildcard paths included), and for every removed enum member either a remap or an `unsafe` entry **naming that path in `declared_narrowed_paths`**. Destinations are cross-checked against added paths. |
| A type or bound **narrowed** — `int → str`, `str → SomeEnum`, `list[int] → list[str]`, `ge=1 → ge=5` | Require a schema version bump and an entry, exactly as a removal does. Every path survives and every spelling is still enumerated, and a file carrying an out-of-domain value stops validating all the same. No structural operation can repair a value, so the entry must carry a `remap_value` for each narrowed path — where the old spellings can be enumerated and [remap legality](#replay-neutrality) accepts it — or be marked `unsafe` **and name each narrowed path in `declared_narrowed_paths`**, which is the only remedy a tightened numeric bound has. A remap answers only for the string values it rewrites — a lost `str`, enum or literal member — and for nothing else: an `int \| literal` field that loses its number, or that loses a spelling *and* raises its floor, still demands `unsafe`, because no mapping reaches a number. |

Alongside the diff, one standing invariant is checked on the new fingerprint itself, whether or not anything changed:

> **Every path a document must carry has to have a value beneath it.** A path that is required, and whose ancestors are all required, must have a value in its surface's defaults layer — otherwise it is breaking on the day it lands, and the refusal names the only remedy the vocabulary allows: give it a default. Wildcard paths are exempt by construction, since the keys beneath an open node are the user's and there is no single value to supply.

Stating it over every required path rather than only over newly added ones costs nothing — it holds across every configuration surface today — and it catches the same defect arriving by the other door, a path that becomes required without gaining a default.

**Every entry is re-checked on every run**, not only the one being authored: the walk above runs for each link of the chain, `fingerprint@N-1` against `fingerprint@N`. An entry verified once at bump time and never again would silently stop matching its own diff the first time somebody edited it.

> **There is no escape hatch.** No `no_migration_needed` marker exists. A path that was never shipped to anyone still carries a one-line `delete_key`, which always skips and costs nothing — because "this one does not need an entry" is a judgment the next person cannot re-derive, and one such marker teaches everyone that the gate is negotiable.

### Convergence — replay is neutral on the witnesses

A full replay of a surface's ledger over each of its reference documents produces zero applied operations, reports nothing about them beyond a [declared narrowing](#what-an-unsafe-entry-promises), and returns the very bytes it was given. The same target checks what else is cheap and unambiguous: the ledger parses into the migration-operation subset, versions are contiguous and match ids, every operation is legal, every `safe` remap satisfies the legality rule, and no entry reintroduces a reserved path or a remapped-away spelling.

> **This target reads checked-in files and never fingerprints a live model** — the ledgers, the stored golden chain, the two reference documents (one of which, for a surface whose defaults come from its model, is rendered from that model's default values — rendered, not fingerprinted). That restraint is what earns it a place in `make agent-check`: every failure is a statement about a file the author wrote, and every remedy is to fix one. A check that read the models would go red on an ordinary configuration edit with *regenerate the golden* as its remedy, which is the fail-regenerate-fail cycle that keeps the coverage gate out of the loop agents run constantly. The cost is bounded and visible: between a version bump and the `make up-migration-schemas` that snapshots it, the new link does not exist, so the entry checks that need a fingerprint pair report the missing link by name instead of running.

### Transform goldens — the operations say what the schema change did

Coverage proves an entry *exists* for every removal. Convergence proves replay is *harmless* on current files. Neither proves the entry is *right*, which is what the transform goldens close.

The regenerator writes, for each surface, the snapshot of its **current** schema version: `fingerprint@N` and the complete reference document `defaults@N`. A bump simply leaves the previous version's files behind, so the chain accumulates one frozen link per historical version.

> **The head link tracks; every link below it is frozen.** The snapshot for the current version is rewritten from live sources on every regeneration.

Freezing the head instead would rot. An additive change is absorbed by the defaults layer and needs no bump, so a head frozen at the last bump would drift from the live model and eventually stop validating against it — while the whole point of the last link is that it is what the current model reads. Only the sparse kit template is not snapshotted at all: it is a convergence and neutrality witness, and both read it live, so a snapshot of it would have no reader.

The check then applies entry N to `defaults@N−1` and asserts three things about what comes out, pairwise over the complete-defaults family:

> **Every path the migration creates, schema version N has** — in `defaults@N` or in `fingerprint@N`; **every path `defaults@N−1` and `defaults@N` share survives the migration**; and **the last link's migrated document is accepted by the current model**, read the way a user's file is read — beneath the current defaults layer where one is layered beneath it, and on its own where the kit copies the document instead of layering one under it.

Each claim is one-directional on purpose, and together they are red on wrong destinations, wrong remap targets, wrong order and over-deletion. The first catches a destination that is misspelled or lands where the new shape carries nothing, which is the defect the whole check exists for: coverage accounts for the removed path and convergence skips the absent source, so without this the typo migrates every user file to a key `extra="forbid"` rejects, with the tool reporting success. The second catches an entry that dropped a parent table where it meant to drop one child. The third catches what moves no path at all — a value the schema does not accept, or a key it does not know.

One exemption belongs to the first claim: a created path whose **container** is absent from `defaults@N` is not compared. When a whole entry of an open mapping is dropped from a packaged document between versions, what an operation did inside it says nothing about the operation.

The comparator is **not byte-exact, not a subset test, and not an equality**. Byte-exactness fails on any honest version bump, because the same commit adds keys, edits comments and flips unrelated defaults. A subset test is blind to over-deletion. An equality is blind in the other direction: it would refuse every addition the same commit made. What survives tolerates additions, comment edits and default flips, because nothing asserts them.

> **What the comparator is not: `paths(defaults@N) − added_at_N`.** A raw fingerprint difference counts a rename's *destination* as an addition, so subtracting it would demand the destination be absent from the expected shape — exactly where a correct rename puts it. This is the same defect the [symbolic end-state walk](#sequential-path-state) met and answered with containment, and the answer here is the same one expressed over documents. Subtraction would also be blind by construction to everything a fingerprint cannot see: a model added to a packaged deck lives beneath an open node, where the fingerprint records a value schema and never a key, so that addition would be asserted rather than tolerated and the check would go red on ordinary content.

> **What the first claim reads: `defaults@N` *or* `fingerprint@N`, never the document alone.** An optional key whose default is `None` has no value in any reference document — TOML has no null, and the synthesized document drops the key — while being a perfectly ordinary destination for a migration to move a user's value onto. Against the document alone, the check would refuse the destination the schema most obviously has. A misspelled destination is in neither the document nor the fingerprint, so nothing the claim was protecting is given up, and the fingerprint is checked-in data like everything else the check reads. The fingerprint is read *with its wildcards*: a document names the user's own key where the fingerprint names `*`, so `deck.claude.new_name` is recorded as `deck.*.new_name`, and a rename beneath an open mapping whose destination the reference document happens not to carry under that entry is a correct rename, not a misspelled one.

> **What the comparator does not assert: value equality against `defaults@N`.** A default flipped in the same commit as a rename makes such a check red with no remedy available to anyone — the older link is frozen, the head link tracks, and a migrated file legitimately carries the user's old value where the new reference document carries the new default. What that assertion was for, *the operations produce values the new schema accepts*, is checked where it can be checked soundly: by the last link's validation above, and by [the remap legality rule](#replay-neutrality), which refuses a remap whose target spelling the new schema does not accept.

One kind of entry has no link to check: an **unsafe** entry is reported and never applied, so no document ever makes that transition mechanically, and the vocabulary explicitly grants such an entry the right to be incomplete — an entry with no operations at all is legal precisely when it is unsafe. A **pre-history** entry does have a link, and this is where it is verified: it has no snapshot on the far side of it, which is what the flag means, so the link starts from its hand-authored [`before@N.toml`](#pre-history-entries) and answers the same three claims. An entry marked pre-history with no such document is refused by name.

The sparse kit template is **not** in the chain: starter-template edits between bumps would go red under equality, and it exercises no operation the complete document does not. It remains a convergence and neutrality witness.

Pairwise checks compose by induction into the full chain — a replay from any historical snapshot lands on the current shape, because prefix entries skip on any snapshot at or past their version, their sources being permanently removed material. That induction is also why only the last link is validated against a model: it is the only link whose model we still have, and every earlier one was the last link when it was authored.

### Testing the gates without coupling them to the configuration models

The surface registry is an **injected parameter, never a module constant**. The gates' own tests point it at small synthetic models with fixture ledgers, fixture fingerprints and fixture golden chains, so gate *behaviour* is tested against something that never moves; a single smoke test asserts that the real registry loads, the real goldens match and the real convergence holds.

Without this, every legitimate configuration change turns the gate's own suite red alongside the gate, and the fix everyone learns is "regenerate the goldens" — which is how a gate goes permanently green while catching nothing.

[The neutrality property](#replay-neutrality) is the deliberate exception: it is quantified over the real surfaces, because the domain it claims is the one real files live in. What keeps that from costing what the rule warns about is the propose-and-decide sampler — a model that grows a new validator makes a proposed mutation stop landing, rather than making the suite red. Everything the property needs a ledger with entries in it for runs against a synthetic surface, as the rule says.

### The targets, and where the data lives

| Target | Alias | Aggregates | What it does |
|---|---|---|---|
| `make check-ledger` | `cl` | `check`, `agent-check` | The ledger parses into migration operations, versions are contiguous and match ids, legality and remap legality hold, no entry reintroduces a reserved path, and replay over both reference documents applies nothing. Reads checked-in data only — no live model is fingerprinted and nothing is regenerated. |
| `make check-migration-schemas` | `cmig` | `check` | Fingerprints every surface, diffs against the goldens, demands a bump and full accounting for every removal, cross-checks destinations, and verifies the pairwise transform-golden chain. |
| `make up-migration-schemas` | `umig` | — | Regenerates the fingerprint goldens, and snapshots the reference documents into the transform-golden chain when a schema version bumped. Refuses a head golden whose material the models have lost. |
| `make up-migration-schemas-force` | `umigf` | — | The same, over that refusal. For a change to the fingerprint *format* on an unreleased schema version, and nothing else. |

Only `check-ledger` joins `agent-check`: it regenerates nothing and each failure has one obvious next action. `check-migration-schemas` is a golden check, and in the loop agents run constantly it would produce a fail-regenerate-fail cycle with no single right answer, so it stays in `check` alone.

> **The regenerator is not part of `make up`, and refuses to erase a removal.** Every other regenerator in that aggregate rewrites a derived artifact from a live source, so running them all out of habit is harmless. The head fingerprint golden is not derived — it is the *proof obligation* the coverage gate compares against, and rewriting it after deleting a field erases the very removal the gate exists to catch, leaving it green over a change that breaks every user's file. So the target is run on purpose and its diff is read, and it stops before overwriting a head golden that records a path, an enumerated spelling or a value domain the models no longer have. The refusal names both readings — a real removal wants a bump and an entry; a golden that merely predates a change to the fingerprint format wants `make umigf` — because the code cannot tell them apart and picking one on the author's behalf is how the wrong one gets chosen.

The checked-in data it all reads:

```
pipelex/migration/ledgers/<surface-id>.toml            the ledgers
pipelex/migration/goldens/<surface-id>/
    fingerprint@N.json                                 the fingerprint at schema version N
    defaults@N.toml                                    the complete reference document at schema version N
    before@N.toml                                      a pre-history entry's hand-authored starting document
```

Two files per version, and a third only where a [pre-history entry](#pre-history-entries) needs one. The fingerprint the coverage check diffs against is the chain's head link, `fingerprint@<current>`, rather than a separate always-current copy — one file with one writer cannot disagree with itself. The reserved-path registry is [derived from the chain](#reserved-paths-and-names), and the sparse kit template is read live rather than snapshotted.

## What the engine reports

Every surface produces the same plan model:

```
MigrationReport
  └── MigrationPlan (per file)
        surface_id, file_path
        blocked_reason, blocked_detail → set when the file itself could not be processed at all
        backup_path, was_written       → set when the run wrote the file
        steps[]        → entry_id, to_schema_version, title, description, breaking, safety, applied_ops[]
        blocked[]      → entry_id, to_schema_version, reason, detail, guidance, applied_ops[], narrowed_paths[]
        unexplained[]  → path, note
```

There is no `from_version` and no trusted-version concept: nothing skips, so nothing needs one. Because a replay walks every entry while usually changing little, the report renders what actually changed — a step lists only the operations that fired, not the many that skipped.

Two different things can be blocked, and the report keeps them apart. An **entry** is blocked when it cannot be applied — it is `unsafe`, or one of its operations came back `CONFLICT` — and it lands in `blocked[]` with the reason and its guidance, while the rest of the file's entries proceed. A **file** is blocked when it cannot be processed at all. That reason sits on the plan itself, and a blocked file never stops its siblings — every other file in the surface is migrated and reported normally.

There is one file-blocked reason per **state the file is in**, rather than one per exception the run happened to catch, because the state is what decides what the user does next:

| Reason | What it says about the file |
|---|---|
| `unreadable` | It is there and its bytes would not come. Nothing was written. |
| `unparseable` | It was read and is not valid UTF-8, or not valid TOML. Nothing was written. |
| `unsupported_schema_version` | It declares a `[meta] schema_version` below its ledger's floor, so the entries that would carry it forward are no longer there. Nothing was written. |
| `unwritable` | It needed a change and the run could not make it — the backup would not go down, or the replacement would not. The file is exactly as it was found. |
| `changed_during_run` | It was removed or edited between the read and the write, so the run refused to write over work it had not seen. |
| `state_uncertain` | The write could not be confirmed: the transaction could not describe what it left behind, and the file does not hold what the run wrote. |

`state_uncertain` is the only one that cannot promise the file is as it was found, which is why it is not folded into `unwritable`: the next move is to compare the file against the rescue copy the plan names, not to fix a permission and run again. It is also, for the single-file commit a migration performs, the only transaction failure that reaches a plan at all — a replacement that fails re-raises its own error, because rolling back nothing is trivially complete.

Two rules govern how an entry appears, and both exist so that a report is never more optimistic than the file:

> **An entry is reported once.** An entry with a conflicting operation lands in `blocked[]` and not in `steps[]`, carrying in its own `applied_ops` whichever of its operations did land before the conflict was found. Operation-level atomicity is the applier's — a conflicting operation writes nothing — but an entry is not atomic, and saying it arrived whole when part of it could not would be a lie the next run has to correct.

> **An `unsafe` entry is reported only when the file still carries the material it is about.** Its operations are rehearsed against the document and the result discarded, and its declared narrowed paths are looked up — at every spelling later entries have given them. An entry with nothing to say about this file stays silent. Reporting every `unsafe` entry regardless would warn every user with a perfectly current file, at every boot, forever — and a warning nobody can act on is a warning everybody learns to ignore. The whole rule is [What an `unsafe` entry promises](#what-an-unsafe-entry-promises).

> **A blocked entry's reason says which claim it is making.** `unsafe` means the file has the old *shape* and the applier will not change it. `conflict` means an operation's destination is already occupied. `value_domain_narrowed` is the weakest and the newest: the file *sets* a path whose accepted values the entry narrowed, and `narrowed_paths[]` lists those paths as the **ledger** spells them — `levels.*`, never the user's own `levels.my_package` — and at the spelling the file this run wrote carries, not the one that matched. It is a list of keys to check by hand rather than a list of errors, because telling one from the other needs the model and the engine has none by design.

> **An unexplained path is what neither the schema nor the ledger accounts for.** `unexplained[]` carries the paths of the migrated document that the current schema does not know and no entry — applied or blocked — explains, each with the two readings the tool cannot tell apart: a typo, or a file written by a newer pipelex. The whole rule is [the downgrade direction](#the-downgrade-direction).

> **No value read from a user's file is ever rendered** — not in the command's output, not in the structured plan, not in an error. Paths, operation kinds and ledger-supplied values carry everything a plan needs to say.

That is a mechanical rule rather than a list of credential-shaped key names, because such a list is a guess that eventually misses one. The single deliberate exception is the backup file, which contains the user's values by definition and is protected by inheriting the source file's mode rather than the process umask.

When migration is reported through a validation error, the error keeps `error_domain: "config"` and gains a structured `migration` block carrying the plan, the remedy and the diagnosis. Consumers branch on the presence of that block, never on wording. Following the workspace convention: the structured fields are the contract, and Markdown, exit codes and HTTP statuses are presentation.

## The commands

Two commands run a migration, and they are the same run with two audiences.

| | `pipelex migrate` | `pipelex-agent migrate` |
|---|---|---|
| Reader | a person | a program |
| Default | plan, show it, ask | plan, and write nothing |
| Writes when | the question is answered, or `--yes` | `--yes` |
| `--dry-run` | plan and stop | plan and stop (the default, said explicitly) |
| Answer | Rich output | JSON, or Markdown with `--format markdown` |

**Both walk the global `~/.pipelex/` and the project `.pipelex/`, and nothing else.** An embedder's `config_dir=` outside those two and this repository's own `tests/pipelex_{run_mode}.toml` are outside the walk: the first is the embedder's to update, the second is not a user's configuration at all, and migrating a directory nobody asked about is how a tool earns a reputation for touching things. A directory that does not exist is skipped, and a project rooted at the home directory is walked once rather than twice.

**The walk is each surface's own directory, one level deep.** Most surfaces live directly in a configuration directory and their tier files sit beside their base file. A surface may instead own a subdirectory — `inference/backends/` — and then that subdirectory is walked the same way, one level, for that surface alone. A subdirectory no surface owns, such as `inference/deck/`, is never entered at all, and no walk goes deeper than the directory a surface names.

> **`--dry-run` and `--yes` together are refused, not resolved.** One asks for no write and the other authorizes one; picking a winner would hide the bug that produced both.

**Neither command boots.** A broken configuration is the reason to reach for `migrate`, so needing a working one would make it useless in exactly the case it exists for. What a migration may use is the ledger, the applier and the filesystem: no configuration load, no model deck, no credentials, no network. That is a property under test rather than an accident, and the test is what keeps a future import from creeping into the list.

**The structured fields are the contract.** `needs_attention` is the verdict — *this run left something a person has to decide* — and it is deliberately not "did anything get written": a run that migrated every file it found has succeeded, and so has a dry run that found nothing blocked. The exit code (`1` when `needs_attention`, `2` on a contradictory pair of flags) and the rendering are presentation, and follow the workspace convention rather than carrying the verdict.

## Boot tolerance

A stale configuration should warn, not stop the world — but only when the ledger can explain it.

```
load user files  →  deep-merge  →  validate (extra="forbid")
    ok                              → boot; no ledger read, no document re-parsed
    fails, surface S
      → re-read S's user files with tomlkit
      → replay S's ledger in memory, per file (writes nothing; `unsafe` entries are rehearsed, never applied)
      → re-merge → re-run the loader's own post-merge step → re-validate
           ok    → WARNING naming the file and, where the command reaches it, the `pipelex migrate` remedy → boot
           fails → unsafe entries, CONFLICT, or unexplained paths → validation error
                   with error_domain "config" and the `migration` block
```

The rules this encodes:

- **Boot never writes.** Nothing writes except the explicit `migrate` command; boot, `doctor` and validation detect and report. A tolerated boot leaves no backup either, which is why the warning keeps coming back until the user runs the command.
- **Boot tolerates only what the ledger explains.** Tolerance widens what starts, never what is silently accepted. **The re-validation is what decides**, and that is stronger than a second gate on the report would be: material an `unsafe` entry is about is still in the file, so the model refuses it and the boot fails, and a `VALUE_DOMAIN_NARROWED` report the model accepts was never a reason to refuse a boot — that report says *check this key*, and the model has now checked it.
- **The retry honours the [schema-version floor](#schema-versions-and-why-every-run-replays-everything).** A file that declares a version below `min_supported_schema_version` is one `pipelex migrate` refuses; the retry declines it through the same predicate rather than carrying it forward under-migrated, and the user's own error — with the `migration` block naming the floor — is what they see.
- **The retry never becomes the failure.** Anything that goes wrong inside it — a ledger that will not load, a file that will not parse — makes it decline, and the error the *configuration* produced is what the user sees. Their error names the key to fix; ours would name our packaging. A file that cannot be re-read abandons the whole retry rather than being skipped, because skipping it would drop a layer from the merge and a re-validation that then succeeded would boot on a configuration the user does not have.
- **The main configuration's warning waits for the logger.** That configuration is what configures logging, so when its retry succeeds there is no logger yet — the loader parks the warning (`config_manager.take_stale_configuration_warning()`) and the boot emits it right after `log.configure`. The telemetry and service loaders run after that point and warn directly. The warning is the same either way; only *when* it is said moves.
- **The inference backend loader parks its warning too, and for a different reason: a caller, not boot order.** By the time backends load, logging has been configured for a while. What that loader has instead is `pipelex doctor`, which probes the backend files by loading the whole library **once per backend** — so a loader that logged for itself would repeat one stale directory's warning a dozen times in one report. It hands the warning over instead (`take_stale_configuration_warning()`), and the caller that owes the user a copy takes it: the models-manager setup emits exactly one per boot, the doctor's per-backend probe simply never asks, and no abstract interface widens to carry it. One warning per load covering every stale file, not one per file and not one per backend.
- **The warning names `pipelex migrate` only for a file the command would reach.** The retry replays whatever the loader merged, and a loader pointed at a directory of its own — an embedder's `config_dir=`, or this repository's `tests/pipelex_{run_mode}.toml` — merges files [outside the walk](#the-commands). For those the warning says the file is the caller's to update where it lives, and does not name a command that would then report nothing to do; a load that spans both gets both sentences, each naming its own files. Same rule as [the remedy on a validation error](#every-surface-reports-it-the-same-way-and-none-of-them-says-start-over): *a remedy is named only where it would write*. The walk is `config_manager.existing_config_dirs`, which is also where `config_directories_to_migrate` reads it — one derivation, read from both ends, so a boot cannot promise what the command declines. Reach is per *surface*, not per path: the file must sit in the directory **its own surface** owns under one of those roots, so a `telemetry.toml` dropped into `inference/backends/` is out of reach exactly as it was before any surface owned a subdirectory.
- **The healthy path is untouched.** The replay runs only on the failure path, so a current configuration never reads a ledger, never re-parses a document, and never even imports the migration engine. (Not "never loads tomlkit": the ordinary configuration read has always imported it. What a healthy boot avoids is the second, DOM-level read.) Replay neutrality is what makes the retry free when it does run.
- **One shared helper**, called by each configuration-surface loader — and that helper is also where `[meta] schema_version` is stripped. The strip belongs there and **not** in the generic TOML reader, which also reads `.mthds` files, backend definitions and the kit index, none of which reserve that key.

**The helper owns the failure path, not the load.** The loaders do different things between their merge and their validate — the main configuration deep-merges programmatic overrides, telemetry substitutes `${VAR}` placeholders, the service configuration does nothing, and the inference backend loader does the most of any of them: it pops `[defaults]` out of the document, splits the header-shaped keys off each remaining root table, and validates the *merge* of the two rather than the document. A helper that owned the whole load would have to be told about every one of them. It is given the surface id and the same ordered path list the loader merged, and it hands back the migrated merge plus a `MigrationPlan` per file; each loader re-runs its own step over that and re-validates. The overrides in particular have to be re-applied by the caller: they are a layer of the *load*, and the replay only ever sees the *files*.

> **A surface whose files are independent documents calls the helper once per file.** The helper deep-merges the paths it is given, which is exactly right for a tier stack: `pipelex.toml` beneath `pipelex_local.toml` beneath `pipelex_override.toml` are layers of one configuration, and the thing that has to validate is their merge. Backend definitions are not layers of anything — `openai.toml` and `portkey.toml` are separate documents that happen to share a directory, and merging them would produce a backend nobody has. So that loader passes one path per call and keeps the results apart, and composes one warning covering every file the round recovered.

> **The migration engine is imported inside the retry, not at the top of the module.** Its applier lives under `pipelex.pipeline` — an interpreter package — while the configuration loaders sit in `runtime_hub`'s import closure, and the kernel layer's property is that importing it loads zero interpreter modules (see [`hub-layering.md`](contribute/hub-layering.md)). A module-level import would break that silently: the layering guard mechanically checks reachability to `interpreter_hub`, which `pipelex.pipeline.fixes.applier` does not have, so nothing would have gone red. The deferred import is also what makes "the healthy path is untouched" literal rather than approximate.

**Boot tolerance does not run the [downgrade diagnosis](#the-downgrade-direction).** On this path the model has already spoken, and pydantic's own extra-field list is both the same answer and a better one — it knows about validators, which a path walk does not. The diagnosis exists for `pipelex migrate`, where nothing validates the file at all. So "unexplained paths still fail the boot" is satisfied by the re-validation failing, and the `migration` block on the error carries the plans.

## Reporting a stale configuration on a validation error

When the boot's retry declines and the model's refusal stands, the error the user gets says one more thing than pydantic can: whether their configuration is *wrong* or merely *old*.

A validation error cannot answer that by itself. It is raised against the merged configuration and carries no provenance — it names a key, not which of the files that were merged put it there, and certainly not whether that key was correct last month. So `report_validation_error` asks the files instead: a **dry-run scan** of the surface that refused, over the same directories a `pipelex migrate` would walk — or, when the caller loaded one explicit directory (`doctor --global`, an embedder's `config_dir=`), over that directory alone, so the block never names a file the reader did not load.

**The scan is named, not guessed.** The caller passes the surface whose model refused; a caller validating something that is not a configuration surface — a `.mthds` bundle, a model deck, a routing profile — passes nothing and gets the translation alone. None of those has a ledger, and offering them a `pipelex migrate` remedy would send a user to a command with nothing to do. That is also why the scan does not run at all when no surface is named: it is a directory walk and a ledger replay, and a bundle-validation failure has no business paying for one.

> **An inference backend file used to be on that list, and moving it off was a code change rather than a wording one.** The boot builds its own message for the two libraries that refuse after the main configuration is already up — the backend library and the model deck — and it named no surface for either, which was right while neither had a ledger. Now one of them does, and the two are told apart by the component itself rather than at the `except` clause: the pairing of a component with its surface is stated once, so a call site cannot quietly drop it. The case this reaches is narrow and real — a backend file that is *both* behind and carrying something we cannot explain never gets as far as boot tolerance's warning, and before this it was told only the second half. The scan is only reachable if the boot catches what the loader really raises, so the classes that mean *this library's files are not loadable* are named once, beside the component — a backend definition file refuses in two shapes, and only one of them carries a pydantic error; the library index file `backends.toml` refuses in a third, on a backend table's own fields, and each has to be a class the boot names.

> **Scoping narrows the answer, never the registry.** Which surface owns a file is decided across *all* of them, because an exact base file claims before any glob. A registry built to hold only the surface being asked about removes the other claimants from that arbitration, and `pipelex_service.toml` — another surface's base file, and a match for `pipelex-config`'s `pipelex_*.toml` — is then replayed under the wrong ledger and diagnosed against the wrong model, so its ordinary settings come back reported as paths this build knows nothing about.

The answer rides the error twice, and the two halves are not interchangeable:

- **`error_domain` stays `"config"`.** It does not become a domain of its own. `ErrorDomain` is a closed cross-repo enum and the agent-hook specification routes any domain it does not know to BLOCK, so a stale configuration reported under a new domain would stop an agent rather than tell it what to run.
- **The structured `migration` block is the contract, and consumers branch on its presence.** Absent means the failure is not staleness. Present, it carries `remedy` (the command), `would_write` (whether that command would rewrite any of these files), `needs_attention` (whether anything here is a person's rather than the tool's), and `plans` — the same `MigrationPlan` shape `pipelex-agent migrate --dry-run --format json` emits under its own `plans` key, so an agent that parses one has already parsed the other. Only the files the scan found something in are listed: unlike the commands' report, which answers *what did the walk visit*, the block answers *what is wrong with this machine*.
- **The message is presentation.** It carries the refusal — the pydantic analysis where the surface's own model refused, or, for the two libraries the boot reports on, the loader's own sentence, kept whole because it names *which model, which backend, which file* before quoting that analysis, and a directory holds a dozen files with the same field names — followed by a paragraph naming the files, what the command would carry forward, and what it cannot do for anyone. Nothing branches on its wording.

> **A remedy is named only where it would write, and `would_write` is what says so.** The block's presence means the migration history has something to report about these files — not that running the command repairs them. A file whose only finding is a path no entry explains, or an entry blocked before any of its operations landed, produces a block with nothing to apply; naming `remedy` there sends a reader to a run that visits the file, writes nothing, and leaves the same refusal in front of them. So every surface branches on the field rather than on the presence, and the ones with nothing to apply point at `pipelex migrate --dry-run`, where the diagnosis actually is. The two flags are independent and never both false: a file with nothing to write and nothing for a person is clean, and clean files are not in `plans`.

The agent loop this opens is the one the commands were built for: a command fails, the block is present, the agent runs `pipelex-agent migrate --dry-run --format json`, shows the user what would change, and runs `--yes` on confirmation. It never hand-edits a configuration file.

> **No value read from a user's file appears in the block either.** This is the third of the three channels that rule covers, beside the command's own output and its structured plan. The block reports paths, operation kinds and ledger-supplied values — a key holding a live credential is named by its *path* and never by what it holds.

**A failure inside the scan is never the failure the user sees**, for the same reason the boot retry declines quietly: they have an error in front of them that names what to fix, and replacing it with a packaging problem of ours would cost them the only message that helps. A ledger that will not load stays loud where it should be — `make check-ledger`, and `pipelex migrate` itself. The catch is narrow rather than blanket, so a bug in our own applier still surfaces as the bug it is.

### Every surface reports it the same way, and none of them says "start over"

A configuration error reaches a user through several surfaces at once — the human CLI's panel, the agent CLI's JSON envelope, the `doctor` row — and before the ledger each of those carried its own hardcoded remedy. The telemetry ones are the case worth naming, because they were written for a real event and then aged into the wrong advice: *the telemetry.toml format has changed, run `pipelex init telemetry`*, shown for the very flat file that entry `telemetry-config@2` exists to carry forward. That command writes a fresh file. It would have taken the PostHog key, the Langfuse credentials and the OTLP exporters with it.

So no surface holds its own answer any more:

- Every configuration surface's refusal goes through `report_validation_error`, so the `migration` block reaches the error wherever it is caught. Most surfaces do it in the loader; the inference backend definitions do it one frame out, in the boot that catches the library's own error, because that library refuses after the main configuration is already up and the boot has a message of its own to build. `TelemetryConfigError` is a `PipelexConfigError` for this reason — it carries `error_domain = CONFIG` from the class rather than from the agent CLI's lookup table, and it can carry a block.
- The **human handler** prints the fields the model refused and then names `pipelex migrate` when the block says it would write, the dry run when it says it would not, and an edit when there is no block at all.
- The **agent envelope** carries `migration` as a field and its hint says which of the three readings applies — no block, a block that would write, a block that would not; an agent branches on the fields, never on the sentence.
- The **`doctor` row** carries a *finding* — `healthy`, `not_found`, `unparseable`, `out_of_date`, `invalid` — and every caller reads that instead of the row's wording. This one is a correctness fix and not only a tidy-up: `--fix` used to decide what it could repair by searching the message for `"format has changed"`, so rewording the row would have switched the whole repair path off in silence. The finding answers for the one file the row is about: the scan behind `out_of_date` runs over the directory that file lives in — which also holds the `telemetry_*.toml` tier — and the verdict is read off that file's own plan, so a stale tier file beside a wrong base file leaves the base file `invalid`, and the fields the model refused stay on the row. **`out_of_date` means the plan would rewrite that file**, not merely that it is unclean: a file the migration would leave untouched is `invalid`, which is the finding that routes to a person and which `--fix` does not offer to run a command over, and the row keeps the dry run's pointer so the diagnosis is not lost with the finding.

> **Writing a fresh file repairs exactly one finding: a missing one.** There is nothing in a file that is not there to lose. Every other unhealthy state has the user's own settings in it, so an out-of-date file is offered `pipelex migrate` and a broken one is left to a person. Regeneration is still reachable, and it is described as what it is — a way to start over that discards the file.
>
> The two remedies are therefore never printed together. A message that has just carried a migration block has promised that `pipelex migrate` keeps every value the file holds; adding *or run `pipelex init config`, which resets them to their defaults* makes whichever one the reader follows the wrong choice. So the block's presence is what drops the regeneration sentence, and a component with no ledger — the model deck — keeps it, because for that one it is the only answer there is.

## The health report

The boot warns, and the validation error explains — but both of them need something to have gone wrong first, and one of them cannot reach a machine at all. `pipelex-agent` cuts Python's logging off process-wide as its first act, so an agent never sees a boot warning; for a program, **asking is the only channel**, and `pipelex doctor` is the asking.

The doctor's configuration-migration row is a **dry run of `pipelex migrate`** — the command's own run with the writing switched off, not an approximation of it. It reports one of four findings:

| Finding | What it means | What comes next |
|---|---|---|
| `up_to_date` | every file the walk claims is at the current schema | nothing |
| `pending` | at least one file would be rewritten | `pipelex migrate` (and `--fix` offers to run it) |
| `needs_attention` | something is there the command will not do on its own | `pipelex migrate --dry-run`, then a person |
| `unavailable` | the scan itself could not run | check by hand; this is our problem, not the machine's |

Two of those distinctions carry weight. `unavailable` is separate from the rest because **a packaging problem of ours must not be reported as a finding about the user's files** — and, more sharply, must not be reported as health: not knowing is not the same as being up to date. And `pending` is separate from `needs_attention` because only one of them has a command behind it; offering to run a migration over a file it would not change is a prompt whose honest outcome is *nothing was written*.

A run is often both at once, which is the ordinary shape on a machine that has drifted, so the row lists **both sets of files** and names both moves. A reader — or an agent — that heard only the first would stop with a broken file still in place.

> **The row takes no directory, and that is a decision.** Every other check in the doctor reports on a *file* and is scoped to the directory the doctor was pointed at, `--global` included. This one reports on a *command*, and `pipelex migrate` has no `--global`: it walks the global `~/.pipelex/` and the project `.pipelex/` both. A row scoped narrower would name a command that then rewrites a file the row never mentioned — and a tool that writes to a user's files must not spring that. Over-reporting is legible instead: every file is named with its full path, so a reader sees which directory each one is in.

**`--fix` runs the same write pass the command runs.** The row above it *was* the dry run — the same two-pass shape `pipelex migrate` has, with the doctor asking the question in the middle — and fix mode reaches the command's own write half rather than a second implementation that could drift from it. What it does not do is call the command itself: that ends the process when something is left for a person, and the doctor still has rows to render and an exit code of its own to set.

**Nothing inside a file is rendered here either.** The row reports paths and counts. It is the fourth channel the rendering rule covers, beside the command's output, its structured plan, and the block on a validation error.

**A failure inside the scan costs more here than anywhere else**, which is why it is caught rather than raised: an exception escaping this probe reaches the doctor's own outer handler, which prints one line and exits — so a broken packaged ledger would replace *every row the user came for* with "Unexpected error". The catch stays narrow (`MigrationError`, `OSError`), so a bug in our applier still surfaces as itself.

## Applying

> **Operations apply to the user's file, and a template is never the remedy.** "Delete your configuration and re-initialize it" is the failure this project exists to remove, not a fallback it may reach for: re-initializing throws away every choice the user made, and it is exactly what a structural change should not cost them.

### Serialization adds nothing

> **Migration serializes with `tomlkit.dumps` of the mutated document, and nothing else.**

The `.mthds` fix path follows its applier with a canonical reflow of the whole file. That is right for `.mthds` files, which are canonically formatted by CI, and wrong for a user-owned configuration, where a one-key rename must not also rewrite the user's spacing and layout. It is also load-bearing for the guarantees: byte-level replay neutrality only holds if serialization contributes no changes of its own.

Stated more strongly than the library can promise on its own: **a replay in which no operation applies returns the very text it was given** — not a re-serialization of it. Neutrality is therefore a property of the engine rather than of the TOML library it happens to use, and a round-trip can never contribute a change of its own to a file that needed nothing.

### A rename changes a name, and nothing else about the line

> **A key written as a dotted assignment stays a dotted assignment when it is renamed.**

`package_log_levels.pipelex = "INFO"` and a `[pipelex.log_config.package_log_levels]` header say the same thing to a TOML parser and are two different things to a TOML *document*. Which one a key is is not a property of its name — it is a flag the parser sets and the renderer reads — and rebuilding the key from its name alone, which is what the library's own re-key primitive does, silently loses it. A renamed dotted key then came back out as a block header, and **a block header absorbs every scalar that follows it in the same table**: a neighbouring `m = 3` became a key of the renamed table, with an `applied` verdict and nothing said. Renamed at an inner segment the whole chain re-rendered at the document root, taking the subtree out of the table it lived in.

Refusing the layout with a `CONFLICT` was the alternative and it is the wrong trade: a rename has exactly one correct answer on a dotted key, the layout is ordinary TOML that no formatter rewrites, and refusing would strand a reshape's table renames on any file that happens to be written that way. So the applier renames the document's body entries where they sit — every chunk of a key written on several dotted lines, carrying the flag forward — which also stops the library from injecting a cosmetic blank line after a table it renamed in place.

### A comment goes with what it introduces

> **A run of own-line comments and blank lines introduces whatever comes next in the file, and a structural operation keeps it there: a moved key or table takes its introduction along, a deleted one takes its introduction away, and the introduction of whatever came *after* stays where it was.**

The TOML library ties neither of them to the item a reader sees them on. A comment written above a key sits before that key in the same table; a banner written above a `[table]` header sits at the *tail of the previous table in document order*, inside its deepest last container, because everything up to the next header belongs to the table being parsed. So a plain delete-and-re-add of a table left its banner behind — now labelling whatever followed — and carried the *next* section's banner away inside the moved body; appending under an existing table landed *after* that table's trailing banner and stole it the same way. A file seeded from the heavily-commented kit template and migrated by the configuration reshape came out with `# Log Config` above the storage section and `# Plugins` above something else entirely.

The applier now applies the rule a reader applies. What travels or is dropped with an item is **the last block of own-line comments before it, with the blank line above that block and anything below it**; an earlier block in the same run — a file preamble above the first section's banner, a closing note under the previous section — stays where it was, and a run holding no comment at all is spacing and moves whole. At the very top of the document, a *lone* comment block that a blank line separates from what follows is the file's preamble and stays too. An item inserted at the end of a table lands before that table's trailing run, never after it, and everything is put back where the parser would have put it — a previous table's deepest tail rather than an implicit parent's own body — so no `[parent]` header that the file never wrote starts rendering because a comment now sits inside it. The cost of the rule is the rare own-line comment written *below* a key to annotate it, which reads as introducing whatever comes next. Comments *inside* a moved table travel with it as before, and inline tables are left alone.

### The document is re-read between operations that applied

> **Operations are applied one at a time, and the document is parsed afresh after each one that changed it.**

This is a measured requirement, not caution. The position-preserving rename the applier depends on leaves the node's raw `dict` storage out of step with the body it renders from, for any value that is not a table: everything the library renders or looks up still works, but *addressing that key again in the same in-memory document* raises from inside the library. Always-replay runs many operations over one document, so migration is the caller that meets it — the `.mthds` fix path renames tables, which take the branch the library keeps consistent.

Re-reading is exact, because serialization is byte-faithful, and it costs one parse per **applied** operation — which under always-replay is almost never, since the common case is a current file where everything skips. The behaviour is pinned by a characterization test so that a library upgrade which fixes it makes the workaround removable rather than invisible.

### Backups

Always back up, before writing. Exactly one backup per file — a successful run replaces the previous one — named with a UTC timestamp, inheriting the source file's mode rather than the default umask, and with its path printed in the report. For files tracked in git, git remains the durable history; the backup covers the untracked ones and the moment between two commits.

The name is the source file's whole name, extension included, followed by `.bak.` and a compact UTC stamp: `pipelex.toml` backs up to `pipelex.toml.bak.20260815T120000Z`. Extension-included so a backup never shadows a real `.toml`, and separator-free so no filesystem objects to it. Pruning matches that whole shape, stamp included — a copy the user made by hand under a name that merely starts the same way (`pipelex.toml.bak.notes`) is theirs, and is never touched.

**A backup does not belong in the user's `git status`, and pipelex writes the rule that keeps it out.** A project's `.pipelex/` is normally inside a git repository, so one run would otherwise put a dozen untracked `.bak.<stamp>` files in front of the user and leave them to work out which are ours. Pipelex therefore keeps a `.gitignore` *inside* the configuration directory, carrying one rule — `*.bak.[0-9]*Z`, built from the same infix and stamp shape the namer uses, so renaming either cannot leave a rule that matches nothing. In-directory rather than in the repository root because the walk is `~/.pipelex/` and the project `.pipelex/` and nothing else: every backup a migration can write inside a repository is already under a directory pipelex owns, which makes a local file a complete answer that needs no idea where the root is and never edits a file the user maintains for their whole project.

The file is written by `pipelex init`, and by any real (non-`--dry-run`) `pipelex migrate` — the second so that a machine whose `.pipelex/` predates this gets the rule from the very run that would otherwise dirty it. It is **create-if-absent and nothing more**: once a `.gitignore` is there it is a file in the user's repository, possibly theirs, possibly ours with a line taken out on purpose, and re-asserting a rule into it every run would be a tool arguing with its user. Two omissions are deliberate. A `.rescue.` copy is **not** ignored — it exists only because a write could not be vouched for and the report tells the user to go and get it, so turning up in `git status` is that reminder working. Neither is a copy the user named themselves: pruning already refuses to touch a `pipelex.toml.bak.notes` on the grounds that it is theirs, and hiding it from their own `git status` would be the same mistake pointed the other way.

The order of the three steps is itself a guarantee. The backup is written **first**, so there is never a moment with a rewritten file and no copy of the original; the older backups are pruned **last**, so there is never a moment with no backup at all; and a write that fails before touching the file takes its own fresh backup with it, so a failed run leaves the directory exactly as it found it. Nothing that happens after the file is written can un-write it in the report: an older backup that will not prune, or a temp file the transaction could not remove, is a warning on a migrated file, never a blocked one.

Three further rules make that safety net worth the name.

> **A run never overwrites or removes a copy it did not make.** The stamp resolves to the second, so two runs of the same file can address the same name. The second reserves the name atomically, finds it taken, and leaves what is there — because what is there is a copy of an *older* state of the file, which is to say the original if anything is. The same rule governs the other direction: a run whose write is refused deletes the copy it made and never the copy it found.

> **A copy the run cannot vouch for leaves the rotation.** When a write ends `state_uncertain`, the backup is renamed out of the `.bak.` family into `.rescue.` — `pipelex.toml.rescue.20260815T120000Z` — which pruning does not match. Otherwise the next successful run of that file would delete the very copy the report told the user to go and get. A rescue copy is never collected by anything but the user. When the copy cannot be moved — it is another run's, or the rescue name is taken, or the rename will not go — it stays where it is rather than being lost to a tidier name, and the report says the copy is still in the rotation and asks the user to take it now, instead of promising it will be waiting.

> **The copy is durable before the file it copies changes.** Its bytes are `fsync`-ed by the staged write and its name by an `fsync` of the directory it lands in, so "back up first, replace second" survives a power loss and not only a process exit. The replacement of the target is deliberately *not* synced in turn: a migration lost to a crash is replayed by the next run, while a lost backup is lost.

What a backup carries across is the file's **permission bits**, and that is the one deliberate exception to "no value read from a user's file is ever rendered" — a backup contains the user's values by definition, so a `0600` configuration must not acquire a world-readable copy beside it. Ownership, ACLs and extended attributes are **not** carried across the replace, on either the backup or the migrated file: an atomic same-directory replace cannot preserve what the running process has no right to set, and re-attaching an attribute blindly (a quarantine flag, a security label) is a worse guess than leaving it off. The security-relevant bit of a configuration file is its mode.

A configuration file that is a **symlink** is followed: the file the user means is the one at the end of the link, so the run reads, backs up and replaces *that* file, and the link survives. Replacing the link path instead would put a regular file where the link was and leave the real file unmigrated. The plan keeps naming the path the directory walk found; the backup path shows where the bytes actually went. This is what the `.mthds` fix loop already does with its own targets. The two callers differ on one half, and the difference is deliberate: **a migration's write scope is the resolved target of any file the walk claims**, not the walked directories themselves. The `.mthds` fix loop pairs its resolution with a write-scope check because it is handed a bundle directory and must not write outside it; a configuration directory is a place a user keeps links to files they own, and a dotfiles repository is the ordinary reason one is there. Refusing it would mean the tool declines to migrate exactly the machines whose owner was most deliberate about their configuration. The plan names the walked path and the backup names the resolved one, so a run that followed a link out of the directory says so. The reasoning behind both readings is in `wip/migrator/migrator-write-scope-and-rename-fidelity.md`.

### Per-file transactions

Each file is written transactionally and independently: snapshot, stage, atomic replace, restore on failure. A file that cannot be processed is reported as blocked, with the reason naming the state it is in, while its siblings proceed. No run leaves a partially rewritten file behind.

## Limits you will meet

These are measured properties of the TOML library the engine uses, not aspirations. They are stated here because a user or an author will run into them, and being surprised by them is worse than being told.

- **Arrays of tables are unaddressable, and reserved.** An `[[entry]]` node is a list, and no `table_path` segment syntax reaches it or anything under it; the `*` wildcard has no array form. One surface carries one today — the telemetry configuration's `otlp` list of exporters — and the fingerprint records it as a terminal `list[table]`: what happens *inside* an exporter entry (a renamed field, a tightened bound, a new required member) is invisible to the coverage gate, so a change there is the author's to account for by hand, exactly as validator-expressed narrowing is. Addressing what lies beneath one needs a new segment kind and a decision on the day — until then, an operation pointed at one resolves nothing and is reported as a guarded skip rather than raising.
- **Comment ownership is a reading, not a fact.** The TOML library records where a comment *sits*, never what it is *about*, and the applier reads a run of own-line comments as introducing whatever follows it (see [A comment goes with what it introduces](#a-comment-goes-with-what-it-introduces)). That reading is right for a banner above a section, for the kit's per-key comments, and for a preamble at the top of a file; it is wrong for a comment written on its own line *below* a key to annotate it, which will follow the next item instead. A migration keeps a file's comments on the sections and keys they introduce — it does not, and cannot, know what any comment means.
- **A migration is not byte-minimal.** A rename normalizes the spacing around its own `=`, and a renamed table that was written out of order across several chunks loses its own bare header while a plain table keeps it. Both forms are semantically identical, both are stable under replay, and neither accumulates — but a migration diff is not always the minimal diff a human would have written.
- **A guarded skip is never an error.** Every operation whose target does not resolve reports itself skipped rather than raising. That guard is what makes always-replay possible, and it is why a misdirected operation is caught by the checks rather than by a crash on a user's machine.
- **A renamed key cannot be addressed again in the same in-memory document.** The position-preserving rename updates the body the document renders from but leaves the node's raw `dict` storage stale, for any value that is not a table. Nothing the library renders or looks up is affected — which is why a single rename is correct, and why the `.mthds` fix path, whose renames target tables, never meets it. The engine [re-reads the document between operations that applied](#the-document-is-re-read-between-operations-that-applied), so nothing downstream has to know about this; it is recorded here because it explains a piece of the engine that would otherwise look like superstition.

## Authoring an entry

The gate says what is missing; you should not be composing entries by hand from a diff. The intended loop:

1. Make the schema change.
2. Run the coverage check. It refuses the change and names every removed path and enum member that lacks accounting, every path whose value domain narrowed, every destination that does not match an added path, and every added path that has no default.
3. Write the entry — or have the migration-authoring skill derive it from the fingerprint diff, bump the surface's schema version, regenerate the fingerprint golden and snapshot the transform goldens.
4. Add the changelog entry. The changelog and the ledger are deliberately separate artifacts saying the same thing to different readers; the release process is where they are checked against each other.

A release can never ship a moved schema without its entry: the release procedure runs the coverage check before the version bump, and refuses a bumped schema whose ledger has not moved with it.

## Related

- [Configuration Internals](contribute/configuration-defaults-and-overrides.md) — how the configuration layers merge, which this contract sits upstream of.
- [Drift Contracts](contribute/drift-contracts.md) — why the checks here are derived checks rather than review obligations: anything mechanizable becomes a derived check, and coverage, convergence, transform goldens and reserved-path checking all are. The one part that is not mechanizable — [domain narrowing expressed in a validator](#the-fingerprint) — is a review obligation instead, and the `config-docs` contract carries these ledgers in its review list for it.
