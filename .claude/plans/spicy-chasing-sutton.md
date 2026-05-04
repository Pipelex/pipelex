# Plan: Fully align deep_flow content generators with ContentGeneratorProtocol

## Context

The `ContentGeneratorProtocol` (`pipelex/cogt/content_generation/content_generator_protocol.py`) evolved independently from the Temporal deep_flow implementations. The deep_flow files have broken references, wrong method names/signatures, missing methods, and wrong return types. The goal is full alignment — no `pyright: ignore[reportIncompatibleMethodOverride]` comments needed.

## Reference files (read-only)

- `pipelex/cogt/content_generation/content_generator_protocol.py` — the protocol to match
- `pipelex/cogt/content_generation/content_generator.py` — non-Temporal reference implementation
- `pipelex/cogt/content_generation/generated_content_factory.py` — `GeneratedContentFactory` for post-processing
- `pipelex/cogt/content_generation/assignment_models.py` — `TemplatingAssignment` model (fields: `context`, `template`, `templating_style`, `category`)
- `pipelex/cogt/templating/template_category.py` — `TemplateCategory` enum
- `pipelex/cogt/templating/templating_style.py` — `TemplatingStyle` model
- `pipelex/cogt/llm/llm_prompt_template.py` — `make_for_structuring_from_preliminary_text()` class method
- `pipelex/deep_flow/tprl/workflow_caller.py` — `WorkflowExecutor` base class

## Files to modify

1. `pipelex/cogt/content_generation/content_generator_protocol.py` — add `wfid` param to all applicable methods
2. `pipelex/cogt/content_generation/content_generator.py` — add `wfid` param (unused, for protocol compat)
3. `pipelex/deep_flow/tprl_content_generation/content_generator_child.py`
4. `pipelex/deep_flow/tprl_content_generation/content_generator_top.py`
5. `pipelex/deep_flow/tprl_content_generation/content_generator_child_factory.py`
6. `pipelex/deep_flow/tprl_content_generation/content_generator_top_factory.py`
7. `pipelex/deep_flow/tprl_content_generation/wf_make_extract.py` — rename class `WfMakeOcr` → `WfMakeExtract`

## Changes

### 1. Add `wfid` to `ContentGeneratorProtocol`

Add `wfid: str | None = None` as the last parameter to all methods that the deep_flow implementations use it with:
- `make_llm_text`
- `make_object_direct`
- `make_text_then_object`
- `make_object_list_direct`
- `make_text_then_object_list`
- `make_single_image`
- `make_image_list`
- `make_templated_text`
- `make_extract_pages`
- `make_render_page_views`

This keeps `wfid` optional (defaulting to `None`) so the non-Temporal `ContentGenerator` doesn't break.

### 2. Add `wfid` to non-Temporal `ContentGenerator`

Add `wfid: str | None = None` parameter to all the same methods in `content_generator.py`. The param is unused in the non-Temporal implementation but satisfies the protocol.

### 3. Rename `WfMakeOcr` → `WfMakeExtract` in `wf_make_extract.py`

The class is still named `WfMakeOcr` despite the file being renamed. Rename to `WfMakeExtract`. The `@workflow.defn(name="wf_make_extract")` string is already correct.

Update imports in `content_generator_child.py` and `content_generator_top.py`.

### 4. Add `generated_content_factory` to `ContentGeneratorChild`

Add `__init__` that accepts `generated_content_factory: GeneratedContentFactory` and stores it as `self._generated_content_factory`, calling `super().__init__(**kwargs)`.

`ContentGeneratorChild` inherits from `WorkflowExecutor` which has `__init__(self, temporal_client, should_auto_connect_temporal, worker_environment, **kwargs)` → `WorkflowCaller.__init__(self, task_queue, workflow_execution_timeout, ...)`. So the child class init should be:

```python
def __init__(self, generated_content_factory: GeneratedContentFactory, **kwargs: Any) -> None:
    super().__init__(**kwargs)
    self._generated_content_factory = generated_content_factory
```

### 5. Add `generated_content_factory` to `ContentGeneratorTop`

Same pattern as child.

### 6. Update factories to pass `generated_content_factory`

- `ContentGeneratorChildFactory.make_content_generator_child()` — add `generated_content_factory: GeneratedContentFactory` parameter and pass through
- `ContentGeneratorTopFactory.make_content_generator_top()` — add `generated_content_factory: GeneratedContentFactory` parameter and pass through

### 7. Rename `make_jinja2_text` → `make_templated_text` and align signature

In both child and top, rename and update signature to match protocol:

```python
@override
async def make_templated_text(
    self,
    context: dict[str, Any],
    template: str,
    templating_style: TemplatingStyle | None = None,
    template_category: TemplateCategory | None = None,
    wfid: str | None = None,
) -> str:
```

