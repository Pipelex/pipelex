from typing import Any

from pydantic import BaseModel  # noqa: TC002
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
    TemplatingAssignment,
)
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
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
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.config_temporal import WorkerConfig
from pipelex.temporal.exceptions import ContentGenerationError
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
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


def _inference_dispatch_kwargs(worker_config: WorkerConfig) -> dict[str, Any]:
    """Provisional split-worker stopgap.

    Returns the ``execute_activity`` kwargs that route an inference activity
    onto ``worker_config.inference_task_queue`` so split-worker deployments
    can run inference on a dedicated runner pool. Today this helper is wired
    only at the ``make_llm_text`` dispatch site — ``act_llm_gen_object`` and
    ``act_llm_gen_object_list`` deliberately stay on the workflow's own queue
    because their cross-pool test coverage (registry decode of dynamic
    classes) has not been built yet (see
    ``wip/temporal-primitives/per-activity-queue-routing-v1.md`` §"Tests to
    upgrade when v1 lands"). All other activities (image-gen, extract, jinja2,
    render-page-views) are non-inference and route to the workflow's own
    queue.

    The proper general design is in
    ``wip/temporal-primitives/per-activity-queue-routing-v1.md``: per-
    activity, per-handle routing covering LLM + image-gen + extract under
    one config table. Do NOT extend this helper to image-gen, extract, or
    any other activity — those will be folded into the new routing system.
    This helper exists so the future migration is a single deletion point.
    """
    return {"task_queue": worker_config.inference_task_queue}


