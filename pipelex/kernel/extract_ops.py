"""Extract operator semantics: deck resolution, job-params assembly, extraction, memory write-back.

These are the functions the interpreter's `PipeExtract` calls, and the ones a programmatic caller
invokes on a `RuntimeBoot`-only process. They read the runtime hub for the services a runtime boot
stands up (the model deck, the content generator) and take everything else as an explicit argument.

One seam is deliberately *not* here: deciding **what** to extract. Turning a step's declared input into
an image or a document URI is a question about the memory's stuffs and the concepts they carry, which
is the caller's business; the kernel takes the `ExtractInput` already built.
"""

from typing import TYPE_CHECKING

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.kernel.extract_results import ExtractResult
from pipelex.kernel.memory_ops import store_result
from pipelex.runtime_hub import get_content_generator, get_model_deck
from pipelex.system.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.core.stuffs.page_content import PageContent


def resolve_extract_setting(*, extract_choice: ExtractModelChoice | None = None) -> ExtractSetting:
    """The deck chain for an extraction: the step's own choice, then the deck's default."""
    model_deck = get_model_deck()
    resolved_choice = extract_choice or model_deck.extract_choice_default
    return model_deck.get_extract_setting(extract_choice=resolved_choice)


def build_extract_job_params(
    *,
    extract_setting: ExtractSetting,
    should_caption_images: bool = False,
    should_include_page_views: bool = False,
    page_views_dpi: int | None = None,
    max_page_images: int | None = None,
    render_js: bool | None = None,
    include_raw_html: bool | None = None,
) -> ExtractJobParams:
    """Compose the per-job parameters from the resolved setting and the step's own one-time values.

    `max_page_images` is the one that composes rather than simply overriding-or-defaulting: a step
    that names it wins over the setting's `max_nb_images`, and `0` is a meaningful value (extract no
    images), so the precedence is written against `None` and not against falsiness. `image_min_size`
    has no step-level counterpart and always comes from the setting.
    """
    return ExtractJobParams(
        should_caption_images=should_caption_images,
        should_include_page_views=should_include_page_views,
        page_views_dpi=page_views_dpi,
        max_nb_images=max_page_images if max_page_images is not None else extract_setting.max_nb_images,
        image_min_size=extract_setting.image_min_size,
        render_js=render_js,
        include_raw_html=include_raw_html,
    )


async def run_extract(
    *,
    memory: WorkingMemory,
    extract_input: ExtractInput,
    extract_setting: ExtractSetting,
    extract_job_params: ExtractJobParams,
    concept: Concept,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    result_name: str | None = None,
    result_code: str | None = None,
) -> ExtractResult:
    """A whole extract step: extract the pages, store them as a list, report.

    The pages always land in memory as a `ListContent` — an extraction produces a page sequence even
    when the source is a single image — so there is no multiplicity fork here as there is on the LLM
    and image-generation paths.
    """
    page_contents = await get_content_generator().make_extract_pages(
        extract_input=extract_input,
        cogt_run_params=cogt_run_params,
        extract_handle=extract_setting.model,
        job_metadata=job_metadata,
        extract_job_params=extract_job_params,
        extract_job_config=ExtractJobConfig(),
    )
    content: ListContent[PageContent] = ListContent(items=page_contents)
    return ExtractResult(
        memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
        content=content,
        extract_setting=extract_setting,
    )
