---
title: "Hub Layering"
description: "The runtime_hub / interpreter_hub boundary — what lives in each layer, the one-arrow rule, and how it is enforced."
---

# Hub layering convention

Pipelex resolves its cross-cutting dependencies through a *hub*: a singleton container plus a set of module-level accessor functions, so a component can reach the config, a worker, or the pipe library without importing the module that owns it. There are **two** hubs, one per layer, and which one a symbol lives on is an architectural boundary, not a filing preference. This document is the canonical specification of that boundary.

The two layers are the textbook language-implementation split:

- **The runtime layer** is the machinery present at execution time whatever is loaded — config, console, secrets, storage, telemetry, the model deck and inference workers, the content generator, reporting, and the value data model. Its hub is `runtime_hub`.
- **The interpreter layer** reads a method and executes it — the libraries, the pipes, the router, the pipeline manager. Its hub is `interpreter_hub`.

Do not read `runtime_hub` as related to the `pipelex.runtime_bridge` package: they share a word, but the hub is the runtime layer's service container while `runtime_bridge` is a transport.

## The one rule

> `interpreter_hub` may import `runtime_hub`. **`runtime_hub` must never import `interpreter_hub`.**

That single arrow is the whole architecture. Everything below is a consequence of it.

Only the *forbidden* direction is load-bearing. The permitted one is currently unused: the one runtime-layer thing `interpreter_hub` needs is the class-registry scoping slot, which lives below *both* hubs (see [The class-registry exception](#the-class-registry-exception)). So today, importing either hub loads the other in neither direction — which is stronger than the rule requires, not a violation of it.

There is deliberately **no** `pipelex.hub`. It was deleted rather than kept as an alias for either layer, so a stale import fails loudly at import time instead of silently resolving to the wrong layer.

## The two layers

### `pipelex/runtime_hub.py` — process-scoped infrastructure

`RuntimeHub` holds what is configured once at boot and never varies per method:

| group | symbols |
| --- | --- |
| container | `RuntimeHub`, `get_runtime_hub`, `set_runtime_hub` |
| config | `get_required_config`, `get_optional_config` |
| console | `get_console` |
| secrets | `get_secrets_provider`, `get_secret` |
| system registries | `get_class_registry`, `get_func_registry` |
| storage | `get_storage_provider` |
| telemetry | `get_telemetry_manager`, `get_otel_tracer` |
| models | `get_models_manager`, `get_model_deck`, `get_sdk_client_manager` |
| inference | `get_inference_manager`, `get_llm_worker`, `get_img_gen_worker`, `get_extract_worker` |
| content generation | `get_content_generator`, `scoped_content_generator` |
| reporting | `get_report_delegate`, `is_in_isolated_execution` |
| run mode | `is_dry_run_forced` |
| tracing | `scoped_event_log`, `get_event_log_override` |
| plugin registries | `get_inference_backend_registry`, `get_model_lister_registry`, `get_orchestrator_registry`, `get_bundle_validator_registry`, `get_storage_provider_registry`, `get_secrets_provider_registry` |

### `pipelex/interpreter_hub.py` — library-scoped method machinery

`InterpreterHub` holds what belongs to the *loaded method*:

| group | symbols |
| --- | --- |
| container | `InterpreterHub`, `get_interpreter_hub`, `set_interpreter_hub` |
| library manager | `get_library_manager`, `get_library` |
| library lookups | `get_concept_library`, `get_required_concept`, `get_native_concept`, `get_required_domain`, `get_optional_domain`, `get_pipe_library`, `get_pipes`, `get_required_pipe`, `get_optional_pipe`, `get_pipe_source` |
| current-library contextvar | `set_current_library`, `get_current_library`, `get_current_library_id_or_none`, `clear_current_library`, `scoped_current_library` |
| library dirs | `resolve_library_dirs`, `get_default_library_dirs` |
| pipe router | `get_pipe_router`, `set_pipe_router`, `teardown_current_pipe_router`, `scoped_pipe_router` |
| run | `get_pipe_run`, `get_pipeline_manager`, `get_pipeline` |
| pipe func | `get_pipe_func_executor`, `scoped_pipe_func_executor`, `get_pipe_func_executor_registry` |

Setters follow their getters onto the matching container.

### Which hub does a new symbol belong to?

Ask **what its lifecycle is**, not what package it happens to be typed by:

- Configured once at boot from config + plugin registration, identical for every method the process runs → `runtime_hub`.
- Tied to a loaded method's libraries, or varying with the current library → `interpreter_hub`.

Placement is decided by *kind*, not by who currently imports it. Several accessors have no in-tree importer (`get_bundle_validator_registry`, `get_orchestrator_registry`, `get_default_library_dirs`, …) — they are live plugin contract and are reached through the container. Do not relocate or delete one because a grep looks empty.

`get_pipe_func_executor_registry` is the one placement worth flagging: it is a plugin registry by kind (which would put it in the runtime layer) but its protocol lives in `pipe_operators/func/` (which puts it in the interpreter layer). It is **interpreter-layer**. See [Known inversions](#known-inversions) for the underlying wart.

## Why the boundary exists

`runtime_hub` must not name anything from `libraries`, `pipe_operators`, `pipe_controllers`, `codegen`, `builder`, `core.bundles`, `core.interpreter`, or the Pipe-touching modules of `core.pipes` at module level. Those module-level imports exist only to type the getters, but they are what made a single hub drag the entire method interpreter into every consumer that just wanted `get_console()`.

The property that matters is measurable: **importing the Pipelex runtime loads zero interpreter modules.** That is both the assertion the closure test pins and the outward-facing claim — the inference engine does not know the MTHDS language exists, so you can embed it without loading a line of the interpreter. Verify it from the repo root on a synced venv:

```bash
.venv/bin/python - <<'PY'
import sys
from pathlib import Path

import pipelex.cogt.content_generation.content_generator  # noqa: F401

INTERPRETER = {"libraries", "pipe_operators", "pipe_controllers", "codegen", "builder"}
loaded = {name: mod for name, mod in sys.modules.items() if name.startswith("pipelex.")}
interpreter = sorted(n for n in loaded if n.split(".")[1] in INTERPRETER)
sloc = 0
for mod in loaded.values():
    file = getattr(mod, "__file__", None)
    if file:
        sloc += sum(1 for line in Path(file).read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#"))
print(f"pipelex modules: {len(loaded)} | sloc: {sloc} | interpreter modules: {len(interpreter)}")
print("offenders:", interpreter)
PY
```

`interpreter modules` must print **0**. When it does not, the `offenders` list names the modules that leaked, and the shortest import path to one of them is what to fix. Swap the imported module to measure any other entry point.

## Where core splits

`pipelex/core/` is not one layer, and trying to declare it one was the mistake this section records. It holds two different kinds of thing:

- **The data model — runtime.** `core.concepts`, `core.domains`, `core.stuffs`, `core.memory`, the input/output *specs* under `core.pipes.inputs` and `core.pipes.stuff_spec`, and `core.pipes.pipe_output`. These describe what a method's values *are*. Nothing in them needs a loaded method, and each measures **zero** interpreter modules. `pipe_output` reads as Pipe machinery but is not: it names no `Pipe` — it holds the working memory, graph spec and usage a run *produced* — and it sits inside `runtime_hub`'s own closure (the chain under [The class-registry exception](#the-class-registry-exception) passes straight through it). It is the one runtime-layer module the [guard's declaration](#the-rule--make-check-hub-layering) does not cover, because that declaration is deliberately package-granular; the closure test covers it instead, since an `interpreter_hub` import there would fail the `pipelex.runtime_hub` entry point.
- **The Pipe machinery — interpreter.** `core.pipes.pipe_abstract`, `pipe_blueprint`, `pipe_factory`, `core.pipes.rendering`, `core.bundles`, `core.interpreter`, and `core.registry_models`. Every one of them names a `Pipe`, and a pipe is the interpreter's own object — they import `pipe_operators` / `pipe_controllers` / `libraries` **directly**, not through a hub. `core.bundles.pipelex_bundle_blueprint` is a discriminated union over every pipe blueprint; `core.registry_models` is a registry of every pipe kind. No amount of dependency injection makes those runtime.

So the runtime-layer declaration lists core's data-model packages by name. `pipelex.core` itself is deliberately *not* a declared package: writing it would claim a property the measurement contradicts.

The dividing line is worth stating as a rule of thumb: **if it names a `Pipe`, it belongs to the interpreter layer.**

### Injected providers, not ambient lookups

The data-model half used to reach for `get_concept_library()` / `get_native_concept()` / `get_required_concept()` — ambient lookups into a loaded method, which is exactly what made `core/` inseparable from the interpreter. They now take what they need as a parameter:

- `ConceptProviderAbstract` (`pipelex/core/concepts/concept_provider_abstract.py`) — resolve a ref, a code, or a native code into a `Concept`, and answer compatibility questions.
- `PipeProviderAbstract` (`pipelex/core/pipes/pipe_provider_abstract.py`) — resolve a pipe code into a `PipeAbstract`.

Both are **read-side only**. Managing a library — adding, removing, listing, setup/teardown — stays in the interpreter layer: `ConceptLibraryAbstract` and `PipeLibraryAbstract` now *extend* these, keeping their management half in `libraries/`. Splitting read from write is what lets a core module state its dependency honestly ("I need something that can resolve concepts") without inheriting a library lifecycle it has no business touching.

The injection point is the interpreter layer. `pipe_factory`, `input_renderer` and `output_renderer` — already interpreter-bound, so nothing is lost — call `get_concept_library()` / `get_required_pipe` themselves and pass the result down; `pipeline/execution_seams.py` does the same for `WorkingMemoryFactory`. That is the one-way arrow the whole design rests on, applied inside `core/`: **the half that knows about a loaded method resolves the collaborator and hands it downward.**

When you add a core data-model function that needs a concept or a pipe, add a `concept_provider` / `pipe_provider` parameter. Do not add a hub import — the guard will reject it, and the closure test will tell you which entry point you broke.

## Placement, not coupling

Splitting the hub removes the *lookups* that crossed the boundary. It does not move a type that was simply filed in the wrong package — and a misfiled type drags its whole package into every closure that names it. Two were resolved this way; both are worth knowing as the pattern to apply to the next one.

**`JobMetadata` moved to `pipelex/system/`.** It is an argument to essentially every `cogt` call, yet it lived in `pipelex/pipeline/` — which made `cogt → pipeline` the fattest remaining edge and pulled `graph.trace_context` into every closure that touched inference. `JobMetadata`, `JobCategory` and `UnitJobId` now live in `pipelex/system/job_metadata.py`, and `JobMetadataError` moved from `pipeline/exceptions.py` to `pipelex/system/exceptions.py`. `cogt → pipeline` is now **zero statements**.

`TraceContext` moved with it, to `pipelex/system/trace_context.py`: it is the transport `JobMetadata` carries, so leaving it in `graph/` would only have renamed the inversion to `system → graph`. Its one dependency on the graph package — `DataInclusionConfig`, nested under `[...graph_config.data_inclusion]` in the TOML — moved down to `pipelex/system/data_inclusion_config.py`, which `graph_config.py` now imports. The TOML shape is unchanged; only the class's home moved, which is what keeps `trace_context` from re-importing `mermaid_config` and `reactflow_config` through `GraphConfig`.

**The templating primitives moved down into `tools/`.** `TemplateCategory`, `TemplatingStyle`, `TagStyle` and `TextFormat` sat under `cogt/templating/` while eight `tools/jinja2/` and `tools/mermaid/` modules imported them — so `tools`, the intended bottom layer, depended on `cogt`. None of the three modules holding them named anything from `cogt`, so this was pure misfiling:

- `TextFormat` and `TemplatingStyle` / `TagStyle` → `pipelex/tools/templating/`, which imports nothing from `pipelex` beyond its own sibling. It is a leaf.
- `TemplateCategory` → `pipelex/tools/jinja2/`, because its entire payload is a map of jinja2 filters. Filing it in `tools/templating/` would have made that package import `tools/jinja2` while `tools/jinja2` imports it back — a cycle inside one layer. As placed, the edges run one way: `tools/mermaid → tools/jinja2 → tools/templating`.

What stays in `cogt/templating/` — `TemplateBlueprint`, the sigil preprocessor, the rendering entrypoint — belongs there: a blueprint is language-layer, and the rest imports `tools/jinja2` downward.

**`resolved_fields` moved down into `core/concepts/`.** The neutral resolved-field layer — one structure field becoming a `ResolvedType` tree — lived under `pipelex/codegen/` while `core/concepts/structure_generation/generator.py` imported it, which put `pipelex.codegen` into the closure of every core module that reached structure generation. It names nothing outside `pipelex.core`, so this was misfiling again: it now lives at `pipelex/core/concepts/resolved_fields.py`, and the codegen emitters import it upward.

**The two renderers regrouped into `core/pipes/rendering/`.** `input_renderer` sat in `core/pipes/inputs/` beside genuinely runtime-layer modules while `output_renderer` sat alone in `core/pipes/output/`. Both render a `PipeAbstract` for a human or an agent, so both belong to the interpreter layer — and leaving `input_renderer` where it was would have forced the runtime-layer declaration to be a list of *modules* rather than packages. Regrouping them made the boundary fall on package lines, which is the difference between a rule you can state and a rule you have to enumerate.

The lesson generalizes: when a runtime-layer package imports an interpreter-layer one, check whether the *type* is misplaced before designing an indirection. None of these needed a resolver slot or a protocol — only a `git mv` and an import rewrite. And when a package straddles the boundary, moving the odd module out is usually cheaper than teaching the guard about exceptions.

## The class-registry exception

`get_class_registry` is the one runtime-layer accessor that is *not* implemented in `runtime_hub`. Its implementation lives in `pipelex/system/registries/class_registry_access.py`, and `pipelex.runtime_hub.get_class_registry` delegates to it.

The reason is a genuine cycle. `core.concepts.concept` needs the active class registry, and it sits **inside** `runtime_hub`'s own import closure:

```
runtime_hub → cogt.llm.llm_worker_abstract → system.telemetry.otel_factory
            → core.pipes.pipe_output → core.stuffs.stuff → core.concepts.concept
```

so `concept.py` cannot import `runtime_hub` at module level. Hosting the accessor in a module that imports nothing from `pipelex` is what lets `core/concepts/` use a plain top-level import — replacing three identical `importlib.import_module("pipelex.hub")` shims that were invisible to every import lint and to pyright's module graph.

**Use `pipelex.runtime_hub.get_class_registry` everywhere.** Import the leaf module directly only from inside `runtime_hub`'s import closure, where the public accessor is unreachable.

### Library scoping crosses downward, at install time

A run may pin a per-library `ClassRegistry` rather than the process-global Kajson one. Knowing *which* library is current is method-layer knowledge, so the runtime layer holds only a slot: `class_registry_scoping`, defaulting to a resolver that returns `None`. `set_interpreter_hub` installs the real resolver, which means scoping is live exactly when a `InterpreterHub` exists — an invariant a caller cannot forget to wire. `Pipelex.teardown` calls `class_registry_scoping.reset()` so a torn-down library manager is never reachable through a still-pinned library id.

This is the same shape as `HubSlot.ISOLATED_EXECUTION_PROBE`: a defaulted callable a higher layer replaces at boot, never an unset attribute. A process that only ever builds a `RuntimeHub` (the doctor path, most unit tests) therefore degrades to the process-global registry instead of raising.

## Enforcement

The boundary is enforced mechanically. Two things are checked, because the rule and the property it buys can fail independently.

### The rule — `make check-hub-layering`

```bash
make check-hub-layering   # alias: make chl
```

An AST guard (`pipelex-dev check-hub-layering`, core in `pipelex/cli/dev_cli/commands/hub_layering_guard.py`) that runs in `make agent-check`, in the `make check` aggregate, and in CI. It checks two rules over `pipelex/` and `tests/`:

1. **The layer rule.** A module in the declared runtime layer — `pipelex.cogt`, `pipelex.plugins`, `pipelex.reporting`, `pipelex.system`, `pipelex.tools`, plus core's data-model packages `pipelex.core.concepts`, `pipelex.core.domains`, `pipelex.core.memory`, `pipelex.core.pipes.inputs`, `pipelex.core.pipes.stuff_spec` and `pipelex.core.stuffs` — may not import `pipelex.interpreter_hub`. Every declared package is compliant, so the guard hard-blocks on **any** violation with an empty exception list. Why `core/` is listed package by package rather than wholesale is [below](#where-core-splits).
2. **The dead-module rule.** *No* scanned module may reference `pipelex.hub`. It was deleted rather than aliased so a stale import fails loudly; this closes the one hole in that guarantee.

Both rules match **imports and bare string literals**, and the string half is the load-bearing one. A missed *import* of a deleted module is an immediate `ImportError`; a missed *string* is not, and it is invisible to every import-graph tool and to pyright's module graph. Both forms that actually occurred here were strings: three `importlib.import_module("pipelex.hub")` shims hiding a cycle from every lint, and one `mocker.patch("pipelex.hub.get_console", ...)` that broke a whole CLI test suite with an `AttributeError` raised nowhere near a hub. Matching is exact-or-boundary against the module path, so `pipelex.runtime_hub` never matches `pipelex.hub` and prose that merely *mentions* a module is not a reference.

The guard resolves relative imports (`from ...interpreter_hub import …`) against the importing module's own package, so the forbidden arrow cannot be spelled around. A path assembled at runtime from f-strings or concatenation is beyond any AST scan; nothing in the tree does that.

Two deliberate carve-outs:

- **`if TYPE_CHECKING:` blocks are exempt from the layer rule** — the rule is about what *loads*, and a type-only import loads nothing. Its `else` branch is not exempt, nor is `if not TYPE_CHECKING:`, and the dead-module rule applies inside `TYPE_CHECKING` too (a deleted module exists in no phase).
- An inline `# hub-layering: ignore` comment anywhere on the offending statement suppresses it, mirroring `# kw-only: ignore`. There is exactly one in the tree, on the guard's own declaration of the forbidden path.

`tests/` is scanned for the dead-module rule only. `tests.*` sits in no declared layer, so a test may freely patch `pipelex.interpreter_hub` — while a stale `pipelex.hub` patch target, the landmine above, still fails the check.

### The property — the import-closure test

`tests/unit/pipelex/test_runtime_layer_import_closure.py` imports each runtime-layer entry point in a **subprocess** and asserts that zero interpreter modules — and no `pipelex.interpreter_hub` — landed in `sys.modules`. This is the [measurement above](#why-the-boundary-exists), pinned. It exists separately from the lint because the two fail independently: a runtime-layer module reaching directly into `pipe_operators`, without touching a hub, breaks the property while the lint stays green.

Its predicate is stricter than the one-liner above: besides the five interpreter top-level packages it names core's Pipe-machinery modules one by one, because most of them only get caught *transitively* — through the `pipe_operators` / `libraries` they pull in — and `core.pipes.pipe_blueprint` pulls in none of it, so a runtime-layer import of it would otherwise pass. Naming them is what makes the predicate state the boundary rather than approximate it. What the predicate deliberately cannot name yet is `pipeline`, `pipe_run` and `core.bundles.exceptions`: interpreter-named homes whose leaf models already land in every runtime closure. That is a placement wart, not a broken arrow, and it is recorded in `wip/pr-1062-review-notes.md`.

Alongside them, `tests/unit/pipelex/test_hub_lifecycle.py` pins that a boot installs both singletons and that the reset really releases the scoping an `InterpreterHub` installed.

### This document — the `hub-layering-convention` drift contract

The guard and the closure test keep the *code* honest; neither can tell whether **this page** still describes it. That is a [drift contract](drift-contracts.md): `hub-layering-convention` names the guard and both hub modules as triggers and this document as the review target, so adding or moving a hub accessor — or changing the declared runtime layer — obliges a recorded review here before the change can land. It carries no verify command, because `check-hub-layering` already gates `make check` and CI.

Two checks make that review mechanical rather than a re-read, and are the ones to run:

- Extract every public module-level symbol from `runtime_hub` and `interpreter_hub` and confirm each appears in the partition tables above. An undocumented accessor is the failure mode this contract exists to catch.
- Import `RUNTIME_LAYER_PACKAGES` from the guard and confirm every declared package is named under [The rule](#the-rule--make-check-hub-layering).

## Known inversions

Named so this document stays honest. None of these import a hub, so a hub-import guard would not flag them — but they mean "`plugins` is a runtime layer" is not yet unconditionally true.

- `plugins/pipe_func/pipe_func_plugin.py` and `plugins/pipe_func_executor_registry.py` are typed by protocols from `pipe_operators/`; `plugins/direct/direct_plugin.py` imports from `pipeline/`. `pipe_func_executor_registry` defers its import under `TYPE_CHECKING` precisely because `pipelex.config` imports it and the inference layer imports `pipelex.config` — a module-level import there would drag the interpreter back into every inference closure. The placement itself is unfixed.
- `core/`'s Pipe-touching half — `pipe_abstract`, `pipe_blueprint`, `pipe_factory`, `pipes/rendering/`, `bundles/`, `interpreter/`, `registry_models` — imports the interpreter directly. That is not an inversion to fix but a fact about what a pipe is (see [Where core splits](#where-core-splits)); it is listed here only so nobody re-reads the runtime-layer declaration as an oversight. Three of those modules import `interpreter_hub` on purpose, to inject downward.
- Broader measured inversions, out of scope for the hub boundary: `cogt → core`, `system → cogt`, `plugins → runtime_bridge`, and `cogt/model_backends/model_lists.py` importing `pipelex.cli.exceptions.PipelexCLIError`. What remains of `tools → cogt` is `tools/pdf/pypdfium2_renderer.py` reaching for `cogt.extract` and `cogt.image` types; the templating half of that cluster is gone (see [Placement, not coupling](#placement-not-coupling)).

## For consumers outside this repo

`pipelex.hub` is gone; there is no shim. Every external importer must choose a layer. The symbols that crossed the repo boundary are split as follows — runtime-layer ones now come from `pipelex.runtime_hub`, interpreter-layer ones from `pipelex.interpreter_hub`, per the tables above. `get_pipelex_hub` splits into `get_runtime_hub` and `get_interpreter_hub`, so each call site must pick the container it actually meant.
