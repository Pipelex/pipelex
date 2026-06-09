from typing import Any

from pydantic import BaseModel, ValidationError
from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import (
    ExtractAssignment,
    ImgGenAssignment,
    LLMAssignment,
    ObjectAssignment,
    RenderPageViewsAssignment,
    SearchAssignment,
    SearchObjectAssignment,
    TemplatingAssignment,
)
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.content_generation.exceptions import MockInferenceObjectFidelityError
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.config import get_config
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.exceptions import ContentGenerationError
from pipelex.temporal.tprl.observability import build_activity_summary
from pipelex.temporal.tprl.temporal_error import TemporalError
from pipelex.temporal.tprl_content_generation.act_extract_generate import act_extract_gen_extract_pages
from pipelex.temporal.tprl_content_generation.act_img_gen_generate import act_img_gen_images
from pipelex.temporal.tprl_content_generation.act_jinja2_generate import act_jinja2_gen_text
from pipelex.temporal.tprl_content_generation.act_llm_generate import (
    act_llm_gen_object,
    act_llm_gen_object_list,
    act_llm_gen_text,
)
from pipelex.temporal.tprl_content_generation.act_render_page_views import act_render_page_views
from pipelex.temporal.tprl_content_generation.act_search_generate import act_search_gen_sourced_answer, act_search_gen_structured
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


def _revalidate_against_object_class(
    raw_obj: BaseModel,
    object_class: type[BaseModelTypeVar],
    *,
    is_mock_inference: bool,
) -> BaseModelTypeVar:
    """Re-validate an activity-boundary object against the original ``object_class``.

    The Temporal arm of ``ContentGenerator._revalidate_against_object_class``: round-trips the
    activity-boundary ``BaseModel`` through json (``mode="json"`` is required for fields that need json-mode
    serialization to round-trip cleanly) into the caller's original concrete class (e.g. ``StructuredContent``).

    Under ``--mock-inference`` the object was built from the schema-reconstructed class inside
    ``act_llm_gen_object*``, which can drop invariants the original class enforces (custom validators,
    ``json_schema_extra`` format/pattern hints datamodel-code-generator omits on round-trip). That
    re-validation failure is re-raised as a clear :class:`MockInferenceObjectFidelityError` rather than an
    opaque pydantic crash mid-workflow (review F2). Scoped to the mock path only — a LIVE provider's invalid
    output keeps its existing ``ValidationError``.
    """
    raw_data = raw_obj.model_dump(mode="json", serialize_as_any=True)
    if not is_mock_inference:
        return object_class.model_validate(raw_data)
    try:
        return object_class.model_validate(raw_data)
    except ValidationError as exc:
        raise MockInferenceObjectFidelityError.for_object_class(object_class.__name__) from exc


