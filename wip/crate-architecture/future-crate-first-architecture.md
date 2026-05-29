# Crate-First Architecture Vision

> **Status**: Vision / future direction
> **Date**: 2026-03-25
> **Related**: [../archive/00-master-plan.md](../archive/00-master-plan.md), [../archive/phase2-implementation-plan.md](../archive/phase2-implementation-plan.md)

---

## Summary

The LibraryCrate should become the central concept in library management. Today, library loading drives everything and crates are a byproduct. The future direction inverts this: **collecting blueprints and building the crate is the primary operation; loading into a live Library is just one consumer of the crate**.

This document captures the architectural direction, the Phase 2 design decision that aligns with it, and the two future capabilities it enables: crate stripping and remote dependency resolution.

---

## Phase 2 Design Decision: Blueprint Accumulation (Option A)

### The question

Phase 2 ships the `LibraryCrate` inside `PipeJob` so Temporal workers can load the full library context. Library loading happens in multiple steps (PIPELEXPATH dirs, extra library_dirs, mthds_contents), each going through `load_from_blueprints()` which internally builds a crate. The question was how to produce the final crate to ship.

### Options considered

**Option A — Accumulate blueprints, build one crate at the end.** Track all blueprints that go through `load_from_blueprints()` in a `_blueprints: dict[str, list[PipelexBundleBlueprint]]` on `LibraryManager`. After all loading is done, `get_crate(library_id)` calls `LibraryCrateFactory.make_from_blueprints()` once with the full list.

**Option B — Accumulate and merge crates.** Each `load_from_blueprints()` call produces a crate. Accumulate them in `_crates: dict[str, LibraryCrate]` on `LibraryManager`. Add a `merge()` classmethod to `LibraryCrate` that combines two crates (raise on key collision, recompute fingerprint). `get_crate()` returns the merged result.

### Decision: Option A

Option A is simpler:
- No `merge()` method needed on `LibraryCrate`
- No crate accumulation dict or fingerprint recomputation
- Fewer concepts for a developer to understand
- Blueprints are the natural unit of accumulation — they're what loading already produces

Option A is also directionally correct toward the crate-first architecture (see below). Blueprints are the raw input; the crate is built from them. Accumulating the input (blueprints) rather than intermediate outputs (crates) keeps the data flow clear.

### Why loading still happens incrementally

Loading is order-dependent: dependencies must be loaded before dependents (pipe validation needs concepts from deps to succeed). So we can't defer all loading to the end. The library needs content loaded step by step.

But **crate building for shipping purposes** is independent of the loading order. We let loading proceed as today (each step goes through its own internal crate), and build the final shipping crate once at the end from all accumulated blueprints.

---

## The Crate-First Architecture

### Current state: loading-driven

```
CURRENT ARCHITECTURE
════════════════════

  load_libraries(dirs)
    → parse .mthds files → blueprints
    → resolve local deps → more blueprints
    → load_from_blueprints(blueprints)
      → LibraryCrateFactory → crate (internal, discarded)
      → load_from_crate(crate) → live Library

  load_from_blueprints(mthds_contents_blueprints)
    → same path

  [Phase 2] get_crate() → build final crate from accumulated blueprints
```

Library loading drives everything. Crates are an internal intermediate. Dependency resolution is interleaved with loading (`_load_single_dependency` parses, creates child Library, loads concepts, builds pipes — all in one method).

### Future state: crate-driven

```
CRATE-FIRST ARCHITECTURE
═════════════════════════

  Phase 1: COLLECT (blueprints only, no Library)
  ──────────────────────────────────────────────
    Parse local .mthds files → blueprints
    Scan blueprints for deps (manifest + address-based)
    Resolve deps: local lookup + remote fetch
    Parse dep blueprints
    Recurse for transitive deps
    → all_blueprints[]

  Phase 2: BUILD CRATE (pure data transform)
  ──────────────────────────────────────────────
    LibraryCrateFactory.make_from_blueprints(all_blueprints)
    Strip to transitive closure of target pipe (optional)
    → one complete, self-contained LibraryCrate

  Phase 3: LOAD (same code path on submitter and worker)
  ──────────────────────────────────────────────────────
    load_from_crate(crate)
    → validates, creates live objects, ready to execute
```

The key shift: **dependency resolution moves out of library loading and into blueprint collection.** The crate becomes the single source of truth. Both submitter and worker use the same `load_from_crate()` path.

---

## Future Capability 1: Crate Stripping (Transitive Closure)

### What

From the entry pipe, walk the transitive closure of pipe and concept dependencies to determine the minimal subset needed. Strip the crate to only those concepts, pipes, and domains.

### Why

- Reduces Temporal payload size (relevant before StoragePayloadCodec, and even after for efficiency)
- Clarifies execution context — a worker receives exactly what it needs, nothing more
- Enables better error messages — "pipe X not in crate" vs. "pipe X not found" when deps are missing

### How it fits

Crate stripping is a pure data transform on blueprints. Controller blueprints contain pipe ref strings (PipeSequence has `steps`, PipeBatch has `pipe`, etc.), so the dependency graph can be traced from blueprints alone without loading into live Pipe objects.

In the crate-first architecture, stripping slots in between Phase 1 (collect) and Phase 2 (build):

