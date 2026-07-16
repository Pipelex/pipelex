---
title: "Content Generation Across Boundaries"
description: "How Pipelex serializes dynamic Pydantic models and large binary content across a worker boundary — JSON schema propagation, class source injection, and storage-based payload offloading — independent of the host runtime."
---

# Content Generation Across Boundaries

This page is for contributors working on Pipelex internals. For the capability overview, see the user-facing [Distributed Execution](../distributed-execution/index.md) page instead.

When content generation (LLM structured output, image generation, PDF extraction, web search) runs on a separate worker process, two serialization problems appear that single-process execution never faces. This page covers them backend-neutrally — the mechanisms live in open core and are the same regardless of which host runtime carries the payload. The concrete activity dispatch is a [commercial platform capability](https://pipelex.com/products#durable-execution); each backend (Temporal, Mistral Workflows) realizes it in its own plugin.

!!! note "Every inference leaf goes through the same seam"
    All inference operators dispatch their leaf call through the swappable `ContentGenerator` abstraction (`pipelex/cogt/content_generation/content_generator.py`): direct inline, or — on a host runtime — wrapped as an activity by the runtime's in-workflow content generator. The backend choice is independent of the run mode: under `run_mode=DRY` the chosen backend still dispatches and the leaf mocks inside it. Wrapping the leaf as a host-runtime activity is what makes it replay-safe (the result is recorded in the run's history) and lets a leaf failure cross the worker boundary as a classified error, instead of re-executing on every replay and hanging the submitter with an unclassified fault.

---

## The two serialization challenges

| Challenge | Trigger | Root cause | Solution |
|-----------|---------|------------|----------|
| **Dynamic class propagation** | LLM structured output (`PipeLLM` with object concept) | The submitter creates a Pydantic model at runtime from `.mthds` concept definitions; the worker process has no such class | Embed the JSON schema in the assignment, reconstruct the class on the worker, carry the source code through the transport's payload metadata |
| **Large payload management** | Image generation (`PipeImgGen`), PDF extraction (`PipeExtract`) | Binary data (base64 images, rendered pages) exceeds a host runtime's payload limit (Temporal's is ~2 MB) | Activities store binary data to external storage, return lightweight URI references |

---

## Dynamic class propagation

### Schema embedding

When a pipe produces structured output, the caller captures the Pydantic model's JSON schema into the assignment — a serializable argument that carries everything the worker needs:

```python
class ObjectAssignment(BaseModel):
    object_class_name: str
    object_class_schema: dict[str, Any]
    llm_assignment_for_object: LLMAssignment

    @staticmethod
    def make_for_class(
        object_class: type[BaseModel],
        llm_assignment: LLMAssignment,
    ) -> "ObjectAssignment":
        return ObjectAssignment(
            object_class_name=object_class.__name__,
            object_class_schema=object_class.model_json_schema(),
            llm_assignment_for_object=llm_assignment,
        )
```

The schema is a plain `dict` — fully serializable, inspectable on the wire, and self-contained. No class reference crosses the process boundary.

### Schema-to-model reconstruction

On the worker, `SchemaToModelFactory.make_from_json_schema(schema, *, class_name)` (`pipelex/cogt/content_generation/schema_to_model_factory.py`) rebuilds a live Pydantic class from the embedded schema:

```python
source_code = cls._generate_source_from_schema(schema)        # datamodel-code-generator
reconstructed_class = cls._exec_and_extract_class(source_code, class_name=class_name)  # exec()
reconstructed_class.__kajson_class_source__ = source_code  # attached for downstream use
```

The reconstruction pipeline:

1. **Generate** — `datamodel-code-generator` converts the JSON schema into Python source code defining a `BaseModel` subclass.
2. **Execute** — `exec()` compiles the source in an isolated namespace and extracts the named class.
3. **Cache** — A thread-safe SHA-256 hash cache is guarded by a single lock held across the entire check-then-generate sequence, not double-check locking: the lock is acquired once, the cache is checked, and — on a miss — generation and exec happen before the lock is released. This kills same-schema thundering herds (concurrent first-misses each paying a full codegen+exec round) at the cost of serializing cache hits on other schemas behind any in-flight miss, an acceptable trade-off given real workloads use a small bounded set of distinct schemas cached for the process lifetime.
4. **Tag** — The generated source code is attached as `__kajson_class_source__` on the class, enabling Kajson to carry it through the transport.

