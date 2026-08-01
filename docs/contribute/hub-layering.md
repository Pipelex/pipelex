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

`runtime_hub` must not name anything from `libraries`, `pipe_operators`, `pipe_controllers`, `codegen`, `builder`, `interpreter_plugins`, `pipe_machinery`, `pipe_signature`, `mthds_parsing`, `pipeline` or `pipe_run` at module level. That list is now stated in whole top-level packages, which is the point of the modularity moves: it used to have to trail "…or the Pipe-touching modules of `core.pipes`", because some of what it forbids lived under a runtime-named package. Those module-level imports exist only to type the getters, but they are what made a single hub drag the entire method interpreter into every consumer that just wanted `get_console()`.

The property that matters is measurable: **importing the Pipelex runtime loads zero modules from any of the packages named above.** That is both the assertion the closure test pins and the outward-facing claim — the inference engine does not know the MTHDS language exists, so you can embed it without loading a line of the parser, the pipe machinery, or a single pipe kind. Verify it from the repo root on a synced venv:

```bash
.venv/bin/python - <<'PY'
import sys
from pathlib import Path

import pipelex.cogt.content_generation.content_generator  # noqa: F401

INTERPRETER = {"libraries", "pipe_operators", "pipe_controllers", "codegen", "builder", "interpreter_plugins", "pipe_machinery", "pipe_signature", "mthds_parsing", "pipeline", "pipe_run"}
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

`pipelex/core/` used to be two layers under one name, and the runtime-layer declaration had to work around it. It does not any more — `pipelex.core` is a single declared entry — but the split is worth recording, because *how* it was resolved is the general lesson.

For a long time `core/` held two different kinds of thing:

- **The data model — runtime.** `core.concepts`, `core.domains`, `core.stuffs`, `core.memory`, the input/output *specs* under `core.pipes.inputs` and `core.pipes.stuff_spec`, and `core.pipes.pipe_output`. These describe what a method's values *are*. Nothing in them needs a loaded method, and each measures **zero** modules from the packages the predicate names. `pipe_output` reads as Pipe machinery but is not: it names no `Pipe` — it holds the working memory, graph spec and usage a run *produced* — and it sits inside `runtime_hub`'s own closure (the chain under [The class-registry exception](#the-class-registry-exception) passes straight through it).
- **The Pipe machinery — interpreter.** `pipe_abstract`, `pipe_blueprint`, `pipe_factory`, `validation`, `template_guard_lint` and the two renderers. Every one of them names a `Pipe`, and a pipe is the interpreter's own object — they import `pipe_operators` / `pipe_controllers` / `libraries` **directly**, not through a hub. No amount of dependency injection makes those runtime.

**The resolution was to move the second kind out, not to describe it more precisely.** All of it now lives in two top-level packages of its own: `pipelex.pipe_machinery` holds the Pipe machinery proper plus the pipe-kind registration manifest (`registry_models.PipeRegistryModels` — the fattest edge of the lot, a list of every pipe class and every pipe factory, so importing it loaded the whole interpreter), and `pipelex.mthds_parsing` holds the MTHDS parser and the bundle blueprint it produces, whose `pipelex_bundle_blueprint` is a discriminated union over every pipe blueprint. See [Registration surface](registration-surface.md) for what adding a pipe kind touches.

One model stayed behind on purpose, and it is the interesting case. `PipelexBundleBlueprintValidationErrorData` is raised by the parser but imported by `pipeline/` and `libraries/`, which carry it into every runtime-layer import closure. Filing it with the parser would have made the boundary unenforceable for `mthds_parsing` — the closure predicate would have needed a permanent exclusion for it. It lives in `core.exceptions` instead, beside the two sibling structured error-data models it shares `PipeValidationErrorType` with. **Moving the leaf is what buys the clean predicate**; excluding it would only have recorded the problem.

So the declaration names `pipelex.core` wholesale, which is a claim the measurement now supports: every `pipelex.core.*` module loads zero modules from the interpreter packages the predicate names, and none reaches `interpreter_hub`. It once listed core's data-model packages one by one, and that enumeration was the shape of the problem — a package-granular declaration is only honest when the packages match the layers.

The dividing line is worth stating as a rule of thumb: **if it names a `Pipe`, it belongs to the interpreter layer.**

### Injected providers, not ambient lookups

The data-model half used to reach for `get_concept_library()` / `get_native_concept()` / `get_required_concept()` — ambient lookups into a loaded method, which is exactly what made `core/` inseparable from the interpreter. It now takes what it needs as a parameter, through one read-side contract: `ConceptProviderAbstract` (`pipelex/core/concepts/concept_provider_abstract.py`) — resolve a ref, a code, or a native code into a `Concept`, answer compatibility questions about two of them, and resolve a concept's declared `structure_class_name` into the class itself.

**Class resolution is part of that contract, and it took a second pass to get there.** The hub split moved *concept* resolution onto the provider but left *class* resolution ambient one level down, inside `Concept` itself: the model reached `get_class_registry()` to answer "what is my structure class?" and to run the structural half of a compatibility check. A `Concept` is a subclass of the MTHDS-protocol wire model `ConceptAbstract` — pure serializable data — so that coupled a standard-owned wire model to a Pipelex process-global. `ConceptProviderAbstract.get_structure_class` decouples them: a `Concept` carries the class *name* as a plain protocol string, and turning a name into a type is the provider's business, never the model's.

Be precise about what that buys, because it is easy to overstate. The read is still **ambient** — `ConceptLibrary.get_structure_class` calls `get_class_registry()`, which selects a registry from the current async context rather than from the provider instance (a `ConceptLibrary` holds none; the per-library `ClassRegistry` lives on `Library`). What changed is that the whole tree now has *one* implementation of that read, behind one seam, instead of it happening inside a wire model. Scoping it to the provider's own library is consequently a one-place change — see `wip/inputs/provider-scoped-class-resolution.md` for why nothing needs it yet.

Two shapes fall out of that, and they are the ones to copy:

- **Compatibility is two tiers, composed by the thing that owns resolution.** `Concept.are_compatible_by_declaration` is pure over the model's fields (plus an injected `concept_resolver`): dynamic short-circuits, ref equality, declared-class-name equality, `refines` chains. `ConceptLibrary.is_compatible` asks that first and only resolves classes when it is inconclusive. A name that should have resolved and didn't now raises `ConceptStructureClassNotFoundError` instead of answering `False` — "unknown" and "incompatible" are different answers, and conflating them was a latent wrong-verdict bug.
- **Rendering takes the resolved class, not the name.** `Concept.render_concept_representation` receives a `structure_class`; `StuffSpec.render_stuff_spec` takes the `concept_provider`, resolves once, and passes the class down. Interpreter-layer callers (`output_renderer`, `input_renderer`, `pipe_io_contracts`, `builder/runner_code`) supply `get_concept_library()`.

The **write side** stays ambient on purpose: `concept_factory` and `structure_generation/generator.py` generate structure classes and register them at library-load time, which is genuinely the registry's business. That those two are the only modules under `pipelex/core/concepts/` touching the registry is pinned as a golden set by `tests/unit/pipelex/core/concepts/test_concept_registry_boundary.py` — nothing else can see it, since both the accessor and its users are runtime-layer.

It is **read-side only**. Managing a library — adding, removing, listing, setup/teardown — stays in the interpreter layer: `ConceptLibraryAbstract` *extends* it, keeping its management half in `libraries/`. Splitting read from write is what lets a core module state its dependency honestly ("I need something that can resolve concepts") without inheriting a library lifecycle it has no business touching.

**There is deliberately no pipe counterpart.** Nothing in core's runtime half resolves a pipe. The two places that follow a pipe reference found *inside* a pipe graph — a condition's mapped pipes, a sequence's last step — live in `pipe_machinery/rendering/`, which is interpreter-layer and calls `interpreter_hub.get_required_pipe` directly; a provider parameter there would buy no closure property. `get_required_pipe` therefore stays on `PipeLibraryAbstract`. Split a read half out when a runtime-layer caller actually needs one, not for symmetry with concepts.

The injection point is the interpreter layer. `pipe_factory`, `input_renderer` and `output_renderer` — already interpreter-bound, so nothing is lost — resolve the concept library themselves and pass it down; `pipeline/execution_seams.py` does the same for `WorkingMemoryFactory`. That is the one-way arrow the whole design rests on, applied inside `core/`: **the half that knows about a loaded method resolves the collaborator and hands it downward.**

When you add a core data-model function that needs a concept — or a concept's structure class — add a `concept_provider` parameter. Do not add a hub import, and do not reach for `get_class_registry()`: the guard will reject the first, and the second is the coupling this section exists to describe.

One module outside `core/` cannot import either hub at module level, and the constraint is a **static-analysis** cycle rather than a runtime one — worth knowing before you restate it. `pipe_machinery/pipe_abstract.py` reads `class_registry_access` directly to decorate graph-registry entries with a JSON Schema. It is *not* in `runtime_hub`'s runtime closure (`plugins.orchestrator_registry` and `pipe_run.pipe_job` reach it through `TYPE_CHECKING`-only edges, and a clean-interpreter probe shows all three absent) — but pyright's `reportImportCycles` counts those edges, so either hub import is a hard type-check failure, reported at `interpreter_hub.py` where no line-level ignore can reach it. Deferring the import does not dodge it. The below-both-hubs accessor is what that case is for; its docstring records the measurement.

## Where the built-in plugins split

Two different splits run through the built-in plugins, and they are easy to conflate. The first is **mechanism vs adapters**, and it does *not* cross a layer boundary: `pipelex/plugins/` is the plugin mechanism — the `PipelexPlugin` contract, the `PluginRegistrar`, and the capability registries the registrar accumulates into — while `pipelex/providers/` holds the built-in adapters that register through it, one directory per provider. Both packages are declared runtime-layer. What the split makes visible is the one-way dependency between them: adapters depend on the mechanism, and the mechanism knows nothing of its adapters. It also stops `pipelex/plugins/` from reading as "the vendors", which is what made the second split hard to see. Note the scope of that claim — it is about these two packages, not about the whole tree: `cogt` does name four providers directly, which [Known inversions](#known-inversions) records and justifies.

Most of those directories are vendor adapters, but not all of them, which is why the package is `providers/` and not `vendors/`: `providers/secrets/` registers the built-in `env` backend, which has no vendor at all, and `providers/storage/` registers local, in-memory, S3 and GCP behind one directory. In both cases only the registration shim lives here — the implementations are under `pipelex/tools/`.

The second split *is* the layer boundary, and the same rule of thumb divides it. Most built-ins adapt a runtime-layer port — an inference backend, a model lister, a storage or secrets provider — and those are the packages under `pipelex/providers/`. Two adapt interpreter-layer ports, because their job is to *construct* interpreter-layer objects: `DirectOrchestratorPlugin` registers a `DirectOrchestrator` and a `DirectBundleValidator`, and `PipeFuncPlugin` registers a concrete `DirectPipeFuncExecutor`. Those two live in **`pipelex/interpreter_plugins/`**.

External plugins are unaffected by the mechanism/adapter split: they import `pipelex.plugins.contract` and `pipelex.plugins.registrar`, both of which stayed put, and they are discovered through the `pipelex.plugins` entry-point group — a group identifier, not a module path, and unchanged.

The registrar's slots are *ports* and they stay runtime-layer — `OrchestratorProtocol`, `BundleValidatorProtocol` and `PipeFuncExecutorFactoryFn` all live under `plugins/*_registry.py`. Only the *adapters* are interpreter-layer. That is ordinary ports-and-adapters, and it is what the layer rule's own remedy text prescribes: have the interpreter layer install it downward at boot. Where each derived registry is *installed* still follows the hub partition rather than the port's home: `RuntimeBoot.setup` puts the orchestrator, bundle-validator, backend, lister, storage and secrets registries on the `RuntimeHub`, and `Pipelex.setup` puts the `PipeFuncExecutorRegistry` on the `InterpreterHub` — the one placement flagged [above](#which-hub-does-a-new-symbol-belong-to). Since [the boot split](#where-the-boot-splits) the two installs sit in the two halves that match their hubs, so the partition is now visible in the code rather than only in this sentence.

Composition happens where welding is legal. `pipelex/providers/builtins.py` exports `RUNTIME_BUILTIN_PLUGINS`; `pipelex/interpreter_plugins/builtins.py` imports that half — downward, which the interpreter layer may do — and exports the composed `BUILTIN_PLUGINS` and `CORE_UNCONDITIONAL_PLUGIN_NAMES`. Both are **parameters** of `build_registrar`, never module globals it imports, so `plugins/discovery.py` stays runtime-layer: `pipelex.py` (the interpreter boot) and the `pipelex plugins list` diagnostic pass the composed lists in, while `runtime_boot.py` defaults to the runtime half alone. Exactly one place still answers "what are the built-in plugins" — it just lives in the layer permitted to say it.

This is the seam external plugins already use. Our Temporal plugin contributes an orchestrator and our Daytona plugin a PipeFunc executor; both are interpreter-touching, both live outside this repo, and both arrive through the `pipelex.plugins` entry point without welding anything. The in-tree built-ins used to be the only ones that welded — [Known inversions](#known-inversions) records what that cost.

One consequence is worth stating as a contract, and it is written into `PipelexPlugin`'s docstring: **a plugin belongs to exactly one layer.** A capability needing adapters in both is two plugins. Nothing enforces it mechanically; a straddling plugin would simply put the interpreter back into every runtime closure, and the guard's transitive rule would say so.

## Where the boot splits

The composition root is split the same way, and it is the same move: a runtime half in a declared runtime-layer home, and an interpreter half that imports it downward and adds what only a method-running process needs.

`pipelex/runtime_boot.py` holds `RuntimeBoot`. It stands up config, logging, the secrets provider, telemetry, the Kajson class registry with `CoreRegistryModels`, the template sets, the SDK client manager, the model deck, the plugin-derived runtime registries, storage, the content generator, the inference manager, the reporting delegate and the observers — and it loads **zero interpreter modules** doing it. `pipelex/pipelex.py` holds `Pipelex`, which subclasses it and appends the `InterpreterHub`, the composed plugin manifests, the `PipeFuncExecutorRegistry` and its executor, the `LibraryManager` and default library dirs, the `PipelineManager`, the `PipeRegistryModels` registration, the `PipeRouter` and the `PipeRun`.

Two top-level modules, not a `boot/` package: they mirror `runtime_hub.py` / `interpreter_hub.py`, which is the tree's strongest naming precedent for a layered pair. `Pipelex` does not move and is not renamed — it is the public entry point every consumer and sibling repo imports, and the layer boundary never required moving it.

**This is what finally gives `RUNTIME_BUILTIN_PLUGINS` a caller.** The plugin split created that constant with no importer in the tree; `RuntimeBoot.setup` defaults to it, so a runtime-only boot discovers exactly the runtime half and the two interpreter-touching built-ins are simply absent. The consequence is worth stating plainly, because it is the reason nothing needed redesigning to make this work: `OrchestratorRegistry`, `BundleValidatorRegistry` and the PipeFunc executor modes are all interpreter-contributed, and therefore **empty on a runtime-only boot** — which is harmless only because nothing in the runtime half *resolves* out of them at boot. They are constructed, set on the hub, and looked up at run time by the interpreter. The two registries the runtime half does resolve out of, secrets and storage, are runtime-contributed and core-unconditional.

Inheritance rather than composition, deliberately: it preserves every attribute address (`self.models_manager`, `self.class_registry`, `self.telemetry_manager` and the rest read the same from both halves, so no consumer inside or outside this repo changes), and it reads as what it is — the interpreter boot *is* the runtime boot plus the interpreter constructions. Two consequences are load-bearing:

- **The singleton resolves by subclass.** `RuntimeBoot` carries `MetaSingleton` too, and the class-level accessors go through `MetaSingleton.get_subclass_instance`, so `RuntimeBoot.is_fully_booted()` answers `True` while a `Pipelex` owns the process globals. Each `make()` asks the *base* class whether a boot exists, which is what makes the two mutually exclusive in both directions — `set_runtime_hub`, `KajsonManager` and `log.configure` are all once-per-process, so booting one on top of the other would serve a half-populated class registry.
- **Teardown ordering is explicit, not a template hook.** The plugin-contributed teardown callbacks must run *before* `pipeline_manager.teardown()`, so a worker's in-flight resources release first. `RuntimeBoot` exposes `_teardown_plugin_callbacks()` and `_teardown_runtime()` as separate phases and `Pipelex.teardown` sequences them with its own step in between, because that order is the whole reason the split exists in this shape.

Enforcement mirrors the packages': `pipelex.runtime_boot` is declared in `RUNTIME_LAYER_PACKAGES` (a *module* entry, beside `pipelex.runtime_hub`) and listed in the closure test's `RUNTIME_LAYER_ENTRY_POINTS`. `pipelex.pipelex` is deliberately **undeclared** — it is interpreter-side by construction, like `pipelex.cli`, so declaring it would fail the rule by design rather than enforce anything. `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py` asserts both directions, because "surely the boot should be runtime-layer" is a plausible future edit.

## Placement, not coupling

Splitting the hub removes the *lookups* that crossed the boundary. It does not move a type that was simply filed in the wrong package — and a misfiled type drags its whole package into every closure that names it. Two were resolved this way; both are worth knowing as the pattern to apply to the next one.

**`JobMetadata` moved to `pipelex/system/`.** It is an argument to essentially every `cogt` call, yet it lived in `pipelex/pipeline/` — which made `cogt → pipeline` the fattest remaining edge and pulled `graph.trace_context` into every closure that touched inference. `JobMetadata`, `JobCategory` and `UnitJobId` now live in `pipelex/system/job_metadata.py`, and `JobMetadataError` moved from `pipeline/exceptions.py` to `pipelex/system/exceptions.py`. `cogt → pipeline` is now **zero statements**.

`TraceContext` moved with it, to `pipelex/system/trace_context.py`: it is the transport `JobMetadata` carries, so leaving it in `graph/` would only have renamed the inversion to `system → graph`. Its one dependency on the graph package — `DataInclusionConfig`, nested under `[...graph_config.data_inclusion]` in the TOML — moved down to `pipelex/system/data_inclusion_config.py`, which `graph_config.py` now imports. The TOML shape is unchanged; only the class's home moved, which is what keeps `trace_context` from re-importing `mermaid_config` and `reactflow_config` through `GraphConfig`.

**The templating primitives moved down into `tools/`.** `TemplateCategory`, `TemplatingStyle`, `TagStyle` and `TextFormat` sat under `cogt/templating/` while eight `tools/jinja2/` and `tools/mermaid/` modules imported them — so `tools`, the intended bottom layer, depended on `cogt`. None of the three modules holding them named anything from `cogt`, so this was pure misfiling:

- `TextFormat` and `TemplatingStyle` / `TagStyle` → `pipelex/tools/templating/`, which imports nothing from `pipelex` beyond its own sibling. It is a leaf.
- `TemplateCategory` → `pipelex/tools/jinja2/`, because its entire payload is a map of jinja2 filters. Filing it in `tools/templating/` would have made that package import `tools/jinja2` while `tools/jinja2` imports it back — a cycle inside one layer. As placed, the edges run one way: `tools/mermaid → tools/jinja2 → tools/templating`.

What stays in `cogt/templating/` — `TemplateBlueprint`, the sigil preprocessor, the rendering entrypoint — belongs there: a blueprint is language-layer, and the rest imports `tools/jinja2` downward.

**`resolved_fields` moved down into `core/concepts/`.** The neutral resolved-field layer — one structure field becoming a `ResolvedType` tree — lived under `pipelex/codegen/` while `core/concepts/structure_generation/generator.py` imported it, which put `pipelex.codegen` into the closure of every core module that reached structure generation. It names nothing outside `pipelex.core`, so this was misfiling again: it now lives at `pipelex/core/concepts/resolved_fields.py`, and the codegen emitters import it upward.

**The two renderers regrouped, then left `core/` altogether — they are now `pipe_machinery/rendering/`.** `input_renderer` sat in `core/pipes/inputs/` beside genuinely runtime-layer modules while `output_renderer` sat alone in `core/pipes/output/`. Both render a `PipeAbstract` for a human or an agent, so both belong to the interpreter layer, and leaving `input_renderer` where it was would have forced the runtime-layer declaration to be a list of *modules* rather than packages. Regrouping them into one `rendering/` package was the first half of the fix and bought a real improvement — the boundary fell on package lines instead of module lines. It was only half, though: the declaration still had to name six `pipelex.core.*` sub-packages, because the boundary now fell on package lines *inside* `core/`. Moving the whole group out to `pipe_machinery/` is what collapsed those six entries to one. The general form: regrouping tells you where the boundary is, moving is what makes the boundary a package name.

The lesson generalizes: when a runtime-layer package imports an interpreter-layer one, check whether the *type* is misplaced before designing an indirection. None of these needed a resolver slot or a protocol — only a `git mv` and an import rewrite. And when a package straddles the boundary, moving the odd module out is usually cheaper than teaching the guard about exceptions — which is exactly how the built-in plugins were split, [below](#where-the-built-in-plugins-split).

## The class-registry exception

`get_class_registry` is the one runtime-layer accessor that is *not* implemented in `runtime_hub`. Its implementation lives in `pipelex/system/registries/class_registry_access.py`, and `pipelex.runtime_hub.get_class_registry` delegates to it.

The reason is a genuine cycle. `core.concepts.concept` needs the active class registry, and it sits **inside** `runtime_hub`'s own import closure:

```
runtime_hub → cogt.llm.llm_worker_abstract → system.telemetry.otel_factory
            → core.pipes.pipe_output → core.stuffs.stuff → core.concepts.concept
```

so `concept.py` cannot import `runtime_hub` at module level. Hosting the accessor in a module that imports nothing from `pipelex` is what lets `core/concepts/` use a plain top-level import — replacing three identical `importlib.import_module("pipelex.hub")` shims that were invisible to every import lint and to pyright's module graph.

**Use `pipelex.runtime_hub.get_class_registry` everywhere.** The exception is a module that must stay import-light *with respect to* `runtime_hub` — that one imports the leaf directly. `core/concepts/` is the case, for two different reasons: `concept.py` sits **inside** `runtime_hub`'s own closure, so the public accessor is literally unreachable there; `concept_factory.py` and `structure_generation/generator.py` sit outside it, and routing them through `runtime_hub` would re-couple `core.concepts` — a declared runtime-layer package — to the whole cogt/plugin stack for one function. Do not "fix" those two to the public accessor: nothing checks this mechanically, and the closure test would not catch it either, since it measures interpreter modules rather than weight.

### Library scoping crosses downward, at install time

A run may pin a per-library `ClassRegistry` rather than the process-global Kajson one. Knowing *which* library is current is method-layer knowledge, so the runtime layer holds only a slot: `class_registry_scoping`, defaulting to a resolver that returns `None`. `set_interpreter_hub` installs the real resolver, which means scoping is live exactly when a `InterpreterHub` exists — an invariant a caller cannot forget to wire. The runtime teardown phase (`RuntimeBoot._teardown_runtime`, reached from every `teardown`) calls `class_registry_scoping.reset()` so a torn-down library manager is never reachable through a still-pinned library id. It lives on the runtime half because releasing the slot belongs to whichever teardown runs — on a runtime-only boot nothing installed a resolver and the reset is a no-op.

This is the same shape as `HubSlot.ISOLATED_EXECUTION_PROBE`: a defaulted callable a higher layer replaces at boot, never an unset attribute. A process that only ever builds a `RuntimeHub` therefore degrades to the process-global registry instead of raising. That used to describe only the doctor path and most unit tests; since [the boot split](#where-the-boot-splits) it is a first-class entry point — `RuntimeBoot.make()` installs no `InterpreterHub`, and a test pins that scoping stays at its unscoped default on that boot.

## Enforcement

The boundary is enforced mechanically. Two things are checked, because the rule and the property it buys can fail independently.

### The rule — `make check-hub-layering`

```bash
make check-hub-layering   # alias: make chl
```

An AST guard (`pipelex-dev check-hub-layering`, core in `pipelex/cli/dev_cli/commands/hub_layering_guard.py`) that runs in `make agent-check`, in the `make check` aggregate, and in CI. It checks three rules over `pipelex/` and `tests/`:

1. **The layer rule.** A module in the declared runtime layer — `pipelex.cogt`, `pipelex.core`, `pipelex.errors`, `pipelex.graph`, `pipelex.kernel`, `pipelex.observer`, `pipelex.plugins`, `pipelex.providers`, `pipelex.reporting`, `pipelex.system`, `pipelex.test_extras`, `pipelex.tools`, `pipelex.tracing`, plus the `pipelex.runtime_hub` and `pipelex.runtime_boot` modules themselves — may not import `pipelex.interpreter_hub`. The declaration is compliant with an empty exception list, so the guard hard-blocks on **any** violation. Entries are matched exact-or-dotted-prefix, which is why a bare *module* is a legal entry beside the packages: without `pipelex.runtime_hub` spelled out, the module at the centre of the rule would be exempt from it, and without `pipelex.runtime_boot` the runtime layer's own composition root would be — see [Where the boot splits](#where-the-boot-splits). `pipelex.core` was six entries until its interpreter tenants moved out — see [Where core splits](#where-core-splits) for what that enumeration was working around.

    `graph`, `tracing`, `observer` and `errors` joined the list late, and the delay cost something — see [Known inversions](#known-inversions). They are the run-graph data model with its tracer and renderers, the trace-event assembler feeding it, the run-observation hooks, and the error taxonomy: machinery present at execution time whatever is loaded, which is the runtime layer's own definition. `pipelex.test_extras` is on the list for the same reason: it ships, `runtime_boot.py` imports it at boot, and it measures clean. `pipelex.kernel` is the same rule applied *ahead* of a breach instead of behind one: it was declared in the commit that created the package, because it holds the operator-execution semantics the interpreter's operator classes call into, and a single `interpreter_hub` reach anywhere in it would put the interpreter back into every programmatic caller — the property the package exists to provide. `pipelex.kit` is data files with no module to police; `pipelex.language`, `pipelex.runtime_bridge` and `pipelex.cli` all measure dirty and are interpreter-side by construction. That is every top-level package accounted for — which is the point, because the rule of thumb is that a measured-clean package should be *declared*, not left undeclared: **an undeclared package is not neutral, it is unpoliced.**
2. **The dead-module rule.** *No* scanned module may reference `pipelex.hub`. It was deleted rather than aliased so a stale import fails loudly; this closes the one hole in that guarantee.
3. **The transitive rule.** No runtime-layer module may *reach* `pipelex.interpreter_hub` either, through any chain of module-level imports. Rules 1 and 2 are per-file and see one hop; this one resolves the whole module-level import graph of `pipelex/` and does reachability over it, reporting the shortest chain and the line of its first hop. It exists because the one-hop rules missed a live breach for a whole release: four modules of the declared runtime-layer `pipelex.plugins` package reached the interpreter hub through `runtime_bridge`, `pipeline` and `pipe_operators`, and both gates stayed green (see [Known inversions](#known-inversions)). A *direct* import is left to rule 1, which names the more specific remedy, rather than reported twice.

    The rule scopes itself to what an import actually loads: module-level imports only, `TYPE_CHECKING` blocks, function bodies and `# hub-layering: ignore`d statements excluded — the same carve-outs rule 1 grants, applied to the graph. It also models what an import loads *on the way*: reaching `pkg.sub.mod` executes `pkg/__init__.py` and `pkg/sub/__init__.py` first, so those are edges too and a breach in a package init is reached by every importer of anything beneath it. And a module-level **string** naming the interpreter hub is an edge, since a dynamic import loads it just the same — rule 1 catches that string in a runtime-layer module, but an *intermediary* sits in no declared layer, so without this the graph would miss it. A finding cannot be silenced **where it is reported** — the marker suppresses one reviewed *import*, never a module's transitive reach, so a module the declaration claims is runtime-layer while the graph says otherwise gets moved or has its dependency inverted.

    The rule also refuses to pass vacuously: if the scan finds no `pipelex.interpreter_hub` among the modules it parsed — a renamed hub, or a scan root the module names cannot be derived from — it raises instead of reporting zero. Reverse reachability from a module the graph does not contain is empty by construction, so without that check a rename would silently turn the whole rule off while the gate stayed green.

All three rules match **imports and bare string literals**, and the string half is the load-bearing one. A missed *import* of a deleted module is an immediate `ImportError`; a missed *string* is not, and it is invisible to every import-graph tool and to pyright's module graph. Both forms that actually occurred here were strings: three `importlib.import_module("pipelex.hub")` shims hiding a cycle from every lint, and one `mocker.patch("pipelex.hub.get_console", ...)` that broke a whole CLI test suite with an `AttributeError` raised nowhere near a hub. Matching is exact-or-boundary against the module path, so `pipelex.runtime_hub` never matches `pipelex.hub` and prose that merely *mentions* a module is not a reference.

The guard resolves relative imports (`from ...interpreter_hub import …`) against the importing module's own package, so the forbidden arrow cannot be spelled around. A path assembled at runtime from f-strings or concatenation is beyond any AST scan; nothing in the tree does that.

Two deliberate carve-outs:

- **`if TYPE_CHECKING:` blocks are exempt from the layer rule** — the rule is about what *loads*, and a type-only import loads nothing. Only `TYPE_CHECKING` and `typing.TYPE_CHECKING` open such a block: an attribute of any other receiver (`settings.TYPE_CHECKING:`) is an ordinary runtime condition and earns no exemption. The `else` branch is not exempt either, nor is `if not TYPE_CHECKING:`, and the dead-module rule applies inside `TYPE_CHECKING` too (a deleted module exists in no phase).
- An inline `# hub-layering: ignore` comment anywhere on the offending statement suppresses it, mirroring `# kw-only: ignore`. It applies to every rule that is about what *loads*, so a suppressed import is also not an edge in rule 3's graph. The only two in the tree are on the guard's own declarations of the two hub paths, which name them rather than importing them.

`tests/` is scanned for the dead-module rule only. `tests.*` sits in no declared layer, so a test may freely patch `pipelex.interpreter_hub` — while a stale `pipelex.hub` patch target, the landmine above, still fails the check. The transitive rule likewise walks `pipelex/` only: a test module has no closure to protect.

### The property — the import-closure test

`tests/unit/pipelex/test_runtime_layer_import_closure.py` imports each runtime-layer entry point in a **subprocess** and asserts that no module from its `INTERPRETER_PACKAGES` set — and no `pipelex.interpreter_hub` — landed in `sys.modules`. This is the [measurement above](#why-the-boundary-exists), pinned. It exists separately from the lint because the two fail independently: a runtime-layer module reaching directly into `pipe_operators`, without touching a hub, breaks the property while the lint stays green.

The entry points are the inference layer, `runtime_hub` itself, `providers.builtins`, and the heaviest module of each runtime-layer `core/` package. `providers.builtins` earns its place by history, under its former name `plugins.builtins`: it instantiates every built-in vendor adapter, and `pipelex.plugins` — then the largest declared runtime-layer package, vendors and mechanism together — had no entry point here when the transitive breach happened. The guard now follows the import graph, but that is *static* analysis and cannot see a dynamic import, so the package that bit us gets a runtime-truth check too. One entry point still covers both halves of what has since become two packages: importing the manifest pulls in every built-in adapter, and they reach the mechanism they register through.

Its predicate is now a single membership test over whole top-level packages — no per-module list and no exclusions. It used to need both: core's Pipe-machinery modules had to be named one by one (most were caught only *transitively*, through the `pipe_operators` / `libraries` they pull in, and `pipe_blueprint` pulled in none of it, so a runtime-layer import of it would have passed a package-only predicate), and `core.bundles.exceptions` had to be excluded by exact match because its validation-error data landed in every runtime closure. Both disappeared when the modules moved: the machinery to `pipe_machinery`, the parser to `mthds_parsing`, and the one leaf model to `core.exceptions`. **A package-granular predicate is honest only once the packages match the layers** — that is the whole argument for the moves, stated as a check.

The predicate now names **every** interpreter package. `pipeline` and `pipe_run` were the last two absent, and the reason was placement, not a broken arrow: four leaf models of theirs landed in every runtime closure, so naming them would have failed every entry point over an address. The remedy was the one `mthds_parsing` used — move the leaves first, then widen the predicate — and where each leaf went is decided by what it *is*, not by which package used to hold it:

| leaf | was | is now | why there |
| --- | --- | --- | --- |
| `SpecialPipelineId` | `pipeline.pipeline_models` | `system.job_metadata` | it is the vocabulary of `pipeline_run_id`, and that is `JobMetadata`'s field |
| `PipeRunMode` | `pipe_run.pipe_run_mode` | `system.pipe_run_mode` | a run-scope directive, not one of a method's values |
| `PipeRunParamKey` | inside `pipe_run.pipe_run_params` | `system.pipe_run_param_key` | same, and `core.concepts` needs it as its reserved-names list |
| `PipeRunError` | `pipe_run.exceptions` | `core.pipes.exceptions` | the runtime layer *subclasses* it — `PipeRunInputsError` and `OptionalValueAbsentError` derive from it in `core.pipes.inputs` |

Note the last row does not follow the first three into `system/`. Consistency of destination is not the criterion — what the symbol *is* decides. Three are run-scope directives and enums; the fourth is the base of a pipe-error family whose other members already live in `core/pipes/`, and filing it with them also lands it in the same error-reference section as the two subclasses that derive from it.

The detector runs in a subprocess, so its logic lives in a `textwrap.dedent` string that no linter or type checker sees — and a predicate that has quietly stopped detecting would make every entry point pass *vacuously*. Three guards close that, each covering what the others cannot:

- **A negative control.** `pipelex.interpreter_hub` is dirty by definition, and the test asserts it comes back *reported as offending modules*, not merely non-zero — so a broken predicate fails rather than going quietly green. It proves the detector detects, but only that *some* name matches.
- **Every configured name is a real package directory** under `pipelex/`. A typo'd or retired name matches nothing, and because the predicate is a membership test that is invisible rather than loud. (The package set is a module-level constant handed to the subprocess as argv, so the names are at least lint-visible; nothing checks a string against disk.)
- **The set matches the `INTERPRETER` set** in this page's [verification snippet](#why-the-boundary-exists) — a reader who runs a stale copy measures zero and believes it. The two had silently disagreed before anyone compared them by machine.

Each subprocess is time-bounded, because an unbounded one turns a deadlock into a hung suite instead of a failure.

Alongside them, `tests/unit/pipelex/test_hub_lifecycle.py` pins that a boot installs both singletons, and that the production `Pipelex.teardown` — not a stand-in calling `class_registry_scoping.reset()` directly — really releases the scoping an `InterpreterHub` installed, and that the next boot re-installs it. `tests/unit/pipelex/test_runtime_boot_closure.py` pins the boot-time half of the property: it *runs* `RuntimeBoot.make()` in a subprocess and asserts zero interpreter modules loaded, no `InterpreterHub` installed, and scoping left unscoped. A subprocess is required rather than preferred — both hubs are sticky class-attribute singletons that teardown never clears, so an in-process check would answer with a stale hub and pass vacuously. Booting rather than importing is what catches a boot step resolving out of an interpreter-contributed registry that is empty on that boot.

### This document — the `hub-layering-convention` drift contract

The guard and the closure test keep the *code* honest; neither can tell whether **this page** still describes it. That is a [drift contract](drift-contracts.md): `hub-layering-convention` names the guard and both hub modules as triggers and this document as the review target, so adding or moving a hub accessor — or changing the declared runtime layer — obliges a recorded review here before the change can land. It carries no verify command, because `check-hub-layering` already gates `make check` and CI.

Two checks make that review mechanical rather than a re-read, and are the ones to run:

- Extract every public module-level symbol from `runtime_hub` and `interpreter_hub` and confirm each appears in the partition tables above. An undocumented accessor is the failure mode this contract exists to catch.
- Import `RUNTIME_LAYER_PACKAGES` from the guard and confirm every declared package is named under [The rule](#the-rule-make-check-hub-layering).

## Known inversions

Named so this document stays honest.

**The one that was fixed, kept as the worked example.** Four modules of the declared runtime-layer `pipelex.plugins` package used to reach `interpreter_hub` — `direct/direct_plugin.py` and `pipe_func/pipe_func_plugin.py` as the leaves (their job is to *construct* interpreter-layer objects), `builtins.py` and `discovery.py` purely as aggregators over them. (That `builtins.py` is today `pipelex/providers/builtins.py`; it moved with the vendor adapters it aggregates when the mechanism and the adapters were split.) None imported the hub *directly*, so the guard did not flag them, and the closure test had no entry point for the package, so nothing else did either: from the moment the declaration landed it claimed a property the measurement contradicted, with both gates green. The remedy was placement, not indirection — the two leaves moved to `pipelex/interpreter_plugins/` and the composition moved to the layer allowed to weld (see [Where the built-in plugins split](#where-the-built-in-plugins-split)) — and the guard grew the [transitive rule](#the-rule-make-check-hub-layering) so the next one cannot hide the same way. Three lessons generalize: a package-granular declaration is a claim about the whole package, an aggregator inherits every breach it aggregates, and a rule that stops at one hop will eventually be walked around.

**The one the worked example predicted, found by declaring the package.** `graph/graph_rendering.py` imported `pipeline.dry_run_pipeline` at module level, and importing it pulled in `interpreter_hub` plus ~76 interpreter modules. Every gate stayed green, for a reason worth stating plainly: rules 1 and 3 both filter their candidates through `is_runtime_layer`, and `pipelex.graph` was not declared — so the module had been outside the rules' domain the whole time. This is the `pipelex.plugins` breach again, one level up: not a package whose declaration overreached, but a package with **no** declaration at all. The remedy was placement, as before. The module split along "do I need a loaded method?", which is this boundary's own question: the pure renderer (`GraphFormat`, `render_graph_from_spec`) stayed in `pipelex.graph`, and the bundle-driven half that has to dry-run a method first (`generate_graph_for_bundle`, `generate_view_for_bundle`) became `pipelex.pipeline.bundle_graph_rendering`, next to the `dry_run_pipeline` it exists to wrap. The lesson is the one this page now states under [The rule](#the-rule-make-check-hub-layering): **an undeclared package is not neutral, it is unpoliced** — omitting an entry makes the guard quieter, never louder.

**The one an aggregate module hid.** Five built-in vendor adapters — `providers/{anthropic,bedrock,google,mistral}/*_list.py` — imported `MissingDependencyError` from `pipelex.exceptions` rather than from its definition site in `pipelex.system.exceptions`. `pipelex/exceptions.py` is the *public all-errors aggregate*: it re-exports every interpreter package's exceptions, so importing anything from it loads `pipeline.exceptions` → `validation_errors` → `fixes.planner` and more. Each of those five declared runtime-layer modules therefore loaded 15 interpreter modules. Neither gate could see it: the guard's rules only chase `interpreter_hub`, and the aggregate never reaches it; the closure test's `providers.builtins` entry point does not cover these modules either, because the vendor plugins import them *inside a function*, which hides them from the static import graph and from the aggregator's own closure at once. The fix is the repo's existing rule — *direct full-path imports everywhere*, i.e. import from where the symbol is defined, never from a convenience aggregate — plus one new entry point (`providers.anthropic.anthropic_list`) so the runtime-truth check now covers the shape. The generalizable lesson: **a module that re-exports across layers is a layer boundary with the sign filed off**, and a deferred import will hide it from every static gate you have. Since then the rule is mechanical rather than prose: `tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py` AST-walks every package declared in `RUNTIME_LAYER_PACKAGES` and fails on any import of `pipelex.exceptions` — module-level or function-local, absolute or relative — as well as on any bare string naming it, since an `import_module` argument or a patch target loads the aggregate through a path no import node records. The next aggregate reference in the runtime layer is caught by CI instead of by review. The aggregate itself remains a legitimate public surface for callers *outside* the runtime layer; the ban is scoped to the layer whose closure it would silently widen.

- **`cogt` names four specific vendors, deliberately.** `cogt/config_cogt.py` imports `AnthropicConfig`, `GoogleConfig`, `MistralConfig` and `OpenAIConfig` from their `pipelex/providers/` packages. Both sides are runtime-layer, so this breaches no hub rule — it is a placement inversion: the vendor-neutral engine names four vendors. It is accepted rather than fixed, because the alternative is worse. The main config model is statically typed end-to-end (`system/configuration/configs.py` and the `pipelex.toml` files are structurally synced, and boot fails loud when they disagree), so making vendor config sections plugin-contributed would trade compile-time typing for a dynamic registry — a real loss to buy a cosmetic win. The edge is one-way and shallow: a config class, not a worker.
- **The img-gen one that stopped being an inversion.** `cogt/img_gen/img_gen_args_factory.py` used to import two vendor img-gen factories at module level, for taxonomy and geometry helpers. It was never a registry problem: dispatch is keyed on `AspectRatioTaxonomy`, a `cogt`-owned enum that names model families and no providers, and no family is served by a single adapter — the `openai` and `azure_openai` decks both ship GPT Image models, and the gateway worker resolves Gemini geometry through the same mapping the native Google worker uses — so there was no provider key to dispatch on, and a registrar slot would have bought a plugin-API bump for two import sites. Fixed by placement instead: the helpers are now `cogt/img_gen/img_gen_gemini_mapping.py` and `cogt/img_gen/img_gen_gpt_mapping.py`, and the Google worker and the gateway factory import *inward* to them. One `cogt → specific vendor` edge of this kind remains — `model_backends/backend_factory.py` reaching for `VertexAIFactory` — already deferred inside a function, and it self-resolves when VertexAI support is removed.
- **What pins the two bullets above.** The complete `cogt → pipelex.providers` list — the four config imports plus that one deferred factory import — is a golden set in `tests/unit/pipelex/cogt/test_cogt_dependency_boundaries.py`, together with the stronger fact that `pipelex/cogt/**` imports no vendor SDK at all. A sixth edge fails it, and nothing else in the repo would notice: both packages are runtime-layer, so the guard and the closure test are blind to an edge between them by construction. Golden sets rather than a rule, because these are *accepted* inversions — there is no predicate separating the sanctioned edges from a new one, and the point is to make the next one a diff a reviewer reads. Note the tempting generalization — *no vendor SDK anywhere in `pipelex/` outside `providers/`* — is **false**, and a test asserting it would be red on day one: `tools/pdf/pypdfium2_renderer.py`, `tools/storage/`, `tracing/` and `reporting/` import pypdfium2 and the AWS/GCP SDKs on purpose, because `providers/storage/` is a registration shim whose implementations live under `pipelex/tools/`. The scope that holds is `cogt`.
- `plugins/pipe_func_executor_registry.py` is typed by a protocol from `pipe_operators/` and defers that import under `TYPE_CHECKING` precisely because `pipelex.config` imports it and the inference layer imports `pipelex.config` — a module-level import there would drag the interpreter back into every inference closure. Being type-only it loads nothing, so it breaches neither rule — the sanctioned deferral pattern. The placement inversion itself is unfixed.
- **The one that stopped being an inversion.** `core/`'s Pipe-touching half — `pipe_abstract`, `pipe_blueprint`, `pipe_factory`, the renderers — imported the interpreter directly while sitting under a package the runtime layer wanted to declare. That was never a wrong *import* (it is a fact about what a pipe is), it was a wrong *address*, and it forced the declaration to enumerate core's data-model packages instead of naming `pipelex.core`. Fixed by placement: the modules are now `pipelex.pipe_machinery` and `pipelex.mthds_parsing`, and the six `pipelex.core.*` entries collapsed to one. Several of them still import `interpreter_hub` on purpose, to inject downward — that is the sanctioned direction and always was.
- Broader measured inversions, out of scope for the hub boundary: `cogt → core`, `system → cogt`, `plugins → runtime_bridge`, and `cogt/model_backends/model_lists.py` importing `pipelex.cli.exceptions.PipelexCLIError`. What remains of `tools → cogt` is `tools/pdf/pypdfium2_renderer.py` reaching for `cogt.extract` and `cogt.image` types; the templating half of that cluster is gone (see [Placement, not coupling](#placement-not-coupling)).

## For consumers outside this repo

`pipelex.hub` is gone; there is no shim. Every external importer must choose a layer. The symbols that crossed the repo boundary are split as follows — runtime-layer ones now come from `pipelex.runtime_hub`, interpreter-layer ones from `pipelex.interpreter_hub`, per the tables above. `get_pipelex_hub` splits into `get_runtime_hub` and `get_interpreter_hub`, so each call site must pick the container it actually meant.
