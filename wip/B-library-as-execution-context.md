# Library as Execution Context: Beyond File-System Bundles

> **Status**: Draft — braindump cleanup
> **Date**: 2026-03-23
> **Related**: [A-temporal-library-fix-proposals-v2.md](A-temporal-library-fix-proposals-v2.md)

---

## 1. The Library Is Not a Collection of Files

The current mental model treats the library as a set of bundles tied to the file system — `.mthds` files, packages, manifests. But once loaded by the `library_manager`, the library becomes something fundamentally different: a **consistent, namespace-isolated set of concepts and pipes**. The library manager resolves dependencies, enforces naming constraints across domain namespaces, and prevents conflicts.

The bundle is the file-system expression of the library. The loaded library is the runtime truth.

---

## 2. What a Pipeline Execution Actually Needs

When a pipeline runs, it needs access to **concepts and pipes** — not files. Specifically:

1. **It needs all the concepts and pipes in its dependency graph.** A pipe controller resolves child pipes, which resolve their children, and so on. Each pipe may reference concepts for its inputs and outputs. The full transitive closure of these references defines what the execution needs.

2. **It does not need anything outside that dependency graph.** A library loaded from the file system might contain 50 pipes. A given pipeline execution might only touch 15 of them and a quarter of the concepts. The rest is dead weight.

This is possible to determine statically because Pipelex's execution is deterministic — the dependency graph of a pipeline is known before execution begins. There are no dynamic pipe lookups or runtime-resolved references.

### Implication: Library Stripping

This opens a path (not yet implemented) to **strip the library down to the minimal subset** required for a given pipeline execution. This would reduce payload sizes and clarify exactly what context is needed. But it is an optimization, not a prerequisite.

---

## 3. The Compact Library Object

For distributed execution, what we need to pass around is not a mirror of the file system or a mirror of method packages. It should be a **compact library object** — a self-contained, serializable representation of the concepts and pipes needed for execution.

This object would be:

- Built from the loaded library state (post-resolution, post-namespace-enforcement)
- Scoped to a pipeline execution (either the full library or a stripped subset)
- Serializable and deserializable without requiring access to the original file system

---

## 4. The Payload Size Problem

Temporal imposes limits on data passed into and out of workflows (default 2MB). Two things need to travel with the execution:

1. **The library context** — concepts and pipes needed for execution. Can be arbitrarily large depending on the library.
2. **The working memory** — runtime data being processed. Can include images, documents, and other large payloads.

Neither of these can be reliably passed inline as workflow arguments. The working memory is especially problematic — it carries user data that can be far larger than any library.

---

## 5. Proposed Solution: External Storage Keyed by Pipeline Run

Each pipeline execution already has a **pipeline run ID**. This ID can serve as the key for external storage:

- Before dispatching to Temporal, the API process uploads the library context and working memory to a storage backend (using the existing storage provider system).
- Each workflow activity fetches the library context and working memory from storage using the pipeline run ID.
- After execution, updated working memory is written back to storage for the next step.

This pattern:

- **Decouples payload size from Temporal limits** — workflows receive a lightweight reference (the run ID), not the full data.
- **Works for both library context and working memory** — same mechanism, same storage backend.
- **Leverages existing infrastructure** — the storage provider system is already in place.
- **Scales naturally** — large libraries and large working memories are handled identically.

### Flow

```
API Process                          Storage                     Temporal Worker
─────────────                        ───────                     ───────────────
pipeline_run_setup()
  ├─ Load library
  ├─ Build compact library object
  ├─ Upload library + working_memory ──► store(run_id, ...)
  └─ Dispatch to Temporal (run_id)
                                                                 WfPipeRouter.run()
                                                                   ├─ Fetch library ◄── fetch(run_id)
                                                                   ├─ Load library into process
                                                                   ├─ Fetch working_memory ◄── fetch(run_id)
                                                                   ├─ Execute pipe
                                                                   └─ Upload updated working_memory ──► store(run_id, ...)
```

---

## 6. Open Questions

- **Caching across runs**: If the same library context is used across multiple pipeline runs (common), can we cache by library fingerprint rather than re-uploading per run?
- **Granularity of storage**: One blob per run, or separate keys for library context vs. working memory vs. intermediate results?
- **Library stripping**: When do we implement minimal-subset extraction? Is it worth the complexity now, or is shipping the full loaded library sufficient for the near term?
- **Storage backend choice**: S3-compatible? Redis for short-lived data? The storage provider abstraction should make this pluggable.
- **Consistency with v2 proposals**: How does this relate to the `LibraryContext` model and `TemporalPipeJobEnvelope` from the v2 proposals? This document argues for a more fundamental shift — externalizing both library and working memory — rather than embedding library context in the workflow input.