```
  all_blueprints = collect(...)
  required_refs = trace_transitive_closure(target_pipe, all_blueprints)
  stripped_blueprints = filter(all_blueprints, required_refs)
  crate = LibraryCrateFactory.make_from_blueprints(stripped_blueprints)
```

### Current blocker

Today, dependency content goes into **child libraries** via `_load_single_dependency`, which has its own loading path that doesn't go through `load_from_crate()` or produce blueprints that accumulate. To strip, we need all blueprints (including dependency blueprints) in one flat list. This requires decoupling resolution from loading (see "What needs to change" below).

---

## Future Capability 2: Remote Package Dependencies

### What

Resolve dependencies from remote package addresses (e.g., `github.com/org/repo/package`). Fetch the package (temporary clone or download), parse its bundles, and include the needed content in the crate.

### Why

- Enables running pipelines whose dependencies aren't pre-installed on the worker
- The crate becomes truly self-contained — a worker needs nothing beyond PIPELEXPATH base
- Enables cloud-native execution where workers are stateless

### How it fits

Remote fetching is pure I/O — it doesn't need a live Library. It produces blueprints, same as local resolution. In the crate-first architecture, it slots into Phase 1 (collect):

```
  Phase 1: COLLECT
    Parse local .mthds files → blueprints
    Scan for deps (manifest + address-based)
    For each dep:
      if local: find installed package → parse blueprints
      if remote: fetch package → parse blueprints    ← NEW
    Recurse for transitive deps
    → all_blueprints[]
```

### Current blocker

Same as crate stripping: `_load_single_dependency` interleaves resolution with loading. Remote fetch would need to happen before loading, which means splitting the "resolve + collect blueprints" step from the "load into Library" step.

---

## What Needs to Change (Incremental Path)

The path from current state to crate-first is incremental. Each step is independently valuable.

### Step 1: Phase 2 (now) — Blueprint accumulation

**Already decided.** Track blueprints in `LibraryManager._blueprints`, build one crate via `get_crate()`. No merge logic. This establishes the pattern of accumulating blueprints as the unit of crate construction.

Dependency content (child libraries) is NOT included in the crate. Known limitation, accepted for Phase 2.

### Step 2: Extract blueprint collector from dependency loading

Split `_load_single_dependency` into two parts:
1. **Collect**: resolve the dependency, parse its .mthds files into blueprints, determine exports
2. **Load**: create child Library, load domains/concepts/pipes, register aliases

The collector produces blueprints. The loader consumes them. Today they're one method.

After this split, the collector's blueprints can be accumulated into `_blueprints[library_id]` alongside the main package's blueprints. The crate becomes complete (includes dependency content).

### Step 3: Add remote fetch to the collector

With the collector extracted, remote fetch is a new resolution strategy alongside local lookup:

```python
def _collect_dependency_blueprints(self, dep) -> list[PipelexBundleBlueprint]:
    match dep.resolution:
        case ResolutionStrategy.LOCAL:
            return self._collect_from_local(dep)
        case ResolutionStrategy.REMOTE:
            return self._collect_from_remote(dep)  # NEW
```

### Step 4: Add crate stripping

With all blueprints (main + deps) accumulated, add a stripping step before crate construction:

```python
def get_crate(self, library_id, target_pipe_ref=None) -> LibraryCrate | None:
    all_blueprints = self._blueprints.get(library_id)
    if target_pipe_ref:
        all_blueprints = strip_to_transitive_closure(target_pipe_ref, all_blueprints)
    return LibraryCrateFactory.make_from_blueprints(all_blueprints)
```

### Step 5 (optional): Fully separate Collect → Build → Load

At this point, the three phases are logically separate but still wired through `LibraryManager`. The final step is to make them explicitly separate, so that:
- A CLI tool can collect + build a crate without loading (e.g., `pipelex crate build`)
- A worker can load from a crate without collecting (already works via `load_from_crate`)
- Tests can construct crates directly from blueprints without the full loading machinery

---

## Cross-Package Refs in a Flattened Crate

One structural challenge for including dependency content in the crate: cross-package pipe refs use alias-based syntax (`alias::domain.pipe`). Today, these resolve through child library lookups. In a flattened crate, there are no child libraries.

Options:
1. **Resolve aliases during crate building** — replace `alias::domain.pipe` with the actual `domain.pipe` ref in all controller blueprints before they enter the crate. The crate contains only flat domain-qualified refs.
2. **Carry alias mappings in the crate** — add an `aliases: dict[str, str]` field that maps alias-prefixed refs to domain-qualified refs. `load_from_crate()` uses this to register aliased lookups.
3. **Defer** — cross-package deps on workers remain a known limitation until this is solved.

Option 1 is cleanest (the crate is fully resolved, no runtime lookup needed) but requires modifying blueprint data during crate construction. Option 2 is simpler to implement but adds runtime complexity. To be decided when we reach Step 2.

---

## Relationship to Other Phases

| Phase | Relationship to crate-first |
|-------|-----------------------------|
| Phase 2 (Temporal crate) | Establishes blueprint accumulation pattern (Step 1) |
| Phase 3 (WM hydration) | Independent — concerns deserialization, not crate content |
| Phase 4 (StoragePayloadCodec) | Complementary — handles large crates; stripping reduces need |
| Crate stripping | Step 4 of this vision |
| Remote deps | Step 3 of this vision |
| Library fingerprint validation | Independent — compares base library fingerprints |
| Cross-worker cache | Complementary — caches the crate, benefits from stripping |
