"""Framework-agnostic web-search leaf, sibling of ``llm_generate``.

These coroutines are the single place a ``PipeSearch`` step's provider spend happens. They take a
serializable ``SearchAssignment`` / ``SearchObjectAssignment``, rebuild the ``SearchJob``, resolve the
worker from the model handle, and run it. The direct ``ContentGenerator`` calls them inline; the Temporal
``act_search_*`` activity calls them inside an activity so the result is recorded in workflow history and
any failure is converted to a terminal ``ApplicationError`` (instead of running inline on the workflow
loop, which left search failures hanging the submitter — see ``wip/`` brief).
"""

from typing import Any

from pipelex.cogt.content_generation.assignment_models import SearchAssignment, SearchObjectAssignment
from pipelex.cogt.content_generation.dry_mock import dry_search_gen_sourced_answer, dry_search_gen_structured
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.search.search_worker_factory import SearchWorkerFactory
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.runtime_hub import get_model_deck, get_report_delegate


def _make_search_worker(search_assignment: SearchAssignment) -> SearchWorkerAbstract:
    model_deck = get_model_deck()
    inference_model = model_deck.get_required_inference_model(
        model_handle=search_assignment.search_setting.model,
        model_type=ModelType.SEARCH,
    )
    return SearchWorkerFactory.make_search_worker(inference_model=inference_model, reporting_delegate=get_report_delegate())


def _make_search_job(search_assignment: SearchAssignment) -> SearchJob:
    return SearchJobFactory.make_search_job(
        query=search_assignment.query,
        search_setting=search_assignment.search_setting,
        job_metadata=search_assignment.job_metadata,
        include_domains=search_assignment.include_domains,
        exclude_domains=search_assignment.exclude_domains,
        from_date=search_assignment.from_date,
        to_date=search_assignment.to_date,
    )


async def search_gen_sourced_answer(search_assignment: SearchAssignment) -> SearchResultContent:
    if search_assignment.cogt_run_params.run_mode.is_dry:
        return dry_search_gen_sourced_answer(search_assignment)
    worker = _make_search_worker(search_assignment)
    search_job = _make_search_job(search_assignment)
    return await worker.search_sourced_answer(search_job=search_job)


async def search_gen_structured(search_object_assignment: SearchObjectAssignment) -> dict[str, Any]:
    """Run a structured search, returning the raw result dict.

    The dict is re-validated against the original output structure class by the submitter
    (``ContentGenerator`` / ``ContentGeneratorInWorkflow``) — that step is pure and deterministic,
    which sidesteps shipping a dynamic output class across the Temporal boundary.
    """
    search_assignment = search_object_assignment.search_assignment
    if search_assignment.cogt_run_params.run_mode.is_dry:
        return dry_search_gen_structured(search_object_assignment)
    worker = _make_search_worker(search_assignment)
    search_job = _make_search_job(search_assignment)
    output_class = SchemaToModelFactory.make_from_json_schema(
        schema=search_object_assignment.output_class_schema,
        class_name=search_object_assignment.output_class_name,
    )
    return await worker.search_structured(search_job=search_job, schema=output_class)
