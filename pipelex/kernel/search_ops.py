"""Search operator semantics: deck resolution, query rendering, search, memory write-back.

These are the functions the interpreter's `PipeSearch` calls, and the ones a programmatic caller
invokes on a `RuntimeBoot`-only process. They read the runtime hub for the services a runtime boot
stands up (the model deck, the content generator) and take everything else as an explicit argument.

The sourced-answer / structured fork is the caller's, made explicit the way `llm_ops` makes the
text-vs-object fork explicit: pass `output_structure_class` and the search comes back structured onto
it, leave it out and it comes back as a sourced answer. Resolving a concept to that class is a
library's business, so the kernel never asks for one.
"""

from pipelex.cogt.content_generation.assignment_models import SearchAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_setting import SearchModelChoice, SearchSetting
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.kernel.memory_ops import store_result
from pipelex.kernel.search_results import SearchResult
from pipelex.runtime_hub import get_content_generator, get_model_deck
from pipelex.system.job_metadata import JobMetadata


def resolve_search_setting(
    *,
    search_choice: SearchModelChoice | None = None,
    include_images_override: bool | None = None,
    max_results_override: int | None = None,
) -> SearchSetting:
    """The deck chain for a search, then handle resolution, then the step's own overrides.

    The middle step is the one worth naming: the deck's setting may name a waterfall or an alias, and
    the returned setting is pinned to the *resolved* handle so it doubles as a distributed run's
    routing key. A caller that skipped it would route on a name no worker recognises.
    """
    model_deck = get_model_deck()
    resolved_choice = search_choice or model_deck.search_choice_default
    search_setting = model_deck.get_search_setting(search_choice=resolved_choice)

    inference_model = model_deck.get_required_inference_model(model_handle=search_setting.model, model_type=ModelType.SEARCH)
    if inference_model.name != search_setting.model:
        search_setting = search_setting.model_copy(update={"model": inference_model.name})

    if include_images_override is not None:
        search_setting = search_setting.model_copy(update={"include_images": include_images_override})
    if max_results_override is not None:
        search_setting = search_setting.model_copy(update={"max_results": max_results_override})
    return search_setting


async def run_search(
    *,
    memory: WorkingMemory,
    prompt_blueprint: TemplateBlueprint,
    search_setting: SearchSetting,
    concept: Concept,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    output_structure_class: type[StuffContent] | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    result_name: str | None = None,
    result_code: str | None = None,
) -> SearchResult:
    """A whole search step: render the query, search, store, report.

    The search itself goes through the same content-generation seam as the LLM, image-generation and
    extract leaves — direct inline, an activity when in-workflow, or a dry mock — which is what makes
    it replay-safe under a distributed orchestrator and lets its failures cross a workflow boundary as
    classified errors instead of hanging.
    """
    query_text = await render_template(
        template=prompt_blueprint.template,
        category=prompt_blueprint.category,
        context=memory.generate_context(),
    )
    search_assignment = SearchAssignment(
        job_metadata=job_metadata,
        cogt_run_params=cogt_run_params,
        query=query_text,
        search_setting=search_setting,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        from_date=from_date,
        to_date=to_date,
    )
    content_generator = get_content_generator()
    content: StuffContent
    if output_structure_class is None:
        content = await content_generator.make_search_sourced_answer(search_assignment=search_assignment)
    else:
        content = await content_generator.make_search_structured(
            output_structure_class=output_structure_class,
            search_assignment=search_assignment,
        )
    return SearchResult(
        memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
        content=content,
        rendered_query=query_text,
        search_setting=search_setting,
    )
