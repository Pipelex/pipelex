# Activity-Level Storage: Fixing Non-Deterministic I/O in Temporal Workflows

> **Status**: Design
> **Date**: 2026-04-01
> **Related**: [phase5-payload-codec-strategy.md](phase5-payload-codec-strategy.md), Temporal img pipeline bug (fix/Temporal-Img branch)
> **Trigger**: `NotImplementedError` when running `test_image_out_in.mthds` through Temporal — aiohttp's connector cleanup calls `loop.is_closed()` on Temporal's sandboxed event loop

---

## 1. The Bug

When running an image-generation pipeline through Temporal, the workflow crashes at the S3 storage step:

```
wf_pipe_router.py:127  →  pipe_img_gen.py:214  →  content_generator_child.py:372
→  content_generator_child.py:306  →  generated_content_factory.py:113
→  s3_storage_provider.py:157  →  aiohttp connector close  →  NotImplementedError
```

`ContentGeneratorChild.make_image_content()` calls `GeneratedContentFactory.make_image_content()` directly within the workflow context. The factory does S3 storage via aiobotocore/aiohttp. aiohttp's cleanup calls `loop.is_closed()` on Temporal's restricted event loop, which doesn't implement that method.

**Root cause**: Non-deterministic I/O (S3 upload, HTTP fetch) executing inside a Temporal workflow instead of an activity.

---

## 2. Scope of the Problem

Three methods in `ContentGeneratorChild` perform I/O directly in workflow context:

| Method | Line | I/O performed | Called by |
|--------|------|---------------|-----------|
| `make_image_content` | 300-314 | S3 storage via factory | `make_single_image`, `make_image_list`, `make_render_page_views` |
| `make_page_contents` | 317-326 | S3 storage via factory (for each page image) | `make_extract_pages` |
| `make_render_page_views` | 462-490 | pypdfium2 PDF rendering + S3 storage via `make_image_content` | `make_extract_pages` |

All other content generation methods (LLM text, objects, image generation, extraction, templating) correctly delegate to child workflows that run activities.

---

## 3. Why a Separate Storage Activity is Not the Right Fix

The naive fix — create an activity that wraps the storage call — has two problems:

1. **Payload size limit**: Temporal enforces a **2MB limit per individual payload** (inputs and outputs of both activities and workflows). The current `act_img_gen_images` already returns `list[GeneratedImageRawDetails]` containing base64 image data. We already see `PayloadSizeWarning` at 1.8MB. Larger images would hard-fail. A separate storage activity would need to receive the same large data as input — hitting the same limit.

2. **Double history pollution**: The large image data would enter workflow history twice — once as the generation activity output, once as the storage activity input.

The Temporal-recommended "Large Data Handling" pattern (see `phase5-payload-codec-strategy.md` section "Large Data Handling" from the Temporal developer skill): activities should read AND write large data internally, passing only small references through the workflow.

---

## 4. The Solution: Merge Storage into Generation Activities

### 4.1 Core Principle

Each content generation activity becomes responsible for the full lifecycle: **generate → store → return lightweight reference**. Large binary data never crosses a Temporal boundary.

### 4.2 New Activity Signatures

**Image generation** (currently returns large `GeneratedImageRawDetails`):

```python
# BEFORE
@activity.defn
async def act_img_gen_images(img_gen_assignment: ImgGenAssignment) -> list[GeneratedImageRawDetails]:
    ...  # generate, return raw base64 data

# AFTER
@activity.defn
async def act_img_gen_images(img_gen_assignment: ImgGenAssignment) -> list[ImageContent]:
    ...  # generate, store to S3, return ImageContent with URLs
```

The activity internally:
1. Generates the image (existing logic)
2. Calls `GeneratedContentFactory.make_image_content()` to store and build `ImageContent`
3. Returns `ImageContent` (only URLs, no binary data)

**Extraction** (currently returns `ExtractOutput` which can contain large extracted images):

```python
# BEFORE
@activity.defn
async def act_extract_gen_extract_pages(extract_assignment: ExtractAssignment) -> ExtractOutput:
    ...  # extract, return raw extracted data with images

# AFTER
@activity.defn
async def act_extract_gen_extract_pages(extract_assignment: ExtractAssignment) -> list[PageContent]:
    ...  # extract, store images, return PageContent with URLs
```

**Page view rendering** (currently done entirely in workflow context):

```python
# NEW
@activity.defn
async def act_render_page_views(render_assignment: RenderPageViewsAssignment) -> list[ImageContent]:
    ...  # render PDF pages, store images, return ImageContent with URLs
```

### 4.3 Workflow Changes

**`WfMakeImages`**: Returns `list[ImageContent]` instead of `list[GeneratedImageRawDetails]`.

**`WfMakeExtract`**: Returns `list[PageContent]` instead of `ExtractOutput`.

