# Content Generation Across Boundaries

This page is for contributors working on Pipelex internals. For the capability overview, see the user-facing [Distributed Execution](../distributed-execution/index.md) page instead.

When content generation (LLM structured output, image generation, PDF extraction, web search, judgment) runs on a separate worker process, two serialization problems appear that single-process execution never faces. This page covers them backend-neutrally — the mechanisms live in open core and are the same regardless of which host runtime carries the payload. The concrete activity dispatch is a [commercial platform capability](https://pipelex.com/products#durable-execution); each backend (Temporal, Mistral Workflows) realizes it in its own plugin.

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

Reconstruction is the *boundary* answer, and only that. An in-process run never walks it: `ContentGenerator` passes the caller's live class down beside the assignment, and `resolve_object_class` (`pipelex/cogt/content_generation/object_class_resolution.py`) uses it as-is. That matters because the rebuild is lossy — custom validators, `json_schema_extra` hints, and the output structure's own description do not survive the round trip — so in-process the provider would otherwise be constrained by a weaker contract than the author wrote, for no reason. On a worker there is no choice: the class genuinely cannot travel, so the rebuild below is the right answer there.

On the worker, `SchemaToModelFactory.make_from_json_schema(schema, *, class_name)` (`pipelex/cogt/content_generation/schema_to_model_factory.py`) rebuilds a live Pydantic class from the embedded schema:

```python
source_code = cls._generate_source_from_schema(schema)  # datamodel-code-generator
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

The class reconstructed on the worker is a structural match to the original, but a different Python class in memory — so `isinstance()` checks would fail. The caller bridges the gap with a `model_validate` round-trip, in `revalidate_leaf_object` (`pipelex/cogt/content_generation/object_revalidation.py`):

```python
if isinstance(raw_obj, object_class):
    return raw_obj
return object_class.model_validate(raw_obj.model_dump(mode=dump_mode, serialize_as_any=True, by_alias=True))
```

`model_dump(serialize_as_any=True)` produces a plain dict from the reconstructed object, and `model_validate()` rebuilds it as a proper instance of the original class, restoring type safety for downstream code.

`by_alias=True` is what keys that dict correctly. `model_json_schema()` emits **by alias**, so the schema's property names are what the original class accepts on the way back in — but the reconstructed class does not always name its fields that way. `datamodel-code-generator` renames any property that cannot be a field name (a python keyword, or a name shadowing a `BaseModel` attribute such as `json`, `copy`, `schema`, `construct`) and records the original as an alias. Dumping by field name would emit `construct_` for a field the original calls `construct`. Where nothing was renamed, the alias is the field name, so this is a no-op.

The short-circuit is what makes this a *boundary* conversion rather than a step on every path. In-process the leaf already worked from the caller's class, so the object is already one — note `isinstance`, not `type(...) is`: a provider library typically returns a *subclass* of the response model, not the class itself. Converting it anyway would run the caller's validators a second time on data they already normalized, which corrupts the output of any validator that transforms rather than merely rejects. A reconstructed class is never a subclass of the original, so the boundary path falls through to the conversion as before.

The helper is public so that both implementations of `ContentGeneratorProtocol` can share it — the in-process generator, which uses it today, and a host runtime's workflow arm, which still carries its own copy and adopts the shared one on its next release. The point of the single home is that the conversion, the short-circuit and the typed dry-run fidelity error stop being two copies that only agree until someone edits one. `dump_mode` is the one thing the two boundaries differ on: an object that crossed a payload boundary needs `mode="json"`, because some field types only round-trip cleanly through their json form.

### Structured web search reuses the same mechanism

Structured web search (`PipeSearch` with a non-text output concept) faces the identical dynamic-class problem and splits the same way, with one twist: the boundary arm must keep the *result* serializable too.

- **At the boundary**, `SearchObjectAssignment` mirrors `ObjectAssignment` — it ships `output_class_name` + `output_class_schema` alongside the `SearchAssignment`, the activity reconstructs a throwaway class to drive the provider call, and `search_gen_structured` returns the **raw result dict**. The submitter re-validates that dict against the original output class — a pure, deterministic step that keeps the dynamic class on the submitter side and never ships it across the boundary.
- **In-process**, `search_gen_structured_object` takes the caller's class, hands it to the provider unchanged, and returns an instance of it. The validation happens once, at the leaf, next to the provider. Returning the instance rather than a dump of it is what keeps it once: the search leaf has no object to short-circuit on if its result has already become a dict.

The sourced-answer path (`make_search_sourced_answer`) has no dynamic class at all: it returns a `SearchResultContent`, a native serializable model.

### Judgments need neither mechanism

A judgment's leaf, `judgment_gen_answers`, has one entry point where search has three, because nothing about it is dynamic. Its `JudgmentAssignment` carries the state as a JSON object, the image and document inputs as prompt files keyed by input name, which cross the boundary as an LLM prompt's files do, the questions as the family's own discriminated models and the resolved `JudgmentSetting`; its result is a map of answers that are plain models of the same package. No caller class travels down and no schema is shipped, so the in-process arm and the boundary arm would be the same function, and there is nothing to split.

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

Each object is stored under `{storage_scope}/generated/<filename>`, the filename rendered from the storage method's `uri_format` (`{hash}.{extension}` by default). The extension follows the MIME type the object is stored under, so the key and the stored content type always agree: `jpg` for `image/jpeg`, `svg` for `image/svg+xml`, and `bin` for a type with no extension of its own. A document a `PipeDocGen` step prints is stored under `{storage_scope}/generated/<hash>/<filename>` instead, so that every download carries its readable name, and that name is held to the grammar every `pipelex-storage://` reader accepts, the hosted platform's included: a stem of `[A-Za-z0-9_-]`, one dot and an alphanumeric extension (`path_safe_file_name` in `pipelex/tools/storage/storage_file_name.py`). A name holding a letter outside ASCII or an inner dot stores without complaint and is then refused by such a reader, so the file could never be downloaded.

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
| Judgment answers | Nothing (verdicts are small) | `dict[str, JudgmentAnswer]` keyed as the questions were |

The traffic also runs the other way, and no file of the method rides it. A run's `LibraryCrate` names the method tree each pipe's bundle belongs to by the tree's digest, and the bundle by its tree path (`TreeBundleRef`), and a `PipeDocGen` step names its template file the same way (`MethodFileRef`): the crate carries no file's bytes, no listing and no path of the host that assembled it. The bundles loaded from content strings sit at the root of the tree of the files submitted with them, a tree the library assembles in memory and names by digest like any other. A leaf that uses a method file reads it where IO is allowed, through one seam, the method file store (`MethodFileStoreProtocol` in `pipelex/core/method_trees/method_file_store.py`, read through `pipelex/core/method_trees/method_files.py`): it reads the tree's listing by the tree's digest, checks the listing against the digest, then reads each file it needs by its SHA-256, checks the bytes against the listing, and passes the run's read scope with every read. The runtime hub holds the store (`get_method_file_store`). Unclaimed, it is the local one, `LOCAL_METHOD_FILES`, which serves the trees this process's libraries hold while they hold them, from the disk they were listed from or from the bytes submitted with a request; a host whose activities run apart from the process that loaded the method claims `HubSlot.METHOD_FILE_STORE` for its own, such as a blob store the runner filled before it dispatched the run.

Two leaves read through it. The print stage of a `PipeDocGen` step reads its template file: the compose stage, which may run in a workflow, names the file in the step's `DocumentComposition`, with what an HTML template renders with (`TemplateRenderContext`): the stuffs the step's inputs name, the only ones its template may read, dumped for transport, the concepts and domains of the run's crate with none of its pipes, the crate's fingerprint, and the run's runtime parameters. The composition crosses into the print activity's payload, so it carries neither the run's pipes nor data the step does not read. The print renders it with the interpreter's template file stage (`pipelex/pipe_operators/doc_gen/template_file_stage.py`, installed on the runtime hub when the interpreter boots), which types the data again in the run's own library when this process holds it, and otherwise in a library loaded from the concepts alone, which the process keeps, by the concepts' fingerprint, for the prints that follow (`RenderLibraryCache`), then prints. At a dry print, the HTML template is rendered too, and an office template is handed to its engine's template checker, whose findings the stage reports. And an out-of-process `PipeFunc` call names its step's tree by digest (`PipeFuncExecutionRequest.tree_digest`), and whoever runs it reads the files of the tree but its bundles (`read_pipe_func_call_files`) and writes them where the function imports them. A run records both identities of the method it ran in its `RunMetadata`: the digest of the tree its pipe belongs to, which changes with any byte of the method, and the crate's fingerprint, which changes only with the meaning of its concepts and pipes.

Each host-runtime plugin dispatches these through its own activities and queue routing; for the Temporal realization (the `act_*` activity set, per-activity task queues), see our Temporal plugin's own docs.

### What a leaf may read: the read scope

A reference is only as safe as whoever reads it. A value can carry any URL its method chose — a `PipeCompose` construct that assembles one from plain text, a model's structured output, a function's result — and the next leaf reads it: a `pipelex-storage://` key with the process's own storage credentials, or a bare path or `file://` URI from the worker's disk. On a host serving many tenants that is a read of another tenant's file, so `RunMetadata` carries a second host-supplied prefix beside `storage_scope`: the **read scope**.

On a run whose read scope is set, a storage key is read only when it lies under the read scope, compared segment by segment, with no empty, `.` or `..` segment; a local path is never read; `https://` and `data:` URLs are untouched. The storage scope must lie under the read scope, since a run reads its own outputs back, and a mismatch is refused when the metadata is built. A run whose read scope is `None` (a laptop, a single-tenant server) reads exactly as before.

The check runs in the leaves, because both orchestration modes call the same leaves and every read of a value's URL happens while one of them handles an assignment. Each assignment declares the URLs it will read through `referenced_uris()` — the prompt's images and documents given by URI, an image generation's input images, the image or document to extract, the document to render as page views — and the leaf authorizes them as its first statement, before the dry-run branch and before any worker is built. A dry run therefore refuses the same method a live run would, and the check performs no IO. The input seam applies the same rule to what it reads itself: a table given as a CSV input, and a file the normalization would upload or link. A refused read raises `UriReadRefusedError`, answered as a 422 with the code `security.input_url_refused`, or `security.method_url_refused` where the reader knows the method named the URL, which names where the URL sat and never quotes it. A unit test walks every assignment model's fields for URL-shaped ones, so a new assignment or a new field that carries a URL fails until its `referenced_uris()` declares it.

The read scope leaves `https://` URLs alone because they are not the process's to scope: they are fetched over the network, and the network fetch has its own guard. Every leaf that needs the bytes behind a URL — prompt images and documents for a provider that does not take URLs, the document an extractor reads, the PDF rendered as page views, a generated image a provider returned as a link — goes through one fetch helper, and that helper connects through `SsrfGuardedTransport` unless `[runtime.network] is_fetch_ssrf_guard_enabled` is off. The transport resolves the host when each connection opens, on the first request and on every redirect hop to a new origin, refuses a name that resolves to any private, loopback, link-local or metadata address, and dials the address it vetted. A refusal raises `SsrfBlockedError`, a security error that no leaf's download fallback absorbs, so the pipe fails; its code is `security.input_url_refused` unless the reader knows the method or a provider's answer named the URL (`security.method_url_refused`, `security.provider_url_refused`). The guard connects directly and ignores `HTTP(S)_PROXY`; a deployment whose egress goes through a proxy, or that reads documents from an intranet host, turns the switch off, as the [network configuration](../configuration/config-technical/network-config.md) explains. Checking in the fetch helper rather than in input normalization is deliberate: a construct, a structured output or a function result can produce a URL as easily as an input can.

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
| Judgment generation function | `pipelex/cogt/content_generation/judgment_generate.py` |
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
