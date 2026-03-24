# The LibraryCrate: From File-System Bundles to Execution Context

> **Status**: Architecture vision
> **Date**: 2026-03-23
> **Related**: [D-master-plan-distributed-execution-v2.md](D-master-plan-distributed-execution-v2.md), [E-pipe-namespace-fix.md](E-pipe-namespace-fix.md)

---

## 1. The Three-Stage Pipeline

Library loading follows a three-stage pipeline. Each stage has a distinct role and a clean boundary with the next.

```
Bundles (files)  ──►  LibraryCrate (data)  ──►  Library (live)
```

**Bundles** are file-system and packaging artifacts: `.mthds` files, method packages with manifests, remote dependencies. They are how methods are authored, versioned, and distributed. A single domain can be spread across multiple bundle files — for example, a `scoring` domain might have `scoring_core.mthds` and `scoring_advanced.mthds`.

**LibraryCrate** is a flat, source-agnostic, serializable snapshot. It contains concept blueprints keyed by `concept_ref` and pipe blueprints keyed by `pipe_ref` — both fully-qualified with their domain prefix. It carries no memory of which file or package each blueprint came from. When multiple bundles contribute to the same domain, their blueprints simply land in the same flat dicts (strict merge — same ref appearing twice is an error).

**Library** is the live runtime. Concepts are instantiated as `Concept` objects with generated structure classes. Pipes are instantiated as `PipeAbstract` subclass instances. The library is the execution truth — what pipe controllers query when resolving child pipes at runtime.

### What about domains?

Domains are a **namespace convention**, not a runtime container. A domain like `scoring` provides the prefix in `scoring.WeightedScore` (concept) and `scoring.compute_score` (pipe). Domains help organize methods at authoring time and prevent naming conflicts, but at runtime they carry no meaningful state. The `Domain` object in the library has only `code`, `description`, and an optional `system_prompt` — none of which are needed for pipe or concept resolution. The LibraryCrate doesn't need domain-level grouping; the namespace is already encoded in the refs.

### Why a middle stage?

Without the LibraryCrate, the system jumps directly from file-system artifacts to live objects. This creates two problems:

1. **Serialization**: Live objects contain runtime state (generated classes, resolved references) that cannot be cleanly serialized. Blueprints are pure Pydantic models — they serialize trivially.

2. **Decoupling**: The live library shouldn't know about files, packages, or remote repositories. The crate is the clean handoff point: everything upstream of it deals with sourcing and parsing; everything downstream deals with instantiation and execution.

---

## 2. What a Pipeline Execution Actually Needs

When a pipeline runs, it needs access to **concepts and pipes** — not files.

1. **It needs all the concepts and pipes in its dependency graph.** A pipe controller resolves child pipes, which resolve their children, and so on. Each pipe references concepts for its inputs and outputs. The full transitive closure of these references defines what the execution needs.

2. **It does not need anything outside that dependency graph.** A library loaded from the file system might contain 50 pipes. A given pipeline execution might only touch 15 of them and a fraction of the concepts. The rest is dead weight.

This is possible to determine statically because Pipelex's execution is deterministic — the dependency graph of a pipeline is known before execution begins. There are no dynamic pipe lookups or runtime-resolved references.

### How dependencies are resolved today

When a pipeline is executed via CLI or API:

