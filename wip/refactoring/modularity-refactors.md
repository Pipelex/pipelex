# Three modularity refactors after the hub split

> ⚠ **SUPERSEDED IN PART — read [`../../TODOS.md`](../../TODOS.md) first.** An engineering review on 2026-07-27 (plus an independent Codex pass) reversed and re-ruled several decisions below. The tracker is now authoritative for *what to do*; this document remains the record of the *original* reasoning. Specifically:
>
> - **D-M1-2 is REVERSED.** `pipe_blueprint.py` is **interpreter-layer and moves**, together with `validation.py`, `template_guard_lint.py` and `handle_pipe_errors.py`. The measurement below counts **outbound** imports, which tells you whether a module is a *leaf*, not which layer owns it. The deciding test is **inbound**: zero declared runtime-layer modules import any of those four. Sections "The rulings that shape the hoist" (below), move 5, and the Decisions row for D-M1-2 are all stale.
> - **The rule of thumb is NOT rewritten.** *"If it names a `Pipe`, it belongs to the interpreter layer"* was correct all along; move 5's proposed replacement only existed to accommodate the `pipe_blueprint` misclassification.
> - **F1 uses no registry.** `inference_backend_registry` is `(family, sdk) → MakeWorkerFn`, and `make_args_for_model` receives no sdk — dispatch is by `AspectRatioTaxonomy`. The fix is a neutral mapping module under `cogt/img_gen/`.
> - **M2 is not release-gated** (zero external consumers of `pipelex.plugins.<vendor>`), and its "vendor modules importing anything but the mechanism = 0" exit metric is false by construction — cross-vendor edges are deliberately preserved.
> - **M1 stacks on M3**; the "each track branches from the #1064 base" note in [Sequencing](#sequencing) is superseded.

**Status: DRAFT v2, not started.** Written on `refactor/Modularity-3`, which is based on `refactor/Hub-2` (PR #1064) — deliberately: all three tracks build on the F1 remedy (`pipelex/interpreter_plugins/`, the transitive guard rule), so #1064 merges first and these PRs land on top of it. Every number below is measured on that tree with the snippets recorded in [Measurement](#measurement); nothing here is estimated. v2 folds in the review pass: the naming and layer questions that were open in v1 are now recorded rulings in [Decisions](#decisions), and the operational costs v1 missed (subject-grant re-pathing, error-page regeneration, test-tree mirroring) are in [Ground rules for the moves](#ground-rules-for-the-moves).

Three tracks that continue the boundary work the hub split started. They are ordered by dependency, not by value: **M3 is a prerequisite slice of M1**, and **M2 is independent of both**.

| track | what | why now |
| --- | --- | --- |
| [M3](#m3--split-the-boot-manifest-by-layer) | split `CoreRegistryModels` by layer, seed the pipe-machinery package | removes core's fattest interpreter edge (92 modules) in one small, self-contained PR |
| [M1](#m1--make-cores-layer-split-physical) | hoist core's interpreter-layer modules out of `core/` | makes the boundary visible in the tree instead of in a guard tuple; collapses `RUNTIME_LAYER_PACKAGES` |
| [M2](#m2--separate-the-plugin-mechanism-from-the-vendor-adapters) | split `pipelex/plugins/` into mechanism + providers | one package name currently hides a clean one-way dependency behind an apparent cycle |

**All three break external imports.** The repo already owes a release-gated cross-repo sweep for the hub split, the Phase 3 type moves, and the `interpreter_plugins` relocation (see [`wip/hub/hub-split-tracker.md`](../hub/hub-split-tracker.md) → Cross-repo sweep). Every rename below lands in the same consumer repos. **Do these before that sweep executes**, so consumers absorb one breaking wave instead of four. That is the single strongest scheduling argument in this document.

---

## M3 — split the boot manifest by layer

### What is true today

`core/registry_models.py` is **not core**. It has exactly one consumer in the entire tree:

```python
# pipelex/pipelex.py:500
self.class_registry.register_classes(CoreRegistryModels.get_all_models())
```

It is a boot-time composition manifest that happens to live in `core/`. And it holds **two unrelated registries in one class**:

- `PIPE_OPERATORS`, `PIPE_OPERATORS_FACTORY`, `PIPE_CONTROLLERS`, `PIPE_CONTROLLERS_FACTORY`, `PIPE_SIGNATURES`, `PIPE_SIGNATURES_FACTORY` — every one of these imports `pipe_operators` / `pipe_controllers` / `pipe_signature` directly. This half is what makes the module load **92 interpreter modules**, the fattest single module in `core/`.
- `STUFF`, `EXPERIMENTAL`, `FIELD_EXTRACTION` — pure `core.stuffs`, zero interpreter modules.

`RegistryModels.get_all_models()` reflects over every list `ClassVar` via `dir(cls)`, so splitting one class into two is mechanical and boot registers both.

### Moves

1. **Split `CoreRegistryModels` by layer, with the names decided up front.**
   - `core/registry_models.py` keeps the value-model half (`STUFF`, `EXPERIMENTAL`, `FIELD_EXTRACTION`) under the name `CoreRegistryModels` — still accurate, since core's runtime half is exactly the value model. Measures 0 interpreter modules after the split.
   - The pipe half becomes `PipeRegistryModels` in **`pipelex/pipe_machinery/registry_models.py`** — M3 creates the `pipe_machinery/` package with just this module, and M1 fills it ([D-M1-1](#decisions)). No placeholder, nothing moves twice.
   - `pipelex.py` registers both. Two adjacent `register_classes` lines that read as obviously-different registrations; no behavior change.

2. **Leave `PipeType` / `PipeCategory` where they are** (`core/pipes/pipe_blueprint.py`). They are string tags naming no class and the module measures 0 — it is runtime-layer by measurement and stays in `core/` permanently ([D-M1-2](#decisions)).

3. **Document the registration surface.** After the move, "adding a pipe kind" is: the kind's package, the type tag, the blueprint union, `PipeRegistryModels`, the spec map (`builder/pipe/pipe_spec_map.py` + `pipe_spec_union.py`). Write that list into `docs/contribute/` so it stops being tribal knowledge — with a note that the spec-layer parallel in `builder/pipe/` is deliberate (see `pipelex/builder/CLAUDE.md`, spec vs blueprint), not duplication to be collapsed.

### Cut from v1: the `PipeBlueprintUnion` extraction

v1 proposed extracting `PipeBlueprintUnion` out of `core/bundles/pipelex_bundle_blueprint.py` as part of M3. Cut, for two reasons v1 only half-admitted: the extraction moves import *statements* but not the closure (`pipelex_bundle_blueprint` still measures 28 interpreter modules either way), and M1 hoists `core/bundles/` out of `core/` anyway — so an extracted union module would **move twice**. Once the module leaves `core/`, its twelve blueprint imports are no longer inverted and the extraction buys nothing. The union stays where it is and rides the M1 hoist; discoverability of the manifests is handled by the registration-surface doc (move 3), not by file adjacency.

### Exit criteria — measured

`core/` reaches up into the pipe-kind packages in **43 import statements**, concentrated in two files:

| source module | `pipe_operators` | `pipe_controllers` | `pipe_signature` | total | moved by |
| --- | --- | --- | --- | --- | --- |
| `core.registry_models` | 14 | 8 | 2 | **24** | M3 |
| `core.bundles.pipelex_bundle_blueprint` | 7 | 4 | 1 | **12** | M1 |
| `core.interpreter.bundle_elaborator` | 2 | 2 | — | 4 | M1 |
| `core.pipes.rendering.output_renderer` | — | 2 | — | 2 | M1 |
| `core.pipes.pipe_abstract` | — | — | 1 | 1 | M1 |

| | before | target after M3 | target after M1 |
| --- | --- | --- | --- |
| inverted `core → pipe_*` statements | 43 | 19 | 0 |
| interpreter modules loaded by `pipelex.core.registry_models` | 92 | 0 | 0 |
| pipe-kind manifests filed inside `core/` | 2 | 1 | 0 |

**CHECKPOINT M3** — gates: `make agent-check` + full `make agent-test` + `make drift-check`, plus the grant re-path from the [ground rules](#ground-rules-for-the-moves). Re-take the [core classification](#measurement) and confirm `core.registry_models` reports 0. This is a natural handoff point: M3 lands as its own PR, and M1 starts from a tree where core's fattest interpreter edge is already gone and the pipe-machinery package exists.

---

## M1 — make core's layer split physical

### What is true today

`docs/contribute/hub-layering.md` already says it: *"`pipelex/core/` is not one layer, and trying to declare it one was the mistake this section records."* But the split exists only inside the guard's configuration:

```python
RUNTIME_LAYER_PACKAGES = (..., "pipelex.core.concepts", "pipelex.core.domains",
   "pipelex.core.memory", "pipelex.core.pipes.inputs",
   "pipelex.core.pipes.stuff_spec", "pipelex.core.stuffs")
```

Six sub-paths enumerated by hand — plus `core.pipes.pipe_output`, which *is* runtime-layer but cannot be listed because the declaration is package-granular, so the doc has to explain that the closure test covers it instead. The boundary lives in a tuple and a paragraph, not in the tree.

### The finding

The residue is far smaller than the six-entry declaration suggests. Importing each `core` module in a subprocess and counting interpreter modules loaded: **86 of 95 measure zero**. The nine that do not:

| module | interpreter modules loaded | pulls in `interpreter_hub` |
| --- | --- | --- |
| `core.registry_models` | 92 | yes |
| `core.pipes.pipe_factory` | 48 | yes |
| `core.pipes.rendering.input_renderer` | 48 | yes |
| `core.pipes.rendering.output_renderer` | 48 | yes |
| `core.pipes.pipe_abstract` | 30 | no |
| `core.bundles.pipe_sorter` | 28 | no |
| `core.bundles.pipelex_bundle_blueprint` | 28 | no |
| `core.interpreter.bundle_elaborator` | 28 | no |
| `core.interpreter.interpreter` | 28 | no |

M3 removes the first one outright. **Eight modules** stand between `core/` and being a single declared runtime-layer package, and they are the whole of M1's hoist.

### The rulings that shape the hoist

Two places where the doc's rule of thumb ("if it names a `Pipe`, it belongs to the interpreter layer") and the measurement disagreed are now settled — **the measurement wins**, because the closure property is what the guard actually enforces ([D-M1-2](#decisions)):

- **`core/pipes/pipe_blueprint.py` is runtime-layer and stays in `core/`.** It imports only `core.concepts` and `core.pipes` siblings and measures 0; what it declares is `PipeType` / `PipeCategory` / the signature-normalization helpers — vocabulary and parse-time validation, not machinery. The doc's claim that every Pipe-naming module "imports `pipe_operators` / `pipe_controllers` directly" is factually wrong for this module; the rewrite (move 5) fixes the rule, not the module.
- **The four measured-zero leaf modules move with their packages.** `core.bundles.exceptions`, `core.interpreter.exceptions`, `core.interpreter.helpers`, `core.interpreter.validation_error_categorizer` measure 0, but cohesion wins: their importers are `cli/`, `libraries/`, `pipeline/`, `builder/` — none runtime-layer-declared (the `core/pipes/handle_pipe_errors.py` mention is a docstring, not an import) — so hoisting them breaches nothing, and an interpreter-layer module is free to measure 0.

### Moves

1. **Hoist the eight interpreter-layer modules (plus the four leaf modules) out of `core/`, into the two packages the groups already form:**
   - **`pipelex/mthds_parsing/`** — bundle parsing, MTHDS text → `PipelexBundleBlueprint` ([D-M1-3](#decisions)): `interpreter.py`, `bundle_elaborator.py`, `pipe_sorter.py`, `pipelex_bundle_blueprint.py`, `helpers.py`, `validation_error_categorizer.py`, and the two exceptions modules merged into one `mthds_parsing/exceptions.py` (topical split only if a circular import forces it, per the error-class location convention). `core/bundles/` and `core/interpreter/` cease to exist.
   - **`pipelex/pipe_machinery/`** — the pipe base machinery, joining `registry_models.py` from M3: `pipe_abstract.py`, `pipe_factory.py`, `rendering/`.

   The machinery package is deliberately **not** named `pipelex/pipes/`: `core/pipes/` remains (inputs, stuff_spec, pipe_output, validation — the runtime half), and two `pipes` packages in adjacent layers would be actively confusing.

2. **Rename the parser class along with its package.** `core/interpreter/` shares its word with the interpreter *layer* and means something narrower — and the collision extends to the class: `PipelexInterpreter` becomes **`MthdsParser`** in `mthds_parsing/interpreter.py` → `mthds_parsing/parser.py`. Parsing the language is an MTHDS-owned concept, so the name is correctly branded. (Renaming `PipelexBundleBlueprint` itself is out of scope — it is wire-visible and widely consumed; if its branding is ever revisited, that is its own track.)

3. **Collapse the guard declaration** to `"pipelex.core"` and delete the `pipe_output` carve-out paragraph from `docs/contribute/hub-layering.md`.

4. **Extend the measurement classification set.** The interpreter-package set in the [measurement snippet](#measurement) (and any permanent check derived from it) gains `mthds_parsing` and `pipe_machinery` — otherwise the re-taken classification would silently under-count.

5. **Rewrite the doc's rule of thumb** to match what the guard enforces: **"if it imports a pipe kind or constructs pipes, it is interpreter-layer; declaring the vocabulary (type tags, blueprint base shapes, signature normalization) is runtime."** The old "names a `Pipe`" phrasing was a good teaching rule but it misclassifies `pipe_blueprint`, and the doc and the guard should not silently diverge.

### Exit criteria — measured

| | before | target |
| --- | --- | --- |
| `RUNTIME_LAYER_PACKAGES` entries naming `pipelex.core.*` | 6 | 1 (`pipelex.core`) |
| `core` modules loading > 0 interpreter modules | 9 | 0 |
| doc carve-outs for `core.pipes.pipe_output` | 1 | 0 |

**CHECKPOINT M1** — gates as above, plus: re-run the [core classification](#measurement) with the extended set and confirm every remaining `pipelex.core.*` module reports 0; confirm `make check-hub-layering` still passes with the collapsed declaration; confirm the transitive rule still reports 0 breaching runtime-layer modules; `make generate-error-pages` and confirm error-page/`type_uri` stability for the moved exception classes ([ground rules](#ground-rules-for-the-moves)).

### Cross-repo blast radius

Small, and known. Grepping the sibling repos for the nine modules:

| repo | file | symbol |
| --- | --- | --- |
| `pipelex-api` | `api/routes/pipelex/build/runner.py` | `PipelexBundleBlueprint` |
| `pipelex-api` | `api/routes/pipelex/crate_ops.py` | `PipeAbstract` |
| `pipelex-api` | `tests/unit/test_validate_errors.py` | `PipelexBundleBlueprintValidationErrorData` |

No external consumer imports `PipelexInterpreter`, so the class rename adds nothing to the sweep. Clean: `pipelex-cookbook`, `cocode`, `pipelex-mistralai-workflows`, `pipelex-worker`, `pipelex-starter-python`, `pipelex-relay`, `sandbox`. `pipelex-temporal` is private and not checked here — verify during the sweep. None of the classes registered in the kajson class registry move (pipe classes stay in `pipe_operators/` etc.), so serialized payloads are untouched.

---

## M2 — separate the plugin mechanism from the vendor adapters

### What is true today

`pipelex/plugins/` is 11.4k lines across 127 files, and it is two things:

- **the mechanism** — 17 top-level modules, 1,436 lines: `contract.py`, `registrar.py` (387), `discovery.py` (161), `exceptions.py` (287), seven `*_registry.py`, `model_handle.py`, `sdk_client_registry.py`, `sdk_client_manager.py`, `backend_extras_factory.py`, `builtins.py`
- **the built-in vendor adapters** — 17 directories, ~9,900 lines: `openai/` 17 files, `gateway/` 14, `bedrock/` 11, `google/` 9, `mistral/` 9, `anthropic/` 8, `portkey/` 7, plus fal, docling, linkup, huggingface, azure_rest, blackboxai, openrouter, pypdfium2, secrets, storage

### The problem

**One package name hides a one-way dependency behind an apparent cycle.** The two heaviest edges in the whole repo are `plugins → cogt` (380 statements) and `cogt → plugins` (15). That reads as a cycle. It is not:

- every vendor directory imports **only** mechanism modules — `contract`, `registrar`, `inference_backend_registry`, `model_handle`, `sdk_client_registry`, `backend_extras_factory` — which is adapters importing the ports they implement, upward and correct
- the `cogt → plugins` half is `llm_worker_factory` / `img_gen_worker_factory` / `extract_worker_factory` / `search_worker_factory` reaching `inference_backend_registry` and `model_handle` — the engine importing the registry, downward and correct

**No mechanism module imports a vendor, with exactly one exception: `builtins.py`**, which is the composition root. That is the same shape the F1 remedy already established for `interpreter_plugins/builtins.py`, so the precedent and the pattern are both in place. Separating mechanism from adapters makes this structure visible in the tree: adapters → mechanism, engine → mechanism, mechanism → nothing.

A secondary point, stated honestly: v1 led with "the name misleads" — `pipelex/plugins/openai/` inviting the conclusion that OpenAI support is external. That argument is real but overstated: each vendor directory ships a `*Plugin` class implementing the `PipelexPlugin` contract, so they genuinely *are* plugins — first-party built-in ones, a category the docs already use comfortably. The conflation of mechanism with adapters is the load-bearing reason to split; the naming clarity is a bonus.

### The seven `cogt → <specific vendor>` edges — split ruling

Seven statements reach from `cogt` *into a specific vendor package*:

```
cogt/config_cogt.py                  -> plugins.{anthropic,google,mistral,openai}.*_config
cogt/img_gen/img_gen_args_factory.py -> plugins.{google,openai}.*_img_gen_factory
cogt/model_backends/backend_factory.py -> plugins.openai.vertexai_factory
```

These are two different animals, and they get two different rulings ([D-M2-2](#decisions)):

- **The four config imports are accepted and documented.** The main config model is statically typed end-to-end (`configs.py` ⇄ `pipelex.toml` structural sync); making vendor config sections plugin-contributed would trade that static typing for a dynamic registry — over-engineering given this repo's config discipline. Record them as a known, deliberate exception in `hub-layering.md`'s Known inversions.
- **The three factory imports are a defect, fixed as a separate small follow-up.** `img_gen_args_factory` naming `GoogleImgGenFactory` / `OpenAIImgGenFactory`, and `backend_factory`'s inline `vertexai_factory` import, are exactly what `inference_backend_registry` exists to dispatch. Fix them behind the registry — but *not* inside the 127-file move, where a behavior change would be invisible in the diff.

### Moves

1. **Keep `pipelex/plugins/` for the mechanism only** — contract, registrar, discovery, exceptions, the registries, the SDK client machinery. That package then genuinely is "how an extension plugs in", matching the docs.

2. **Move the 17 vendor directories to `pipelex/providers/`** ([D-M2-1](#decisions)). `providers/` beats v1's preferred `backends/` on two concrete grounds: `backends/` would collide with the existing `pipelex/cogt/model_backends/` (two "backends" packages in adjacent layers), and the code's own vocabulary for the non-inference adapters is already "provider" — `secrets_provider_registry`, `storage_provider_registry` — so `providers/secrets/` and `providers/storage/` fit without the nesting workaround `backends/` would force. "Inference provider" is also the natural industry term, and the directories are keyed by vendor, not capability.

3. **`builtins.py` follows the vendors** (`pipelex/providers/builtins.py`) and keeps exporting `RUNTIME_BUILTIN_PLUGINS` / `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES`. `interpreter_plugins/builtins.py` re-points its downward import. Both remain parameters of `build_registrar`, unchanged.

4. **Add `pipelex.providers` to `RUNTIME_LAYER_PACKAGES`.** The vendors are runtime-layer today by declaration and by measurement; the split must not silently drop them from the guard. This is the one step where a mistake is invisible — the transitive rule is what catches it.

5. **Cross-vendor edges survive unchanged** (`blackboxai` / `openrouter` / `portkey` → `openai`; `gateway` → `fal` / `google` / `openai` / `portkey`) because they stay inside the new package.

### Exit criteria — measured

| | before | target |
| --- | --- | --- |
| mechanism modules importing a vendor | 1 (`builtins.py`, by design) | 0 in `plugins/`, 1 in `providers/` |
| vendor modules importing anything but the mechanism | 0 | 0 (unchanged) |
| `cogt → <specific vendor>` statements | 7 | 7 (4 documented in Known inversions; 3 queued as the registry follow-up) |
| `RUNTIME_LAYER_PACKAGES` covers every vendor module | yes | yes |

**CHECKPOINT M2** — gates as above, plus a re-run of the transitive layering rule confirming 0 breaching runtime-layer modules, the closure test still reporting 0 interpreter modules for every runtime entry point, and `make generate-error-pages` if any vendor directory carries an exceptions module.

### Cross-repo blast radius

Anything importing `pipelex.plugins.<vendor>.*` breaks. In-tree that is 7 statements in `cogt` and 67 test files. External: `pipelex-api`, `pipelex-cookbook`, `cocode`, `pipelex-mistralai-workflows` all import `pipelex.plugins.*` or `pipelex.core.*` — size the vendor-specific subset during the sweep. `pipelex-temporal` (private) is unchecked here.

The *plugin entry-point contract* is unaffected: an external plugin imports `pipelex.plugins.contract` / `pipelex.plugins.registrar`, both of which stay put. That is the surface we promised third parties, and it does not move.

---

## Decisions

The questions v1 left open, now ruled. Each ruling is recorded where it is applied; this table is the index.

| id | ruling | why |
| --- | --- | --- |
| **D-M1-1** | The pipe manifest lives in `pipelex/pipe_machinery/registry_models.py` as `PipeRegistryModels`; M3 creates the package, M1 fills it | next to `PipeAbstractType` / `PipeFactoryProtocol` that type its lists; no placeholder, nothing moves twice |
| **D-M1-2** | The measurement wins over the "names a `Pipe`" heuristic: `pipe_blueprint.py` is runtime and stays in `core/`; the four measured-zero leaf modules move with their packages | the closure property is what the guard enforces; leaf-module importers verified non-runtime, so cohesion is free |
| **D-M1-3** | `core/interpreter/` + `core/bundles/` → `pipelex/mthds_parsing/`; `PipelexInterpreter` → `MthdsParser` | says what it does, correctly MTHDS-branded, and evicts the colliding word from both the path and the class |
| **D-M2-1** | Vendors move to `pipelex/providers/`, flat (no capability nesting) | avoids the `cogt/model_backends` collision `backends/` would create; matches the existing `*_provider_registry` vocabulary; directories are keyed by vendor |
| **D-M2-2** | The four `cogt` config imports: accepted, documented in Known inversions. The three factory imports: defect, fixed behind the registry as a separate follow-up after M2 | static config typing is worth keeping; the factory fix is a behavior change and must not hide inside a 127-file rename |

## Ground rules for the moves

Cross-cutting operational costs that apply to every track — v1 missed all three, and the first one would have made the first `make agent-check` after any move fail confusingly.

- **Re-path subject grants in the same commit as each move.** `subject_grants.toml` keys grants by `<path>::<qualname>`, and staleness is symmetric: a grant whose def moved **hard-fails** `check-keyword-only`. Every track that moves files rewrites the affected path prefixes in the registry in the same commit as the `git mv`, then verifies with `make cko`. Do not rely on the auto-fixer here — `fko` would silently keyword-only the "ungranted" subjects instead.
- **Regenerate error pages when an exceptions module moves.** The per-class pages under `docs/errors/` are what each error's `type_uri` dereferences to. After any move that relocates an error class, run `make generate-error-pages` (alias `gep`) and confirm the pages — and any module-path-derived component of the URIs — are stable or intentionally changed.
- **Mirror the test tree and clean derived state.** `tests/unit/` mirrors source paths; each move drags its test files along in the same commit. Run `make cleanderived` after the moves so pytest collection and the linters don't chase ghosts.

## Sequencing

```
PR #1064 (refactor/Hub-2) merges
    ↓
M3  →  M1        (M3 removes core's fattest interpreter edge and seeds pipe_machinery/; M1 hoists the rest)
M2               (independent — can run in parallel or in either order)
    ↓
follow-up: the three cogt factory imports behind the registry (D-M2-2)
    ↓
release-gated cross-repo sweep  (one wave: hub split + Phase 3 moves + interpreter_plugins + M1 + M2 + M3)
```

Each track is its own PR with its own checkpoint, branched from the #1064-inclusive base. None of them should be merged into the sweep's own branch — the sweep consumes their results.

## Measurement

Core module classification, run from the repo root on a synced venv. Reports, per `pipelex.core.*` module, how many interpreter modules it loads and whether it drags in `interpreter_hub`. `I` must name every interpreter top-level package — it is one of three copies of that set (the others are `INTERPRETER_PACKAGES` in the closure test and the `INTERPRETER` set in `docs/contribute/hub-layering.md`'s verification snippet), and a package missing from any one of them makes that check pass vacuously. `"pipe_machinery"` was added by M3, `"mthds_parsing"` by M1a:

```bash
.venv/bin/python - <<'PY'
import os, subprocess, sys

ROOT = os.getcwd()
SNIP = '''
import sys, importlib
importlib.import_module(%r)
I = {"libraries", "pipe_operators", "pipe_controllers", "codegen", "builder", "interpreter_plugins", "pipe_signature", "pipe_machinery", "mthds_parsing"}
bad = sorted(n for n in sys.modules if n.startswith("pipelex.") and len(n.split(".")) > 1 and n.split(".")[1] in I)
print(len(bad), int("pipelex.interpreter_hub" in sys.modules))
'''
mods = []
for dirpath, dirnames, files in os.walk(os.path.join(ROOT, "pipelex", "core")):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    for f in files:
        if not f.endswith(".py"):
            continue
        rel = os.path.relpath(os.path.join(dirpath, f), ROOT)[:-3].replace(os.sep, ".")
        mods.append(rel[:-9] if rel.endswith(".__init__") else rel)
for m in sorted(mods):
    r = subprocess.run([sys.executable, "-c", SNIP % m], capture_output=True, text=True, cwd=ROOT)
    n, hub = r.stdout.split()
    if int(n) or int(hub):
        print(f"INTERP  interp_mods={n:<4} hub={hub}  {m}")
PY
```

Cross-package import-statement counts (the `core → pipe_operators` style numbers) come from an `ast` walk resolving relative imports against the importing module's package, counting one per `Import` / `ImportFrom` whose target's second path segment differs from the source's. The hub-layering guard already carries a correct implementation of that graph — prefer extending `hub_layering_guard.py` over re-deriving it if any of this becomes a permanent check.