!!! warning "Class name normalization"
    `datamodel-code-generator` normalizes schema titles to PascalCase (e.g., `dynamic_concept_test__Greeting` becomes `DynamicConceptTestGreeting`). The code tries both the original and normalized names. If neither matches, it raises `ValueError` listing the available classes.

### Carrying the class source across the boundary

The reconstructed class's source rides in the transport's **payload metadata**, not in the payload data itself — keeping the JSON payload clean and the reconstruction transparent. A host runtime's data converter injects it on serialize and re-attaches it on deserialize:

**Serialize:**

```python
class_source = getattr(type(value), "__kajson_class_source__", None)
if class_source is not None:
    metadata["kajson_class_source"] = class_source.encode()
```

**Deserialize:**

```python
source_bytes = payload.metadata.get("kajson_class_source")
class_source_code = source_bytes.decode() if source_bytes else None
pydantic_gizmo = kajson.loads(
    data,
    class_registry=get_class_registry(),
    class_source_code=class_source_code,
)
# Re-attach source so it survives further hops
if class_source_code is not None and isinstance(pydantic_gizmo, BaseModel):
    type(pydantic_gizmo).__kajson_class_source__ = class_source_code
```

Re-attaching after `kajson.loads()` ensures the source survives if the object crosses another boundary (e.g. a worker returning a result to a parent that forwards it). The `__kajson_class_source__` attachment is open core; the converter that injects it into payload metadata is the host-runtime plugin's (Pipelex's Temporal backend realizes it as `BaseModelPayloadConverter`).

### The type bridge

The class reconstructed on the worker is a structural match to the original, but a different Python class in memory — so `isinstance()` checks would fail. The caller bridges the gap with a `model_validate` round-trip (`pipelex/cogt/content_generation/content_generator.py`):

```python
raw_obj = await llm_gen_object(object_assignment=object_assignment)
return object_class.model_validate(raw_obj.model_dump(serialize_as_any=True))
```

`model_dump(serialize_as_any=True)` produces a plain dict from the reconstructed object, and `model_validate()` rebuilds it as a proper instance of the original class, restoring type safety for downstream code.

### Structured web search reuses the same mechanism

Structured web search (`PipeSearch` with a non-text output concept) faces the identical dynamic-class problem and solves it the same way. `SearchObjectAssignment` mirrors `ObjectAssignment` — it ships `output_class_name` + `output_class_schema` alongside the `SearchAssignment`, the activity reconstructs a throwaway class to drive the provider call, and returns the **raw result dict**. The submitter re-validates that dict against the original output class (`output_structure_class.model_validate(result_dict)`) — a pure, deterministic step that keeps the dynamic class on the submitter side and never ships it across the boundary. The sourced-answer path (`make_search_sourced_answer`) has no dynamic class at all: it returns a `SearchResultContent`, a native serializable model.

---

## Large payload management

### The payload size constraint

A host runtime's payload has a practical size limit (Temporal's is around 2 MB). A single generated image can exceed it in base64; PDF extraction produces multiple page images. Sending raw binary through the runtime would fail conversion or degrade the run history.

### The store-then-reference pattern

Activities handle the full binary lifecycle internally — generate, store, return a lightweight reference. The storing is open-core: `GeneratedContentFactory` (`pipelex/cogt/content_generation/generated_content_factory.py`) uploads binary data via the configured `StorageProviderAbstract` (S3, local filesystem, …) and returns `ImageContent` or `PageContent` — Pydantic models carrying URIs, MIME types, and metadata, but never raw bytes. A host runtime's activity simply wraps that helper:

