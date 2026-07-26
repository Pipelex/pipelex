# Renaming the layers and the hubs — `runtime` / `interpreter`

**Status:** decided, not started. **Do this AFTER H-4 lands green** (see [Sequencing](#sequencing--why-this-window-matters)).

Decided by Louis on 2026-07-26, at the close of the hub-split refactor, after challenging the naming that Phases 0–4 shipped. This document is the record of *what* was decided and *why*, plus the mechanical plan. Read [Why](#why-the-current-names-are-wrong) before executing — the rationale is what stops a future session relitigating this or half-applying it.

## The decision

| | was | becomes |
| --- | --- | --- |
| the low layer | "low layer" | **the runtime layer** |
| the high layer | "high layer" (mostly unnamed) | **the interpreter layer** |
| the low hub | `pipelex/service_hub.py` · `ServiceHub` | `pipelex/runtime_hub.py` · **`RuntimeHub`** |
| the high hub | `pipelex/method_hub.py` · `MethodHub` | `pipelex/interpreter_hub.py` · **`InterpreterHub`** |

The one rule, restated — and note it now needs no gloss:

> **The interpreter hub may import the runtime hub. The runtime hub must never import the interpreter hub.**

The headline property, restated in the same vocabulary:

> **Importing the Pipelex runtime loads zero interpreter modules.**

That second sentence is both the measurement the closure test pins and the outward-facing claim: *the inference engine does not know the MTHDS language exists — you can embed it without loading a line of the interpreter.*

## Why the current names are wrong

### "Low" / "high" — the tell is that only one side got a name

Low/high is fine for a *lint* (the guard checks arrow direction, and direction is relational). It is wrong as the *conceptual* vocabulary, for three reasons:

1. **Only one side was ever enumerated**, so the other side has no handle. Across the Phase 3 and Phase 4 docs the same concept got coined fresh every time it was needed: "the Pipe-touching remainder", "the high half", "the interpreter". When every author invents a term, the term is missing.
2. **"Low-level" connotes primitive / plumbing / the boring part.** That is exactly backwards: the low half is the inference engine, arguably the most valuable code in the repo.
3. **It is contentless.** "Our low layer does not import our high layer" describes our dependency graph. It tells a reader nothing about what either layer *is*, and it sells nothing.

**The codebase had already converged on the right word for one side and nobody noticed.** The measurement snippet, the closure test and the guard docstrings all say *interpreter* (`INTERPRETER = {"libraries", "pipe_operators", "pipe_controllers", "codegen", "builder"}`), and `pipelex/core/interpreter/` exists. Only the guard identifiers and the doc headings still said "high".

### Rejected alternatives for the low layer, with reasons

Recording these so they are not re-proposed:

- **`inference`** — a subset masquerading as the whole. `tools`, `system`, `reporting` and the entire value data model are not inference. It also collides with live usage: the docs and closure test already say "the inference layer" to mean `cogt` specifically ("importing the inference layer must not load the interpreter"). Widening the term makes that sentence ambiguous.
- **`INTERPRETER_FREE_*`** — defined by exclusion. Louis' objection, and correct: a layer should be named for what it is.
- **`foundation`** — genuinely viable, and the fallback if the nesting cost below ever bites. Positive, no collision, sells fine. Passed over only because it is less informative than `runtime` and does not share a word with the hub.
- **`engine`** — same defect as `inference`: console, secrets, storage and the value data model are not engine.
- **`platform`** — collides with `pipelex-platform`, our hosted CRUD API.
- **`core`** — catastrophic: `pipelex/core/` exists and *straddles both layers*.
- **`kernel`** / **`base`** / **`substrate`** — respectively OS-loaded (and `pipelex/kit/` exists), flat (and `base_exceptions.py` exists), and cold jargon.

### Why `runtime` / `interpreter` won

It is the textbook language-implementation split, so it explains itself to any developer who has implemented a language: the **runtime** is the machinery present at execution time (allocator, stdlib, FFI — here: models, workers, config, values); the **interpreter** reads the program and executes it (here: reads `.mthds`, builds pipes, routes them).

It also gives **one word across layer and hub** rather than two vocabularies: `runtime_hub` lives in the runtime layer, `interpreter_hub` in the interpreter layer.

**Known cost, accepted:** the workspace `CLAUDE.md` calls all of `pipelex/` "the Python runtime", so "the runtime layer" nests inside "the runtime". Mild, and identical to the tension in `runtime_hub`, which Louis accepted explicitly.

### `service_hub` → `runtime_hub`

Two reasons.

1. **Commercial collision.** Once "the Pipelex service" means the hosted product, `from pipelex.service_hub import get_secret` is ambiguous — and after the cross-repo sweep that exact line lands in `pipelex-platform`, `pipelex-api` and `pipelex-api-hosted`, repos that *are* the service. The word means two different things one line apart.
2. **"Runtime" names the role, "service" named the mechanism.** The container holds config, console, secrets, storage, telemetry, the model deck, the inference workers, the content generator, reporting, run mode, tracing and the plugin registries — ambient machinery that lives for the process and is needed to execute anything, whatever is loaded. That is a runtime. "Service" only described how it is injected.

Louis waved off the proximity to the existing `runtime_bridge` package. Worth one clarifying sentence in `hub-layering.md` anyway, because `plugins → runtime_bridge` appears in the Known-inversions list, so the two names will sit near each other and a reader may infer a relationship.

### `method_hub` → `interpreter_hub`

`method_hub` was **already flagged as a knowing concession** at D1 of the original plan: *"`method_hub` borrows the MTHDS noun for a runtime container — acceptable because the object genuinely holds the loaded method's libraries, but it is a conscious call against the brand-boundary rule."* Three defects:

1. **"Method" is an MTHDS/product noun, not a Pipelex runtime noun.** Inside `pipelex/` the vocabulary is bundle / library / pipe / domain / concept; "method" lives at the language and hosted-product level (`method_id`, `mt_…`, `mthds_run`). The brand rule in the workspace `CLAUDE.md` says MTHDS owns the language nouns and Pipelex owns the runtime ones — this borrows in the forbidden direction.
2. **It misdescribes the contents** — the container holds a `LibraryManager`, the concept/domain/pipe libraries, a current-library binding, the router, the pipeline manager, the PipeFunc executor.
3. **The singular is misleading.** Multiple libraries can be open, bound per async context; "method hub" implies one method.

Two alternatives were considered and rejected **in this order**, so do not circle back to either:

- **`library_hub`** — rejected by Louis: a library is *inert*, while the container is active machinery (router, pipeline manager). Naming it for the passive artifact undersells it.
- **`pipe_hub`** — proposed by Louis, rejected on evidence: it is **narrower than its contents**. A meaningful share of the hub is concepts and domains, not pipes (`get_concept_library`, `get_required_concept`, `get_native_concept`, `get_required_domain`, `get_optional_domain`), plus the library binding and dirs. `get_native_concept()` on a `pipe_hub` reads wrong, and those concept accessors are load-bearing — they are exactly what the runtime layer consumes through `ConceptProviderAbstract` after Phase 4. `pipe_hub` makes the same class of error as `library_hub`, in the opposite direction: one too passive, the other too narrow.

`interpreter_hub` covers pipes, concepts, domains and the execution machinery under one true idea: *everything bound to the method you loaded, and the thing that runs it.*

**On the `pipelex/core/interpreter/` collision** — this was raised as an objection and then withdrawn, deliberately. It only holds if the layers keep the low/high names. Once the layer is *called* the interpreter layer, `core/interpreter/` sitting inside it is a part-of relationship, exactly as consistent as `runtime_hub` living inside "the runtime". Not a collision.

## Sequencing — why this window matters

**Land H-4 green first** (`make agent-test` + both drift contracts), so there is a known-good commit, then do the rename as its own commit *before* the release and *before* the cross-repo sweep.

The load-bearing fact: **the cross-repo sweep has not happened yet.** External repos still import `pipelex.hub` — they are broken either way and get rewritten exactly once. Renaming now costs **zero** extra cross-repo churn. Renaming after the sweep means doing it twice, and the second time is a published-contract break with no cover story. The CHANGELOG entry is written but unreleased, so the announcement absorbs it for free.

Doing it as a separate commit (not amended into H-4) keeps a clean bisect point, since it touches ~300 files mechanically.

## Before you start — verify no collisions

Not checked exhaustively when the decision was taken. Do this first:

```bash
# in the workspace root, not just _hub
grep -rn "runtime_hub\|RuntimeHub\|interpreter_hub\|InterpreterHub" --include="*.py" --include="*.md" .
```

`pipelex-temporal/` is private — check it out and grep it too; it is the heaviest consumer (35 files import `pipelex.hub` today).

## The mechanical plan

Counts below are files, measured at commit `46e76c953`.

### 1. The two modules

- `git mv pipelex/service_hub.py pipelex/runtime_hub.py`
- `git mv pipelex/method_hub.py pipelex/interpreter_hub.py`
- Class renames: `ServiceHub` → `RuntimeHub`, `MethodHub` → `InterpreterHub`.
- Accessor renames: `get_service_hub` / `set_service_hub` → `get_runtime_hub` / `set_runtime_hub`; `get_method_hub` / `set_method_hub` → `get_interpreter_hub` / `set_interpreter_hub`.
- Update both module docstrings — they open with the layering rationale.

### 2. Call sites

| import | files in `pipelex/` | files in `tests/` |
| --- | --- | --- |
| `pipelex.service_hub` | 113 | 66 |
| `pipelex.method_hub` | 55 | 135 |

Rewrite via an `ast` pass over whole import statements, **not regex** — the same hazard as Phase 1: parenthesized multi-line import blocks. Phase 1's rewriter is the model.

⚠ **String literals are the landmine, again.** This is the lesson that cost 36 broken tests at H-1: an import rewrite is blind to `mocker.patch("pipelex.service_hub.get_console", ...)`, `importlib.import_module(...)`, and any config-driven dotted path. Sweep for the string forms separately:

```bash
grep -rn '"pipelex\.service_hub\|"pipelex\.method_hub\|'"'"'pipelex\.service_hub\|'"'"'pipelex\.method_hub' pipelex tests
```

### 3. Also rename these attributes / locals

- `pipelex/pipelex.py:125-128` — `self.service_hub` / `self.method_hub` instance attributes (and every reader of them).
- `pipelex/system/registries/class_registry_access.py` — the `class_registry_scoping` slot is installed by `set_method_hub`; its docstring names the hub.
- `pipelex/plugins/registrar.py` — `HubSlot` is *not* affected (its members are capability names: `CONTENT_GENERATOR`, `PIPE_ROUTER`, …). Leave it. `HubSlotAlreadyClaimedError` likewise.

### 4. The guard — `pipelex/cli/dev_cli/commands/hub_layering_guard.py`

| identifier | becomes |
| --- | --- |
| `LOW_LAYER_PACKAGES` | `RUNTIME_LAYER_PACKAGES` |
| `is_low_layer(...)` | `is_runtime_layer(...)` |
| `METHOD_HUB_MODULE` | `INTERPRETER_HUB_MODULE` (value `"pipelex.interpreter_hub"`) |
| `HubLayeringViolationKind.METHOD_HUB_IMPORT` | `INTERPRETER_HUB_IMPORT` (wire value `"interpreter-hub-import"`) |
| `HubLayeringViolationKind.METHOD_HUB_REFERENCE` | `INTERPRETER_HUB_REFERENCE` (wire value `"interpreter-hub-reference"`) |

`DELETED_HUB_MODULE = "pipelex.hub"` **stays exactly as is** — that rule is about the module that was deleted in Phase 1 and is unrelated to this rename. Keep its `# hub-layering: ignore` marker.

Also update the module docstring (it states both rules and the carve-outs) and `HubLayeringViolationKind.remedy`, whose strings name the hubs.

Leave the escape hatch spelling `# hub-layering: ignore` alone — "hub layering" is still accurate, and changing it would silently un-suppress the two lines that carry it.

### 5. Tests

Contents first — every one of these needs its import lines, constants and patch-target strings swept:

- `tests/unit/pipelex/test_hub_import_closure.py` — `LOW_LAYER_ENTRY_POINTS` → `RUNTIME_LAYER_ENTRY_POINTS`; the module docstring states the property.
- `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py` — `test_low_layer_membership` → `test_runtime_layer_membership`; `test_core_is_split_between_the_layers` keeps its name but its assertions call the renamed predicate.
- `tests/unit/pipelex/test_hub_lifecycle.py`, `tests/unit/pipelex/test_hub_class_registry.py` — import lines and any patch-target strings.

**Module renames — Louis' call: rename them as part of this work.** Note first that `test_hub_*` is not *stale*: "hub" survives the rename (there are still two hubs, and `hub_layering_guard.py` / `check-hub-layering` / `hub-layering.md` are all unchanged). So apply the repo's actual convention — a test module mirrors its source module, or else names the property it pins — which moves two and leaves two:

| module | action | why |
| --- | --- | --- |
| `test_hub_import_closure.py` | → **`test_runtime_layer_import_closure.py`** | It pins a property, not a module: *the runtime layer loads no interpreter*. Naming the layer makes the file findable from the vocabulary. |
| `test_hub_class_registry.py` | → **`test_class_registry_scoping.py`** | It is the D5 regression guard for the `class_registry_scoping` slot, not a test of "the hub". The current name has always been imprecise. |
| `test_hub_lifecycle.py` | **keep** | It pins that a boot installs *both* hub singletons and that teardown drops the scoping one installed. "Hub lifecycle" is exactly what that is, and both hubs still exist. |
| `cli/dev/test_hub_layering_guard.py` | **keep** | Mirrors its source module `hub_layering_guard.py`, which is not renamed. Moving it would break the mirror. |

⚠ **Renaming test modules needs a cache reset.** Per the repo `CLAUDE.md`, moving or deleting tests confuses pytest collection and the linters — run `make cleanderived` afterwards. That deletes `tests/integration/pipelex/fixtures/_generated_model_sets.py`, after which pyright fails with unresolved-import errors unrelated to your change; `make regenerate-test-models-quiet` restores it. Do this *before* concluding anything failed.

### 6. `subject_grants.toml`

29 entries under `pipelex/service_hub.py::`, 26 under `pipelex/method_hub.py::`.

⚠ **Migrate the grants BEFORE running any check.** Two independent traps, both hit this session:
- `make fko` runs early in `agent-check` and will silently make an ungranted subject keyword-only.
- Staleness is symmetric: a grant whose def moved hard-fails `make cko` until the registry is fixed.

The path prefix and the class name both change (`ServiceHub.` → `RuntimeHub.`, `MethodHub.` → `InterpreterHub.`).

### 7. Build and CI

- `Makefile` — the `check-hub-layering` target's `PRINT_TITLE` says "Enforcing the service_hub / method_hub layering boundary" (line ~362) and the help text at line ~159. The target name and the `chl` alias can stay: "hub layering" is still what it checks.
- `.github/workflows/lint-check.yml` — job `lint-hub-layering` (line ~137). **Do not rename the job**: it may be a required status check, and a rename silently un-requires it. Nothing to change here unless the target name changes.
- `.github/workflows/lint-fresh-check.yml` — runs `make check-hub-layering`; unaffected.

### 8. Docs

- `docs/contribute/hub-layering.md` — the largest edit. Retitle the layers throughout, rewrite "The two halves" headings, update the Enforcement rule list, and add the `runtime_bridge` clarifying sentence. Keep the "Where core splits" section's *content* — only its layer vocabulary changes.
- `docs/under-the-hood/architecture-overview.md` — "What Keeps The Layers Apart: The Two Hubs" section and the paragraph on core straddling the line.
- `CHANGELOG.md` — amend the `[Unreleased]` breaking-change entry rather than adding a second one. It currently announces `pipelex.hub → pipelex.service_hub / pipelex.method_hub`; it should announce the final names directly, since `service_hub` / `method_hub` will never have shipped.
- Grep the rest: `docs/under-the-hood/{pipe-routing-and-execution,runtime-bridge-and-transport,execution-graph-tracing}.md`, `docs/advanced/`, `tests/CLAUDE.md` (its "root-level modules" trigger list names both hubs), and in-code docstrings.
- `tests/CLAUDE.md` also lists `pipelex/service_hub.py` / `pipelex/method_hub.py` under "When to run full `make agent-test`".

### 9. This branch's own tracker

`TODOS.md` and `wip/hub/hub-split-refactor.md` are dense with `service_hub` / `method_hub`. They are historical records of the refactor, so a mechanical sweep is fine — but keep D1's rejected-alternatives reasoning intact and add a pointer to this document.

## Gates

`make agent-check` · full `make agent-test` (a rename of this size touches root modules, so per `tests/CLAUDE.md` the full suite is the correct gate) · `make drift-check`.

Expect **`cli-docs` to fire** — the rename touches many CLI modules' import lines. `config-docs` will likely fire too. Both are import-path-only for this change, but review honestly against the targets before acking, per the `drift-review` skill.

## Cross-repo

This **replaces**, not adds to, the first wave of the [cross-repo sweep](../../TODOS.md#cross-repo-sweep): external repos go straight from `pipelex.hub` to `pipelex.runtime_hub` / `pipelex.interpreter_hub`, never touching the intermediate names. Update the sweep tables in `TODOS.md` to the final names as part of this work, so the sweep is done once with the right target.

Affected: `pipelex-temporal` (35 files, private), `pipelex-mistralai-workflows` (11), `pipelex-api` (9), `pipelex-cookbook` (2), `cocode` (2). `get_pipelex_hub` splits into `get_runtime_hub` / `get_interpreter_hub`.