class ContentGeneratorInWorkflow(ContentGeneratorProtocol):
    """ContentGenerator that dispatches each operation as a Temporal activity directly.

    The ``InWorkflow`` suffix signals the load-bearing constraint: every method calls
    ``workflow.execute_activity(...)``, which only works when invoked from inside a
    workflow's ``run()``. Calling these methods outside of a workflow context will fail.
    """

    def __init__(self, generated_content_factory: GeneratedContentFactory) -> None:
        self._generated_content_factory = generated_content_factory
        # Per-run uniqueness invariant for activity_ids. Today no operator call site
        # invokes the same protocol method twice within one ``WfPipeRouter`` execution
        # (audit recorded in TODOS.md / collapse-content-generation-workflow-layer-v2.md
        # §0). This dict is a runtime guard so a future regression surfaces as a clear
        # ``ContentGenerationError`` instead of an opaque Temporal duplicate-activity-id
        # failure. Keyed by ``(workflow_id, run_id)`` so retries, ``continue_as_new``,
        # and id-reuse policies (which keep ``workflow_id`` but produce a new ``run_id``)
        # do not inherit the prior run's seen ids — that would raise spurious duplicates
        # on the new run's first default activity_id. The generator instance is set once
        # on the hub and reused across many workflow runs.
        # Replay-safety: ``_record_activity_id`` short-circuits during replay so a
        # cached set on this same worker process does not produce false-positive
        # duplicates after cache eviction. The dict otherwise grows unboundedly across
        # workflow runs — accepted for now; cleanup is a follow-up tracked in TODOS.md.
        self._seen_activity_ids: dict[tuple[str, str], set[str]] = {}

    def _record_activity_id(self, activity_id: str, method_name: str) -> None:
        # Skip the check on replay. After cache eviction, Temporal replays the
        # workflow code from history on the same worker process; the singleton
        # generator's set still holds entries from the original execution, so
        # checking would raise spurious "duplicate" errors. Trust history during
        # replay — duplicates can only be introduced on a fresh execution.
        if workflow.unsafe.is_replaying():
            return
        info = workflow.info()
        run_key = (info.workflow_id, info.run_id)
        seen = self._seen_activity_ids.setdefault(run_key, set())
        if activity_id in seen:
            msg = (
                f"Duplicate activity_id '{activity_id}' for method '{method_name}'. "
                "Activity ids must be unique within a single workflow execution; "
                "pass a distinct ``wfid`` at the call site to disambiguate repeated calls."
            )
            raise ContentGenerationError(msg)
        seen.add(activity_id)

    @override
    @update_job_metadata
    async def make_llm_text(
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        wfid: str | None = None,
    ) -> str:
        log.debug(f"ContentGeneratorInWorkflow make_llm_text: {llm_prompt_for_text}")
        log.verbose(f"llm_setting_main: {llm_setting_main}")
        worker_config = get_config().temporal.worker_config
        activity_id = wfid or "craft-text"
        self._record_activity_id(activity_id, "make_llm_text")
        llm_assignment = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )
        log.verbose(llm_assignment.desc, title="llm_assignment")
        try:
            # Asymmetric routing: LLM text dispatches to ``inference_task_queue`` so
            # split-worker deployments can run inference on a dedicated runner queue.
            # All other activities below run on the workflow's own queue (no
            # ``task_queue=`` kwarg passed) — copy-pasting that kwarg to img-gen,
            # extract, jinja2, etc. would break runners that don't register those
            # activities. ``_inference_dispatch_kwargs`` is the single deletion
            # point when per-activity-queue routing lands (see helper docstring).
            generated_text: str = await workflow.execute_activity(
                act_llm_gen_text,
                arg=llm_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                activity_id=activity_id,
                **_inference_dispatch_kwargs(worker_config),
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
        wfid: str | None = None,
    ) -> BaseModelTypeVar:
        log.verbose(f"ContentGeneratorInWorkflow make_object: {llm_prompt_for_object}")
        worker_config = get_config().temporal.worker_config
        activity_id = wfid or "craft-object-direct"
        self._record_activity_id(activity_id, "make_object")
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object,
            llm_prompt=llm_prompt_for_object,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        try:
            obj: BaseModel = await workflow.execute_activity(
                act_llm_gen_object,
                arg=object_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                activity_id=activity_id,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow generated object direct: {obj}")
        # Round-trip through json so the activity-boundary BaseModel becomes the caller's
        # original concrete class (e.g. StructuredContent). ``mode="json"`` is required
        # for fields that need json-mode serialization to round-trip cleanly.
        return object_class.model_validate(obj.model_dump(mode="json", serialize_as_any=True))

    @override
    @update_job_metadata
    async def make_object_list(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
        wfid: str | None = None,
    ) -> list[BaseModelTypeVar]:
        worker_config = get_config().temporal.worker_config
        activity_id = wfid or "craft-object-list-direct"
        self._record_activity_id(activity_id, "make_object_list")
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt=llm_prompt_for_object_list,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        try:
            obj_list: list[BaseModel] = await workflow.execute_activity(
                act_llm_gen_object_list,
                arg=object_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                activity_id=activity_id,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorInWorkflow generated object list direct: {obj_list}")
        return [object_class.model_validate(raw_obj.model_dump(mode="json", serialize_as_any=True)) for raw_obj in obj_list]

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
        wfid: str | None = None,
    ) -> ImageContent:
        worker_config = get_config().temporal.worker_config
        img_gen_config = get_config().cogt.img_gen_config
        activity_id = wfid or "craft-image-single"
        self._record_activity_id(activity_id, "make_single_image")
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=1,
        )
        try:
            image_content_list: list[ImageContent] = await workflow.execute_activity(
                act_img_gen_images,
                arg=img_gen_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                activity_id=activity_id,
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
        wfid: str | None = None,
    ) -> list[ImageContent]:
        worker_config = get_config().temporal.worker_config
        img_gen_config = get_config().cogt.img_gen_config
        activity_id = wfid or "craft-image-list"
        self._record_activity_id(activity_id, "make_image_list")
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=nb_images,
        )
        try:
            image_content_list: list[ImageContent] = await workflow.execute_activity(
                act_img_gen_images,
                arg=img_gen_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                activity_id=activity_id,
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
        wfid: str | None = None,
    ) -> str:
        worker_config = get_config().temporal.worker_config
        activity_id = wfid or "jinja2-text"
        self._record_activity_id(activity_id, "make_templated_text")
        templating_assignment = TemplatingAssignment(
            job_metadata=job_metadata,
            context=context,
            template=template,
            templating_style=templating_style,
            category=template_category or TemplateCategory.BASIC,
        )
        try:
            jinja2_text: str = await workflow.execute_activity(
                act_jinja2_gen_text,
                arg=templating_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                activity_id=activity_id,
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
        wfid: str | None = None,
    ) -> list[ImageContent]:
        if not extract_input.document_uri:
            msg = "PDF URI is required to render page views"
            raise ValueError(msg)
        worker_config = get_config().temporal.worker_config
        job_params = extract_job_params or ExtractJobParams.make_default_extract_job_params()
        page_views_dpi = job_params.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi
        activity_id = wfid or "render-page-views"
        self._record_activity_id(activity_id, "make_render_page_views")
        render_assignment = RenderPageViewsAssignment(
            job_metadata=job_metadata,
            document_uri=extract_input.document_uri,
            page_views_dpi=page_views_dpi,
        )
        try:
            image_content_list: list[ImageContent] = await workflow.execute_activity(
                act_render_page_views,
                arg=render_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                activity_id=activity_id,
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
        wfid: str | None = None,
    ) -> list[PageContent]:
        worker_config = get_config().temporal.worker_config
        base_id = wfid or "extract"
        extract_activity_id = f"{base_id}-pages"
        self._record_activity_id(extract_activity_id, "make_extract_pages")
        extract_assignment = ExtractAssignment(
            job_metadata=job_metadata,
            extract_handle=extract_handle,
            extract_input=extract_input,
            extract_job_params=extract_job_params,
            extract_job_config=extract_job_config,
        )
        try:
            page_contents: list[PageContent] = await workflow.execute_activity(
                act_extract_gen_extract_pages,
                arg=extract_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                activity_id=extract_activity_id,
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
                render_activity_id = f"{base_id}-render-page-views"
                self._record_activity_id(render_activity_id, "make_extract_pages")
                page_views_dpi = extract_job_params.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi
                render_assignment = RenderPageViewsAssignment(
                    job_metadata=job_metadata,
                    document_uri=extract_input.document_uri,
                    page_views_dpi=page_views_dpi,
                )
                try:
                    page_view_contents = await workflow.execute_activity(
                        act_render_page_views,
                        arg=render_assignment,
                        start_to_close_timeout=worker_config.workflow_execution_timeout,
                        retry_policy=worker_config.retry_policy,
                        activity_id=render_activity_id,
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
