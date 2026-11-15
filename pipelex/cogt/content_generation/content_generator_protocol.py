from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment, SearchAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.cogt.doc_gen.document_composition import DocumentComposition
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.judgment.judgment_models import JudgmentOutcome
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.document_conversion.exceptions import DocumentConverterMisconfiguredError
from pipelex.tools.document_conversion.readable_pdf import ReadablePdf
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.tabular.exceptions import TableReaderMisconfiguredError
from pipelex.tools.tabular.table_records import TableRecords
from pipelex.tools.templating.templating_style import TemplatingStyle
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
P = ParamSpec("P")
R = TypeVar("R")


def update_job_metadata(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # Attempt to get job_metadata from kwargs or from args
        job_metadata = kwargs.get("job_metadata")
        if job_metadata is None:
            msg = "job_metadata argument is required for this decorated function."
            raise RuntimeError(msg)

        if not isinstance(job_metadata, JobMetadata):
            msg = "The job_metadata argument must be of type JobMetadata."
            raise TypeError(msg)

        job_metadata.content_generation_job_id = func.__name__

        return await func(*args, **kwargs)

    return wrapper


class ContentGeneratorProtocol(Protocol):
    """Content-generation seam between operators and the cogt leaves.

    Every leaf-dispatching method takes ``cogt_run_params`` (the cogt slice of the run params,
    sliced off ``PipeRunParams`` by the operator). Implementations stamp it onto the assignment
    they build, so the leaf sees the same ``run_mode`` on any backend — inline or inside a
    Temporal activity. The two search methods take a pre-built assignment instead; the operator
    stamps ``cogt_run_params`` at assignment construction.
    """

    def make_llm_text(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
    ) -> Coroutine[Any, Any, str]: ...

    def make_object(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
    ) -> Coroutine[Any, Any, BaseModelTypeVar]: ...

    def make_object_list(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
    ) -> Coroutine[Any, Any, list[BaseModelTypeVar]]: ...

    def make_single_image(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> Coroutine[Any, Any, ImageContent]: ...

    def make_image_list(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        nb_images: int,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> Coroutine[Any, Any, list[ImageContent]]: ...

    def make_templated_text(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        context: dict[str, Any],
        template: str,
        templating_style: TemplatingStyle | None = None,
        template_category: TemplateCategory | None = None,
    ) -> Coroutine[Any, Any, str]: ...

    def make_render_page_views(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
    ) -> Coroutine[Any, Any, list[ImageContent]]: ...

    def make_rendered_document(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        composition: DocumentComposition,
        doc_gen_setting: DocGenSetting,
    ) -> Coroutine[Any, Any, DocumentContent]:
        """Print a `PipeDocGen` step's composed document on the engine `doc_gen_setting` names and store it: the step's print stage."""
        ...

    def make_readable_pdf(
        self,
        *,
        job_metadata: JobMetadata,  # ruff: ignore[unused-method-argument] - the default refuses whatever it is given
        cogt_run_params: CogtRunParams,  # ruff: ignore[unused-method-argument]
        source_uri: str,  # ruff: ignore[unused-method-argument]
        format_key: str,  # ruff: ignore[unused-method-argument]
        input_name: str | None,  # ruff: ignore[unused-method-argument]
    ) -> Coroutine[Any, Any, ReadablePdf]:
        """The PDF a step reads in place of an Office file: the one kept beside it, or one converted and kept.

        A leaf operation, since it reads and writes storage and calls the converter: a host runtime's content generator
        dispatches it as it dispatches every other leaf. This body is what a content generator gets that does not
        implement it, a host runtime's included until it does: the step asked for a conversion its orchestrator cannot
        run, a fault of the deployment, which configured a converter its orchestrator cannot reach.

        Raises:
            DocumentConverterMisconfiguredError: This content generator does not convert documents.
        """
        msg = (
            f"The content generator '{type(self).__name__}' cannot convert Office files to PDF, and a document converter is configured: "
            "unset [runtime.document_conversion] backend, or run on an orchestrator whose content generator converts."
        )
        raise DocumentConverterMisconfiguredError(msg)

    def read_table(
        self,
        *,
        job_metadata: JobMetadata,  # ruff: ignore[unused-method-argument] - the default refuses whatever it is given
        cogt_run_params: CogtRunParams,  # ruff: ignore[unused-method-argument]
        source_uri: str,  # ruff: ignore[unused-method-argument]
        mime_type: str | None,  # ruff: ignore[unused-method-argument]
        file_name: str | None,  # ruff: ignore[unused-method-argument]
        input_name: str | None,  # ruff: ignore[unused-method-argument]
        field_names: list[str],  # ruff: ignore[unused-method-argument]
        row_field: str | None,  # ruff: ignore[unused-method-argument]
        table_name: str | None,  # ruff: ignore[unused-method-argument]
    ) -> Coroutine[Any, Any, TableRecords]:
        """The records a `PipeStructure` step reads from one table of a spreadsheet `Document`, as plain data.

        A leaf operation, since it reads storage: a host runtime's content generator dispatches it as it dispatches every
        other leaf, and returns the records, never the file's bytes. ``mime_type`` and ``file_name`` are the document's
        declarations, which judge its format when its bytes do not; ``field_names`` are the row concept's fields the
        columns match, ``row_field`` the one that receives each row's position, and ``table_name`` the Excel Table to
        read, ``None`` for the workbook's only one. This body is what a content generator gets that does not implement
        it, a host runtime's included until it does: the step asked for a read its orchestrator cannot run, a fault of
        the deployment, whose orchestrator plugin predates the read.

        Raises:
            TableReaderMisconfiguredError: This content generator does not read tables.
        """
        msg = (
            f"The content generator '{type(self).__name__}' cannot read a table from a document, which a PipeStructure step asked for: "
            "update the plugin providing the orchestrator, or run on an orchestrator whose content generator reads tables."
        )
        raise TableReaderMisconfiguredError(msg)

    def make_extract_pages(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams,
        extract_job_config: ExtractJobConfig,
    ) -> Coroutine[Any, Any, list[PageContent]]: ...

    def make_search_sourced_answer(
        self,
        search_assignment: SearchAssignment,
    ) -> Coroutine[Any, Any, SearchResultContent]: ...

    def make_search_structured(
        self,
        *,
        output_structure_class: type[BaseModelTypeVar],
        search_assignment: SearchAssignment,
    ) -> Coroutine[Any, Any, BaseModelTypeVar]: ...

    def make_judgment_answers(
        self,
        judgment_assignment: JudgmentAssignment,
    ) -> Coroutine[Any, Any, dict[str, JudgmentOutcome]]: ...