1. The caller provides a bundle (as `mthds_content` or by referencing a file) and optionally a `pipe_code` (defaults to the bundle's `main_pipe`).

2. `pipeline_run_setup()` loads **all** bundles from the provided library directories (`PIPELEXPATH`, `-L` flag, `library_dirs` parameter) and from installed methods (`.mthds/methods/` directories). This is a brute-force approach — everything available gets loaded.

3. If `mthds_content` was provided, its blueprint is loaded on top.

4. After loading, the library is validated: every pipe's dependencies (child pipes for controllers, concepts for inputs/outputs) must exist in the loaded library. If something is missing, validation fails.

This "load everything, validate after" approach works but is wasteful. It loads pipes and concepts that will never be used, and it requires that all transitive dependencies be available on the file system at load time.

---

## 3. The LibraryCrate

The LibraryCrate is a self-contained, serializable representation of the concepts and pipes needed for execution, organized by domain.

### Structure

```python
class LibraryCrate(BaseModel):
    """Complete library content, ready to load into a live Library."""
    concepts: dict[str, ConceptBlueprint]    # concept_ref (domain.Code) -> blueprint
    pipes: dict[str, PipeBlueprintUnion]     # pipe_ref (domain.pipe_code) -> blueprint
    fingerprint: str                         # SHA256 of serialized content
```

The crate is flat. No domain-level grouping — the domain is implicit in the keys (`scoring.WeightedScore`, `scoring.compute_score`). This mirrors how the live library already works for concepts (keyed by `concept_ref`), and how it will work for pipes once the `pipe_ref` fix lands.

### Properties

- **Flat and ref-keyed**: Two dicts, keyed by fully-qualified refs. Domain is a namespace prefix, not a structural container.
- **Source-agnostic**: No file paths, no bundle identity, no package provenance. The crate doesn't know (or care) where its blueprints came from.
- **Serializable**: Pure Pydantic models. JSON round-trip is trivial. This is what makes it suitable for both in-process use and wire transfer.
- **Fingerprinted**: A SHA256 digest of the serialized content enables caching — if the same crate has already been loaded, skip the work.

### How it's built

```python
# 1. Parse bundles from files
blueprints: list[PipelexBundleBlueprint] = [
    PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=path)
    for path in mthds_file_paths
]

# 2. Build crate: qualify refs with domain, merge into flat dicts
crate = LibraryCrateFactory.make_from_blueprints(blueprints)

# 3. Load into live library
library_manager.load_from_crate(library_id, crate)
```

Each bundle declares a domain (e.g., `scoring`). During crate construction, concept codes become `concept_ref`s (`Score` → `scoring.Score`) and pipe codes become `pipe_ref`s (`compute_score` → `scoring.compute_score`). Multiple bundles — even for the same domain — simply add entries to the flat dicts. If the same ref appears twice, that's a conflict — error, not silent override.

### What blueprints contain

**ConceptBlueprint** (`core/concepts/concept_blueprint.py`): `description`, `structure`, `refines`. Clean Pydantic BaseModel.

**PipeBlueprintUnion** (`core/bundles/pipelex_bundle_blueprint.py`): Discriminated union of 10 pipe blueprint types (`PipeFuncBlueprint`, `PipeLLMBlueprint`, `PipeSequenceBlueprint`, etc.). All are Pydantic models with fields for inputs, output, type-specific configuration (prompts, steps, branches, etc.).

These are already the "data form" of pipes and concepts. They parse cleanly from `.mthds` files, they serialize cleanly to JSON, and the existing factory methods (`ConceptFactory.make_from_blueprint()`, `PipeFactory.make_from_blueprint()`) know how to instantiate live objects from them.

---

## 4. Namespace Prerequisites

Before building the LibraryCrate, a fundamental asymmetry in the library must be fixed.

**Concepts are properly namespaced.** The `ConceptLibrary` indexes concepts by `concept_ref` = `domain.ConceptCode` (e.g., `scoring.WeightedScore`). Two concepts with the same code in different domains coexist without conflict.

**Pipes are NOT namespaced.** The `PipeLibrary` indexes pipes by bare `code` (e.g., `compute_score`, not `scoring.compute_score`). If two domains define a pipe with the same code, the second one collides with the first — the library raises an error as if it were a duplicate, even though they're in different domains.

This must be fixed by introducing `pipe_ref` = `domain.pipe_code` on `PipeAbstract` and rekeying `PipeLibrary` by `pipe_ref`, symmetric with how concepts work. The domain library must also support additive merging (multiple bundles contributing to the same domain).

Once `pipe_ref` is in place, the flat LibraryCrate keying becomes natural — both concepts and pipes use fully-qualified refs as dict keys, and the domain is just the prefix before the dot.

See [E-pipe-namespace-fix.md](E-pipe-namespace-fix.md) for the detailed technical spec.

---

## 5. Dependency Resolution Roadmap

Dependency resolution improves in phases, from brute-force to precise.

### Current state: Load everything

`pipeline_run_setup()` loads all bundles from all provided library paths. Validation checks that dependencies exist, but nothing is selective. The full library travels to execution even if only a fraction is needed.

### Near-term: Full crate, validated

The LibraryCrate contains everything that was loaded — the full set of domains, concepts, and pipes. This is equivalent to today's behavior but with the crate as the clean intermediate. No stripping yet.

### Planned: Static dependency tree analysis (crate stripping)

From the entry pipe, walk the transitive closure:
- For each pipe controller, collect its `pipe_dependencies()` (child pipe codes)
- For each pipe (controller or operator), collect its `concept_dependencies` (input/output concepts)
- Recursively resolve until the full dependency graph is known

Then strip the crate to only the domains, concepts, and pipes in the dependency graph. This reduces payload sizes for distributed execution and clarifies exactly what context is needed.

This is feasible because execution is deterministic — the dependency graph is fully known at build time.

### Future: Remote dependency resolution

Resolve dependencies from GitHub method package addresses. When a bundle declares a dependency on `github:org/repo`, clone to a temp directory, parse the bundles, and merge into the crate. This enables running pipelines whose dependencies aren't pre-installed locally.

---

## 6. Generalization Across Execution Modes

The LibraryCrate is **not** a Temporal-specific construct. It is the universal intermediate representation for all execution modes.

**Direct execution** (in-process):
```
Bundles → LibraryCrate → Library (live, in same process)
```

**Distributed execution** (Temporal):
```
Bundles → LibraryCrate → serialize → send to worker → deserialize → Library (live, on worker)
```

The only difference is that distributed execution adds a serialize/deserialize step. The crate itself is identical.

This means we build and validate the LibraryCrate in direct mode first. Once it works — once all existing tests pass through the `bundles → crate → library` path — distributed execution gets serialization for free because the crate is already a Pydantic model.

---

## 7. External Storage for Large Payloads

When payloads grow beyond Temporal's 2MB limit (large libraries, WorkingMemory with images/documents), external storage becomes necessary.

Each pipeline execution has a **pipeline run ID** that can serve as the storage key:

- Before dispatching to Temporal, upload the crate and working memory to a storage backend
- Workers fetch by run ID, load, execute, write back results
- Uses the existing `StorageProviderAbstract` system

This is a later optimization (Phase 4 in the master plan), not part of the core LibraryCrate design. The crate's serialization is a prerequisite — you can't upload what you can't serialize — but the storage mechanism is independent.

---

## 8. Open Questions

- **Caching by fingerprint**: If the same LibraryCrate (same fingerprint) is used across multiple pipeline runs, can workers cache the loaded library and skip re-loading? This is especially valuable for Temporal workers processing many runs with the same library.

- **Storage backend choice**: S3-compatible? Redis for short-lived data? The `StorageProviderAbstract` makes this pluggable, but the default choice matters for developer experience.

- **Domain `system_prompt` migration**: The bundle-level `system_prompt` currently flows into the `Domain` object and is used as a fallback by PipeLLM pipes that don't define their own. When we flatten the crate (no domain-level data), this fallback must be inlined at pipe factory time — each PipeLLM gets its system_prompt resolved during construction, before entering the crate. This is a small change in `PipeLLMFactory` but needs to be done as part of Phase 0 or Phase 1.
