"""Framework-agnostic web-search leaf, sibling of ``llm_generate``.

These coroutines are the single place a ``PipeSearch`` step's provider spend happens. They take a
serializable ``SearchAssignment`` / ``SearchObjectAssignment``, rebuild the ``SearchJob``, resolve the
worker from the model handle, and run it. The direct ``ContentGenerator`` calls them inline; the Temporal
``act_search_*`` activity calls them inside an activity so the result is recorded in workflow history and
any failure is converted to a terminal ``ApplicationError`` (instead of running inline on the workflow
loop, which left search failures hanging the submitter — see ``wip/`` brief).

The structured search has two entry points rather than one nullable parameter, because its two arms
genuinely return different things: in-process the caller's class travels down and an instance of it
comes back; at the boundary only the schema is available and the raw dict stays on the wire.
"""

from typing import Any

from pydantic import BaseModel

from pipelex.cogt.content_generation.assignment_models import SearchAssignment, SearchObjectAssignment
from pipelex.cogt.content_generation.dry_mock import (
    dry_search_gen_sourced_answer,
    dry_search_gen_structured,
    dry_search_gen_structured_object,
)
from pipelex.cogt.content_generation.object_class_resolution import resolve_search_output_class
from pipelex.cogt.content_generation.object_revalidation import revalidate_leaf_data
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.search.search_worker_factory import SearchWorkerFactory
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.runtime_hub import get_model_deck, get_report_delegate
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


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
    """Run a structured search at the *boundary*, returning the raw result dict.

    This is the arm a worker enters with only the serialized assignment in hand: no class can travel to
    it, so the output structure is rebuilt from the JSON schema, and the result stays a dict — which is
    what keeps a dynamic class off a distributed orchestrator's wire. The submitter re-validates that
    dict against the original class, a step that is pure and deterministic.

    In-process, call :func:`search_gen_structured_object` instead: the caller's real class is still on
    the stack, and handing it down is what keeps its validators and schema hints from being lost.
    """
    search_assignment = search_object_assignment.search_assignment
    if search_assignment.cogt_run_params.run_mode.is_dry:
        return dry_search_gen_structured(search_object_assignment)
    boundary_class = resolve_search_output_class(search_object_assignment=search_object_assignment, output_class=None)
    return await _run_structured_search(search_object_assignment, schema=boundary_class)


async def search_gen_structured_object(
    search_object_assignment: SearchObjectAssignment,
    *,
    output_class: type[BaseModelTypeVar],
) -> BaseModelTypeVar:
    """Run a structured search *in-process*, returning an instance of the caller's own output class.

    The class travels down to the provider unchanged, so the search is constrained by the schema the
    caller actually wrote — its custom validators are reflected in the hints and description the schema
    carries, rather than being erased by a JSON-schema rebuild.

    Returns an instance rather than a dict because the validation belongs here, next to the provider:
    doing it once at the leaf is what stops the caller's validators running a second time in the
    submitter. The two arms of this module therefore differ in return type on purpose — a dict is the
    wire's shape, an instance is the caller's.
    """
    search_assignment = search_object_assignment.search_assignment
    if search_assignment.cogt_run_params.run_mode.is_dry:
        return dry_search_gen_structured_object(search_object_assignment, output_class=output_class)
    result_dict = await _run_structured_search(search_object_assignment, schema=output_class)
    # ``is_mock_built=False`` is a statement, not a formality: this data came from the provider, so a
    # failure here is a malformed response and keeps its ``ValidationError`` — it is not the dry-run
    # schema-round-trip gap, which cannot arise on an arm that never rebuilt the class.
    return revalidate_leaf_data(result_dict, object_class=output_class, is_mock_built=False)


async def _run_structured_search(search_object_assignment: SearchObjectAssignment, *, schema: type[BaseModel]) -> dict[str, Any]:
    """Resolve the worker and run the provider call — the part both arms share."""
    search_assignment = search_object_assignment.search_assignment
    worker = _make_search_worker(search_assignment)
    search_job = _make_search_job(search_assignment)
    return await worker.search_structured(search_job=search_job, schema=schema)
