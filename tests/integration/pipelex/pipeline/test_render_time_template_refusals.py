"""Pin: a template that names a filter its environment lacks, inside a branch, is refused at render as the method's fault.

Jinja2 compiles a filter or a test inside a branch to a lookup that only fails when the branch renders, and a prompt is
only parsed at load, so such a template passes the load and fails the run. The failure used to escape as a raw
`TemplateRuntimeError`, or as a `Jinja2TemplateRenderError` that is not the caller's fault, and a hosted run answered
500 "An internal error occurred.". It is now `method.template_invalid`: a located refusal naming the pipe, the
template's field and the filter Jinja2 refused, kept under STRICT disclosure, which never quotes the template's text.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipeline.test_data import RenderTimeTemplateTestData

_UNKNOWN_FILTER_FAULT = f"No filter named '{RenderTimeTemplateTestData.UNKNOWN_FILTER}' found."


def _llm_bundle(*, prompt_field: str) -> str:
    bundle = RenderTimeTemplateTestData.LLM_MTHDS.replace(RenderTimeTemplateTestData.PROMPT_FIELD_SLOT, prompt_field)
    if prompt_field == "system_prompt":
        bundle += RenderTimeTemplateTestData.PLAIN_PROMPT + "\n"
    return bundle


async def _failed_run(*, pipe_code: str, bundle: str, inputs: dict[str, Any], pipe_run_mode: PipeRunMode) -> PipelineExecutionError:
    with pytest.raises(PipelineExecutionError) as exc_info:
        await PipelexMTHDSProtocol(pipe_run_mode=pipe_run_mode).execute(pipe_code=pipe_code, mthds_contents=[bundle], inputs=inputs)
    return exc_info.value


def _assert_is_the_refusal(*, error: PipelineExecutionError, detail: str, next_step: str) -> None:
    report = error.to_error_report()
    assert report.code == CoreCode.METHOD_TEMPLATE_INVALID
    assert report.message == detail
    assert report.user_action is not None
    assert report.user_action.detail == next_step

    strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
    assert strict_payload["message"] == detail
    assert strict_payload["message"] != INTERNAL_ERROR_PLACEHOLDER
    assert strict_payload["user_action"] == {"kind": "change_input", "detail": next_step}
    document = report.to_problem_document(disclosure_mode=DisclosureMode.STRICT)
    assert document["status"] == 422
    assert document["detail"] == detail
    # Neither the template's text nor the branch it would have rendered reaches the caller.
    assert RenderTimeTemplateTestData.TEMPLATE_TEXT not in json.dumps(document)
    assert "{%" not in json.dumps(document)


@pytest.mark.asyncio(loop_scope="class")
class TestRenderTimeTemplateRefusals:
    async def test_a_condition_expression_naming_an_unknown_filter_in_a_branch_is_refused(self) -> None:
        """A live run taking the branch: `method.template_invalid` at the condition, its expression and the unknown filter named."""
        error = await _failed_run(
            pipe_code="route_parcel",
            bundle=RenderTimeTemplateTestData.CONDITION_MTHDS,
            inputs={"parcel": "a box of books", "lane": "express"},
            pipe_run_mode=PipeRunMode.LIVE,
        )

        _assert_is_the_refusal(
            error=error,
            detail=f"Pipe 'route_parcel' failed: PipeCondition 'route_parcel': its expression cannot render: {_UNKNOWN_FILTER_FAULT}",
            next_step=f"Fix the expression of PipeCondition 'route_parcel': {_UNKNOWN_FILTER_FAULT}",
        )

    @pytest.mark.parametrize("prompt_field", ["prompt", "system_prompt"])
    async def test_an_llm_prompt_naming_an_unknown_filter_in_a_branch_is_refused(self, prompt_field: str) -> None:
        """A dry run renders the prompt as a live run does: `method.template_invalid` naming the step, the prompt field and the filter."""
        error = await _failed_run(
            pipe_code="summarize",
            bundle=_llm_bundle(prompt_field=prompt_field),
            inputs={"topic": "the tides"},
            pipe_run_mode=PipeRunMode.DRY,
        )

        _assert_is_the_refusal(
            error=error,
            detail=f"Pipe 'summarize' failed: PipeLLM 'summarize': its {prompt_field} cannot render: {_UNKNOWN_FILTER_FAULT}",
            next_step=f"Fix the {prompt_field} of PipeLLM 'summarize': {_UNKNOWN_FILTER_FAULT}",
        )
