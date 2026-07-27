---
description: Every place a new pipe kind has to be registered, and why the list is as long as it is.
---

# Registration surface

A pipe kind is not one class. Adding `PipeFoo` means touching a handful of separate places, none of which the others infer — there is no plugin registry for pipe kinds and no scan of the tree. This page is the checklist, and the explanation of which of those places are genuinely load-bearing versus which look like duplication and are not.

## What a pipe kind is made of

Each kind lives in its own package under `pipelex/pipe_operators/<kind>/` or `pipelex/pipe_controllers/<kind>/`, and holds three classes:

| file | class | role |
| --- | --- | --- |
| `pipe_foo_blueprint.py` | `PipeFooBlueprint` | the MTHDS language surface — what a `.mthds` file parses into |
| `pipe_foo.py` | `PipeFoo` | the runnable pipe |
| `pipe_foo_factory.py` | `PipeFooFactory` | blueprint → pipe |

`PipeSignature` follows the same shape from `pipelex/pipe_signature/`, with the caveat noted below.

## The checklist

1. **The kind's package** — the three classes above, plus an `exceptions.py` if the kind raises its own errors (see the error-class location convention in the Python standards).

2. **The type tag** — add the value to `PipeType` in `pipelex/pipe_machinery/pipe_blueprint.py`, and give it an arm in the `category` property that maps it to `PipeCategory.PIPE_OPERATOR` or `PipeCategory.PIPE_CONTROLLER`. The match is exhaustive with no `case _`, so the type checker walks you to every remaining site — that is the point of writing it that way.

3. **The blueprint union** — add `PipeFooBlueprint` to `PipeBlueprintUnion` in `pipelex/mthds_parsing/pipelex_bundle_blueprint.py`. It is a pydantic discriminated union keyed on the `type` field, so a kind absent from the union is a parse error on any `.mthds` file that names it, not a silent skip.

4. **The registration manifest** — add `PipeFoo` and `PipeFooFactory` to `PipeRegistryModels` in `pipelex/pipe_machinery/registry_models.py`, in `PIPE_OPERATORS` / `PIPE_OPERATORS_FACTORY` or `PIPE_CONTROLLERS` / `PIPE_CONTROLLERS_FACTORY`. This is the one whose omission is **silent**: boot succeeds either way, and the failure surfaces later as a kajson deserialization error on a pipe. `tests/unit/pipelex/test_registry_models_split.py` pins the manifests against the class registry for exactly that reason.

5. **The spec layer** — add `PipeFooSpec` under `pipelex/builder/pipe/`, then register it in **both** `pipe_spec_map.py` (`pipe_type_to_spec_class`, the authoring lookup) and `pipe_spec_union.py` (`PipeSpecUnion`, the discriminated union). The two are separate on purpose: the union carries `PipeSignatureSpec`, the map does not, because a signature is not a user-selectable type.

## Why `core/` no longer holds the manifest

`PipeRegistryModels` used to live in `pipelex/core/registry_models.py` alongside core's value model. Importing it loads every pipe operator, every pipe controller and their factories — so a module filed under `core/` pulled in the whole interpreter, and `core` read as a dependant of the pipe packages it is supposed to sit below. The manifest now lives in `pipelex/pipe_machinery/`; `core.registry_models` keeps `CoreRegistryModels` (the stuff-content classes) and imports nothing from `pipe_operators` / `pipe_controllers` / `pipe_signature`.

Both manifests are registered side by side at boot (`pipelex/pipelex.py`), and they must stay **disjoint** — a class in both is a sign one half was edited without the other.

See [Hub Layering](hub-layering.md) for the layer boundary this split serves.

## The spec/blueprint parallel is deliberate

Steps 3 and 5 look like the same list written twice. They are not, and collapsing them would be a mistake:

- **Blueprints are the MTHDS language.** `PipeFooBlueprint` defines what an author may write in a `.mthds` file. It is the reference for the standard.
- **Specs are an authoring convenience for AI agents.** `PipeFooSpec` is a simplified shape with convenience fields that `to_blueprint()` transforms into blueprint fields. Spec-level fields deliberately differ from blueprint-level ones — `PipeComposeSpec.target_format` is a spec convenience with no blueprint counterpart, for instance.

The two layers evolve for different reasons and answer to different consumers, so they carry their own unions. When adding validation or a field, decide which layer owns it first: language rules go on blueprints, authoring convenience goes on specs. `pipelex/builder/CLAUDE.md` is the canonical statement of that split.