**New `WfRenderPageViews`**: Wraps the new `act_render_page_views` activity.

### 4.4 ContentGeneratorChild Changes

`make_image_content` and `make_page_contents` become trivial or eliminated — the child workflows already return the final content types.

| Method | Before | After |
|--------|--------|-------|
| `make_single_image` | Calls `WfMakeImages` (returns raw details) → `make_image_content` (S3 I/O in workflow) | Calls `WfMakeImages` (returns `ImageContent`) → done |
| `make_image_list` | Same pattern as above | Same fix |
| `make_image_content` | Direct factory call with S3 I/O | No longer needed for Temporal path — storage happens in activity |
| `make_extract_pages` | Calls `WfMakeExtract` (returns `ExtractOutput`) → `make_page_contents` (S3 I/O in workflow) | Calls `WfMakeExtract` (returns `list[PageContent]`) → done |
| `make_page_contents` | Direct factory call with S3 I/O | No longer needed for Temporal path |
| `make_render_page_views` | pypdfium2 rendering + S3 I/O in workflow | Calls `WfRenderPageViews` → done |

### 4.5 Non-Temporal Path Unchanged

`ContentGenerator` (the non-Temporal implementation) continues to work as-is. The factory-level `make_image_content` and `make_page_contents` remain for the non-Temporal path. The change is only in the Temporal activities and `ContentGeneratorChild`.

---

## 5. New Assignment Models

The activities need assignment models that carry enough context for storage:

```python
class ImgGenAssignment(BaseModel):
    # existing fields...
    job_metadata: JobMetadata  # already has user_id, pipeline_run_id for storage keys
    img_gen_handle: str
    img_gen_prompt: ImgGenPrompt
    img_gen_job_params: ImgGenJobParams
    img_gen_job_config: ImgGenJobConfig
    nb_images: int
    # NO NEW FIELDS NEEDED — job_metadata already carries what storage needs
```

`ImgGenAssignment` already contains `job_metadata` (with `user_id` and `pipeline_run_id`) which the `GeneratedContentFactory` needs for building storage keys. No model changes required for image generation.

For page view rendering, a new assignment model:

```python
class RenderPageViewsAssignment(BaseModel):
    job_metadata: JobMetadata
    document_uri: str
    page_views_dpi: int
```

---

## 6. How the Activity Gets the Storage Provider

Activities run in the worker process, which has the full Pipelex runtime initialized. The activity can access storage via:

```python
from pipelex.hub import get_storage_provider

storage_provider = get_storage_provider()
generated_content_factory = GeneratedContentFactory(storage_provider=storage_provider)
```

This is already the pattern used by other worker-side code (`gateway_extract_worker.py`, `pypdfium2_worker.py`).

---

## 7. Impact on the `ContentGeneratorProtocol`

The protocol defines `make_image_content` and `make_page_contents` as public methods. After this change:

- **Non-Temporal** (`ContentGenerator`): Still uses them — no change.
- **Temporal** (`ContentGeneratorChild`): These methods are no longer called from workflow context. They could be removed from the child, or kept as pass-throughs.

**Decision**: Keep the protocol unchanged. The `ContentGeneratorChild` implementations of `make_image_content` and `make_page_contents` will still exist but won't be called from workflow code paths. They're kept for protocol compliance and in case they're called from non-workflow contexts in the future.

---

## 8. Relationship to PayloadCodec (Phase 5)

The PayloadCodec (`phase5-payload-codec-strategy.md`) is the general solution for large payload offloading — it transparently offloads any payload exceeding a size threshold to external storage at the wire boundary.

This design is complementary, not competing:

| Concern | This design | PayloadCodec |
|---------|-------------|--------------|
| Non-deterministic I/O in workflow | **Fixes** — moves I/O to activities | Does not fix — codec doesn't change where I/O happens |
| Large payloads through Temporal | **Fixes for images** — activities return URLs | **Fixes for everything** — transparent offloading |
| Required regardless of codec? | **Yes** — even with a codec, S3 I/O cannot run in workflow context | N/A |

Even after PayloadCodec is implemented, activities should still handle their own storage. The codec is a safety net for payloads that are unavoidably large (e.g., library contexts), not a substitute for proper activity design.

---

## 9. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Changing `WfMakeImages` return type breaks existing tests | High | Update test assertions; tests already use `InMemoryStorageProvider` |
| Extract output loss of detail (returning `PageContent` instead of `ExtractOutput`) | Medium | Ensure all needed fields from `ExtractOutput` are captured in `PageContent` |
| `make_render_page_views` in `ContentGeneratorChild` also uses pypdfium2 I/O | Known | Covered by the new `WfRenderPageViews` workflow |
| Storage provider not initialized in worker | Low | Worker init already sets up full Pipelex runtime; other activities use `get_storage_provider()` |