```python
async def generate_and_store_images(img_gen_assignment):
    """Large binary (base64/bytes) is stored inside the activity and never
    crosses the runtime boundary — only URLs come back."""
    factory = GeneratedContentFactory(storage_provider=get_storage_provider())
    return await img_gen_image_list_and_store(
        img_gen_assignment=img_gen_assignment,
        generated_content_factory=factory,
    )
```

!!! info "What crosses the boundary"
    `ImageContent` carries `url` (storage URI), `public_url`, `mime_type`, paired `width`/`height`, and `caption` — but never raw bytes. The `url` can be an S3 URI, HTTP URL, or local file path depending on storage configuration.

What gets stored vs. what crosses the boundary, by content type:

| Content type | What gets stored | What crosses the boundary |
|-------------|-----------------|----------------------------|
| Generated image | Base64/bytes → storage via `GeneratedContentFactory` | `list[ImageContent]` with URIs |
| Extracted pages | Extracted page images → storage | `list[PageContent]` with URI references |
| Rendered page views | PDF page renders → storage | `list[ImageContent]` with URIs |
| LLM text | Nothing (text is small) | Plain `str` |
| LLM object | Nothing (JSON is small) | `BaseModel` + `__kajson_class_source__` in metadata |
| Search sourced answer | Nothing (answer + source refs are small) | `SearchResultContent` (answer + `DocumentContent` sources) |
| Search structured | Nothing (JSON is small) | Raw `dict`, re-validated against the output class on the submitter |

Each host-runtime plugin dispatches these through its own activities and queue routing; for the Temporal realization (the `act_*` activity set, per-activity task queues), see the `pipelex-temporal` plugin's docs.

---

## Kajson class resolution

When `kajson.loads()` receives both a `class_registry` and `class_source_code`, the resolution follows a priority chain:

```python
if class_source_code is not None:
    source_registry = _build_registry_from_source(class_source_code)
    if class_registry is not None:
        # Source-derived classes fill gaps; explicit registry takes priority
        for name, cls in source_registry.root.items():
            if not class_registry.has_class(name):
                class_registry.register_class(cls, name=name, ...)
    else:
        class_registry = source_registry
```

Resolution order:

1. **Explicit `class_registry`** — the per-call scoped registry (see [Runtime Bridge & Transport](./runtime-bridge-and-transport.md#per-call-scoping))
2. **Source-derived classes** — from `class_source_code`, filling gaps in the explicit registry
3. **`sys.modules`** — already-imported classes
4. **Dynamic import** — last resort, importing the module path from `__module__` metadata

!!! note "exec() safety"
    `_build_registry_from_source()` uses `exec()` internally. The source code originates from `datamodel-code-generator` running against the same JSON schema the submitter used — it is never user-supplied arbitrary code.

---

## File Reference

| Component | File |
|-----------|------|
| Assignment models (schema embedding) | `pipelex/cogt/content_generation/assignment_models.py` |
| Schema-to-model reconstruction | `pipelex/cogt/content_generation/schema_to_model_factory.py` |
| Content generator (type bridge) | `pipelex/cogt/content_generation/content_generator.py` |
| LLM generation functions | `pipelex/cogt/content_generation/llm_generate.py` |
| Search generation functions | `pipelex/cogt/content_generation/search_generate.py` |
| Generated content factory (storage) | `pipelex/cogt/content_generation/generated_content_factory.py` |
| Kajson serialization | `kajson` (external PyPI package) |
| ImageContent model | `pipelex/core/stuffs/image_content.py` |
| PageContent model | `pipelex/core/stuffs/page_content.py` |

The host-runtime data converter and the `act_*` activities that carry these payloads are backend-specific and live in their plugin repos, not in open core.

---

## Next Steps

- [Runtime Bridge & Transport](./runtime-bridge-and-transport.md) — boundary DTOs, LibraryCrate propagation, deferred hydration, per-call scoping
- [Pipe Routing & Execution](./pipe-routing-and-execution.md) — how PipeJobs travel through the system
- [Architecture Overview](./architecture-overview.md) — the two-layer design and how components fit together
