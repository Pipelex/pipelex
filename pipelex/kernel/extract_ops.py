"""Extract operator semantics: deck resolution, job-params assembly, extraction, memory write-back.

These are the functions the interpreter's `PipeExtract` calls, and the ones a programmatic caller
invokes on a `RuntimeBoot`-only process. They read the runtime hub for the services a runtime boot
stands up (the model deck, the content generator) and take everything else as an explicit argument.

One seam is deliberately *not* here: deciding **what** to extract. Turning a step's declared input into
an image or a document URI is a question about the memory's stuffs and the concepts they carry, which
is the caller's business; the kernel takes the `ExtractInput` already built.
"""

from functools import partial
from typing import TYPE_CHECKING

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.exceptions import ExtractInputFormatError
from pipelex.cogt.extract.extract_input import PAGE_VIEWS_FILE_ADVICE, PAGE_VIEWS_FILE_OR_CONVERTER_ADVICE, PAGE_VIEWS_RENDERER, ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.models.model_deck import resolve_deck_choice
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.kernel.document_conversion_ops import readable_extract_input
from pipelex.kernel.extract_results import ExtractResult
from pipelex.kernel.memory_ops import store_result
from pipelex.runtime_hub import get_content_generator, get_model_deck
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.filetype_utils import PDF_FORMAT_KEY, describe_file_format, format_key_from_mime_type

if TYPE_CHECKING:
    from pipelex.core.stuffs.page_content import PageContent


def resolve_extract_setting(*, extract_choice: ExtractModelChoice | None = None) -> ExtractSetting:
    """The deck chain for an extraction: the step's own choice, then the deck's default.

    The step's choice that the deck does not resolve is the method's, `model.unknown`; the deck's default is the
    deployment's, `ModelDeckChoiceUnresolvedError`.
    """
    model_deck = get_model_deck()
    if extract_choice:
        return model_deck.get_extract_setting(extract_choice=extract_choice)
    return resolve_deck_choice(
        deck_setting="extract.choice_default", resolve=partial(model_deck.get_extract_setting, extract_choice=model_deck.extract_choice_default)
    )


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


def _refuse_page_views_of_a_known_non_pdf(*, extract_input: ExtractInput, extract_job_params: ExtractJobParams, converter_would_help: bool) -> None:
    """Refuse page views on a document known not to be a PDF, before the extraction is paid for.

    Run setup refuses what is certain before the run; this catches the rest, a step reached through a condition or a
    document a previous step produced. An unknown format is left to the renderer. An image is its own page view. An
    Office file reaches it when the runtime has no converter, `converter_would_help` then saying so in the advice, or
    when no model of the step reads PDFs, which a converter would not change.

    Raises:
        ExtractInputFormatError: If page views are asked of a document whose format is known and is not PDF.
    """
    if not extract_job_params.should_include_page_views or extract_input.document_uri is None:
        return
    format_key = format_key_from_mime_type(mime_type=extract_input.mime_type)
    if format_key is None or format_key == PDF_FORMAT_KEY:
        return
    subject = f"Input '{extract_input.input_name}' is" if extract_input.input_name else "The file to extract is"
    file_format = describe_file_format(format_key=format_key, mime_type=extract_input.mime_type)
    advice = PAGE_VIEWS_FILE_OR_CONVERTER_ADVICE if converter_would_help else PAGE_VIEWS_FILE_ADVICE
    msg = f"{subject} {file_format}, and page views are drawn from a PDF. {advice}"
    refusal = ExtractInputFormatError(msg).with_params(format=format_key, model=PAGE_VIEWS_RENDERER)
    if extract_input.input_name:
        refusal = refusal.with_params(input=extract_input.input_name)
    raise refusal


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
    with job_metadata.log_context():
        # An Office file the extraction's models may not all read, or whose page views are asked for, is read as its PDF
        # when the runtime converts documents: the page views and the extraction then read the same file.
        readable_input = await readable_extract_input(
            extract_input=extract_input,
            model_reference=extract_setting.model,
            asks_for_page_views=extract_job_params.should_include_page_views,
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
        )
        if not readable_input.reads_pdf:
            _refuse_page_views_of_a_known_non_pdf(
                extract_input=readable_input.extract_input,
                extract_job_params=extract_job_params,
                converter_would_help=readable_input.converter_would_help,
            )
        page_contents = await get_content_generator().make_extract_pages(
            extract_input=readable_input.extract_input,
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