Update `TemplatingAssignment` construction:
```python
templating_assignment = TemplatingAssignment(
    context=context,
    template=template,
    templating_style=templating_style,
    category=template_category or TemplateCategory.BASIC,
)
```

Remove `PromptingTarget` import from both files. Add `TemplatingStyle` import. Remove `Jinja2TemplateCategory` references.

### 8. Rename `make_extract_extract_pages` → `make_extract_pages` and change return type

Change return type to `list[PageContent]`. After getting `ExtractOutput` from the workflow, call:
```python
return await self.make_page_contents(job_metadata=job_metadata, extract_output=extract_output)
```

Keep `extract_job_params` and `extract_job_config` as required params (matching protocol).

### 9. Change `make_single_image` return type to `ImageContent`

After getting `GeneratedImageRawDetails` from the workflow, convert:
```python
return await self.make_image_content(
    job_metadata=job_metadata,
    generated_image_raw_details=generated_image,
    img_gen_prompt=img_gen_prompt,
)
```

### 10. Change `make_image_list` return type to `list[ImageContent]`

After getting `list[GeneratedImageRawDetails]`, convert each:
```python
return [
    await self.make_image_content(
        job_metadata=job_metadata,
        generated_image_raw_details=raw_details,
        img_gen_prompt=img_gen_prompt,
    )
    for raw_details in generated_image_list
]
```

### 11. Add `make_image_content` method to both

Same implementation as non-Temporal `ContentGenerator`:
```python
@override
async def make_image_content(
    self,
    job_metadata: JobMetadata,
    generated_image_raw_details: GeneratedImageRawDetails,
    img_gen_prompt: ImgGenPrompt | None,
) -> ImageContent:
    image_content = await self._generated_content_factory.make_image_content(
        primary_id=job_metadata.user_id,
        secondary_id=job_metadata.pipeline_run_id,
        raw_details=generated_image_raw_details,
    )
    if img_gen_prompt:
        image_content.source_prompt = img_gen_prompt.positive_text
        image_content.source_negative_prompt = img_gen_prompt.negative_text
    return image_content
```

### 12. Add `make_page_contents` method to both

```python
@override
async def make_page_contents(
    self,
    job_metadata: JobMetadata,
    extract_output: ExtractOutput,
) -> list[PageContent]:
    return await self._generated_content_factory.make_page_contents(
        primary_id=job_metadata.user_id,
        secondary_id=job_metadata.pipeline_run_id,
        extract_output=extract_output,
    )
```

### 13. Add `make_render_page_views` method to both

Same as non-Temporal version, using `pypdfium2_renderer`:
```python
@override
async def make_render_page_views(
    self,
    job_metadata: JobMetadata,
    extract_input: ExtractInput,
    extract_handle: str,
    extract_job_params: ExtractJobParams | None = None,
    extract_job_config: ExtractJobConfig | None = None,
    wfid: str | None = None,
) -> list[ImageContent]:
    if not extract_input.document_uri:
        msg = "PDF URI is required to render page views"
        raise ValueError(msg)
    job_params = extract_job_params or ExtractJobParams.make_default_extract_job_params()
    page_views_dpi = job_params.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi
    page_view_images = await pypdfium2_renderer.render_pdf_pages_from_uri(
        pdf_uri=extract_input.document_uri, dpi=page_views_dpi
    )
    return [
        await self.make_image_content(
            job_metadata=job_metadata,
            generated_image_raw_details=GeneratedImageRawDetails.make_from_pil_image(
                pil_image=page_view_image,
                image_format=ImageFormat.PNG,
            ),
            img_gen_prompt=None,
        )
        for page_view_image in page_view_images
    ]
```

### 14. Fix `LLMPromptTemplate` method name in `content_generator_top.py`

Lines 138 and 217: `for_structure_from_preliminary_text()` → `make_for_structuring_from_preliminary_text()`

### 15. Remove all `pyright: ignore[reportIncompatibleMethodOverride]` comments

With full alignment, these are no longer needed.

### 16. Fix imports in both deep_flow files

**Add:**
- `from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory`
- `from pipelex.cogt.templating.templating_style import TemplatingStyle`
- `from pipelex.core.stuffs.image_content import ImageContent`
- `from pipelex.core.stuffs.page_content import PageContent`
- `from pipelex.tools.misc.image_utils import ImageFormat`
- `from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer`

**Remove:**
- `from pipelex.cogt.model_backends.prompting_target import PromptingTarget` (child)
- `from pipelex.tools.templating.templating_models import PromptingTarget` (top — wrong path anyway)

**Fix:**
- `WfMakeOcr` → `WfMakeExtract` in import from `wf_make_extract`

## Verification

Run `make agent-check` to verify no new lint/type errors are introduced.
