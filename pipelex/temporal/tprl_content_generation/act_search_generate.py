from typing import Any

from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import SearchAssignment, SearchObjectAssignment
from pipelex.cogt.content_generation.search_generate import search_gen_sourced_answer, search_gen_structured
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors


@activity.defn
@convert_pipelex_errors
async def act_search_gen_sourced_answer(search_assignment: SearchAssignment) -> SearchResultContent:
    log.dev("act_search_gen_sourced_answer")
    return await search_gen_sourced_answer(search_assignment=search_assignment)


@activity.defn
@convert_pipelex_errors
async def act_search_gen_structured(search_object_assignment: SearchObjectAssignment) -> dict[str, Any]:
    log.dev("act_search_gen_structured")
    return await search_gen_structured(search_object_assignment=search_object_assignment)