class ContentGeneratorInWorkflow(ContentGeneratorProtocol):
    """ContentGenerator that dispatches each operation as a Temporal activity directly.

    The ``InWorkflow`` suffix signals the load-bearing constraint: every method calls
    ``workflow.execute_activity(...)``, which only works when invoked from inside a
    workflow's ``run()``. Calling these methods outside of a workflow context will fail.

    Activity IDs are never customized — the Temporal SDK assigns deterministic
    sequential integers per workflow run, which both guarantees uniqueness and
    is replay-safe by construction. Per-call meaning is carried in ``summary=``.
    """

    def __init__(self, generated_content_factory: GeneratedContentFactory) -> None:
        self._generated_content_factory = generated_content_factory

    @override
    @update_job_metadata
    async def make_llm_text(
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
    ) -> str:
        log.debug(f"ContentGeneratorInWorkflow make_llm_text: {llm_prompt_for_text}")
        log.verbose(f"llm_setting_main: {llm_setting_main}")
        worker_config = get_config().temporal.worker_config
        llm_assignment = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )
        log.verbose(llm_assignment.desc, title="llm_assignment")
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_llm_gen_text.__name__,
            routing_key=llm_assignment.llm_handle,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            generated_text: str = await workflow.execute_activity(
                act_llm_gen_text,
                arg=llm_assignment,
                summary=build_activity_summary("LLM text", job_metadata, extras={"model": llm_assignment.llm_handle}),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow generated text: {generated_text}")
        return generated_text

    @override
    @update_job_metadata
    async def make_object(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
    ) -> BaseModelTypeVar:
        log.verbose(f"ContentGeneratorInWorkflow make_object: {llm_prompt_for_object}")
        worker_config = get_config().temporal.worker_config
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object,
            llm_prompt=llm_prompt_for_object,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_llm_gen_object.__name__,
            routing_key=llm_assignment_for_object.llm_handle,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            obj: BaseModel = await workflow.execute_activity(
                act_llm_gen_object,
                arg=object_assignment,
                summary=build_activity_summary("LLM object", job_metadata, extras={"class": object_class.__name__}),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow generated object direct: {obj}")
        return _revalidate_against_object_class(obj, object_class, is_mock_inference=job_metadata.is_mock_inference)

    @override
    @update_job_metadata
    async def make_object_list(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
    ) -> list[BaseModelTypeVar]:
        worker_config = get_config().temporal.worker_config
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt=llm_prompt_for_object_list,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_llm_gen_object_list.__name__,
            routing_key=llm_assignment_for_object.llm_handle,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            obj_list: list[BaseModel] = await workflow.execute_activity(
                act_llm_gen_object_list,
                arg=object_assignment,
                summary=build_activity_summary("LLM object list", job_metadata, extras={"class": object_class.__name__}),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow generated object list direct: {obj_list}")
        return [_revalidate_against_object_class(raw_obj, object_class, is_mock_inference=job_metadata.is_mock_inference) for raw_obj in obj_list]

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

    @override
    @update_job_metadata
    async def make_single_image(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> ImageContent:
        worker_config = get_config().temporal.worker_config
        img_gen_config = get_config().cogt.img_gen_config
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=1,
        )
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_img_gen_images.__name__,
            routing_key=img_gen_assignment.img_gen_handle,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            image_content_list: list[ImageContent] = await workflow.execute_activity(
                act_img_gen_images,
                arg=img_gen_assignment,
                summary=build_activity_summary("Img gen 1×", job_metadata, extras={"model": img_gen_handle}),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        if len(image_content_list) != 1:
            msg = f"Expected 1 image, got {len(image_content_list)}"
            raise ContentGenerationError(msg)
        image_content = image_content_list[0]
        log.verbose(f"ContentGeneratorInWorkflow generated image: {image_content}")
        return image_content

    @override
    @update_job_metadata
    async def make_image_list(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        nb_images: int,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> list[ImageContent]:
        worker_config = get_config().temporal.worker_config
        img_gen_config = get_config().cogt.img_gen_config
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=nb_images,
        )
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_img_gen_images.__name__,
            routing_key=img_gen_assignment.img_gen_handle,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            image_content_list: list[ImageContent] = await workflow.execute_activity(
                act_img_gen_images,
                arg=img_gen_assignment,
                summary=build_activity_summary("Img gen N×", job_metadata, extras={"model": img_gen_handle, "n": str(nb_images)}),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow generated image list: {image_content_list}")
        return image_content_list

    @override
    @update_job_metadata
    async def make_templated_text(
        self,
        job_metadata: JobMetadata,
        context: dict[str, Any],
        template: str,
        templating_style: TemplatingStyle | None = None,
        template_category: TemplateCategory | None = None,
    ) -> str:
        worker_config = get_config().temporal.worker_config
        templating_assignment = TemplatingAssignment(
            job_metadata=job_metadata,
            context=context,
            template=template,
            templating_style=templating_style,
            category=template_category or TemplateCategory.BASIC,
        )
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_jinja2_gen_text.__name__,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            jinja2_text: str = await workflow.execute_activity(
                act_jinja2_gen_text,
                arg=templating_assignment,
                summary=build_activity_summary("Templated text", job_metadata),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow templated text: {jinja2_text}")
        return jinja2_text

    @override
    @update_job_metadata
    async def make_render_page_views(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
    ) -> list[ImageContent]:
        if not extract_input.document_uri:
            msg = "PDF URI is required to render page views"
            raise ValueError(msg)
        worker_config = get_config().temporal.worker_config
        job_params = extract_job_params or ExtractJobParams.make_default_extract_job_params()
        page_views_dpi = job_params.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi
        render_assignment = RenderPageViewsAssignment(
            job_metadata=job_metadata,
            document_uri=extract_input.document_uri,
            page_views_dpi=page_views_dpi,
        )
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_render_page_views.__name__,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            image_content_list: list[ImageContent] = await workflow.execute_activity(
                act_render_page_views,
                arg=render_assignment,
                summary=build_activity_summary("Render page views", job_metadata),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow rendered page views: {image_content_list}")
        return image_content_list

    @override
    @update_job_metadata
    async def make_extract_pages(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams,
        extract_job_config: ExtractJobConfig,
    ) -> list[PageContent]:
        worker_config = get_config().temporal.worker_config
        extract_assignment = ExtractAssignment(
            job_metadata=job_metadata,
            extract_handle=extract_handle,
            extract_input=extract_input,
            extract_job_params=extract_job_params,
            extract_job_config=extract_job_config,
        )
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_extract_gen_extract_pages.__name__,
            routing_key=extract_assignment.extract_handle,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            page_contents: list[PageContent] = await workflow.execute_activity(
                act_extract_gen_extract_pages,
                arg=extract_assignment,
                summary=build_activity_summary("Extract pages", job_metadata, extras={"handle": extract_handle}),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow generated page contents: {page_contents}")

        if extract_job_params.should_include_page_views:
            page_view_contents: list[ImageContent] = []
            if extract_input.document_uri:
                page_views_dpi = extract_job_params.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi
                render_assignment = RenderPageViewsAssignment(
                    job_metadata=job_metadata,
                    document_uri=extract_input.document_uri,
                    page_views_dpi=page_views_dpi,
                )
                render_dispatch_kwargs = worker_config.resolve_dispatch(
                    activity_name=act_render_page_views.__name__,
                    queue_options_by_queue=get_config().temporal.queue_options,
                    is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
                ).to_execute_kwargs()
                try:
                    page_view_contents = await workflow.execute_activity(
                        act_render_page_views,
                        arg=render_assignment,
                        summary=build_activity_summary("Render page views (extract)", job_metadata),
                        **render_dispatch_kwargs,
                    )
                except ActivityError as exc:
                    log.error(f"ActivityError caused by: {exc.cause}")
                    if isinstance(exc.cause, ApplicationError):
                        raise TemporalError.from_app_error(exc=exc.cause) from exc
                    raise
            elif extract_input.image_uri:
                page_view_contents = [ImageContent(url=extract_input.image_uri)]
            if len(page_view_contents) != len(page_contents):
                msg = f"Number of page view contents ({len(page_view_contents)}) does not match number of page contents ({len(page_contents)})"
                raise ContentGenerationError(msg)
            for page_content in page_contents:
                page_content.page_view = page_view_contents.pop(0)

        return page_contents

    @override
    async def make_search_sourced_answer(
        self,
        search_assignment: SearchAssignment,
    ) -> SearchResultContent:
        worker_config = get_config().temporal.worker_config
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_search_gen_sourced_answer.__name__,
            routing_key=search_assignment.search_handle,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            search_result: SearchResultContent = await workflow.execute_activity(
                act_search_gen_sourced_answer,
                arg=search_assignment,
                summary=build_activity_summary(
                    "Search sourced answer", search_assignment.job_metadata, extras={"model": search_assignment.search_handle}
                ),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow generated search result: {search_result}")
        return search_result

    @override
    async def make_search_structured(
        self,
        output_structure_class: type[BaseModelTypeVar],
        search_assignment: SearchAssignment,
    ) -> BaseModelTypeVar:
        worker_config = get_config().temporal.worker_config
        search_object_assignment = SearchObjectAssignment.make_for_class(
            output_class=output_structure_class,
            search_assignment=search_assignment,
        )
        dispatch_kwargs = worker_config.resolve_dispatch(
            activity_name=act_search_gen_structured.__name__,
            routing_key=search_assignment.search_handle,
            queue_options_by_queue=get_config().temporal.queue_options,
            is_traced=get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced,
        ).to_execute_kwargs()
        try:
            result_dict: dict[str, Any] = await workflow.execute_activity(
                act_search_gen_structured,
                arg=search_object_assignment,
                summary=build_activity_summary(
                    "Search structured", search_assignment.job_metadata, extras={"class": output_structure_class.__name__}
                ),
                **dispatch_kwargs,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        # Re-validate on the submitter (workflow) side against the original class — pure and
        # deterministic, so the dynamic output class never has to cross the activity boundary. The
        # activity returns the provider's raw dict unvalidated (e.g. the gateway worker returns
        # json.loads(...)), so a malformed structured response raises a bare ValidationError here in
        # workflow code. Left raw it is neither WorkflowExecutionError nor PipelexError, so Temporal
        # treats it as a workflow-task failure and retries forever, hanging the submitter — the exact
        # failure mode this seam exists to prevent. Convert it to a terminal ContentGenerationError (a
        # PipelexError) so the workflow fails and surfaces as an ErrorReport, matching the direct path.
        try:
            return output_structure_class.model_validate(result_dict)
        except ValidationError as exc:
            msg = f"Structured search result failed validation against {output_structure_class.__name__}: {exc}"
            raise ContentGenerationError(msg) from exc
