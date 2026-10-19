"""Pin: a template that names a filter its environment lacks, inside a branch, is refused at render as the method's fault.

Jinja2 compiles a filter or a test inside a branch to a lookup that only fails when the branch renders, and a prompt is
only parsed at load, so such a template passes the load and fails the run. The failure used to escape as a raw
`TemplateRuntimeError`, or as a `Jinja2TemplateRenderError` that is not the caller's fault, and a hosted run answered
500 "An internal error occurred.". It is now `method.template_invalid`: a located refusal naming the pipe, the
template's field and the filter Jinja2 refused for the operator, and the code's sentence for the caller, which never quotes
the template's text.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.problem.registry import CoreCode, StepKind

from pipelex.config import get_config
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipeline.test_data import RenderTimeTemplateTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

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


def _assert_is_the_refusal(*, error: PipelineExecutionError, message: str, detail: str, pipe_code: str) -> None:
    """The caller reads the code's sentence, located on the pipe; the refusal's own message is the operator's diagnostics."""
    caller = error.to_problem(view=ProblemView.CALLER)
    assert caller.code == CoreCode.METHOD_TEMPLATE_INVALID, caller.to_wire()
    assert caller.detail == detail, caller.to_wire()
    assert caller.location is not None
    assert caller.location.pipe == pipe_code
    assert caller.next_step.kind == StepKind.CHANGE_METHOD
    assert error_code_spec(CoreCode.METHOD_TEMPLATE_INVALID).status == 422
    operator = error.to_problem(view=ProblemView.OPERATOR)
    assert operator.diagnostics is not None
    assert operator.diagnostics.message == message
    # Neither the template's text nor the branch it would have rendered reaches the caller.
    caller_wire = json.dumps(caller.to_wire())
    assert RenderTimeTemplateTestData.TEMPLATE_TEXT not in caller_wire
    assert "{%" not in caller_wire


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
            message=f"PipeCondition 'route_parcel': its expression cannot render: {_UNKNOWN_FILTER_FAULT}",
            detail=f"The template 'expression' of pipe 'route_parcel' is invalid ({_UNKNOWN_FILTER_FAULT}).",
            pipe_code="route_parcel",
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
            message=f"PipeLLM 'summarize': its {prompt_field} cannot render: {_UNKNOWN_FILTER_FAULT}",
            detail=f"The template '{prompt_field}' of pipe 'summarize' is invalid ({_UNKNOWN_FILTER_FAULT}).",
            pipe_code="summarize",
        )

    async def test_a_broken_deployment_structure_prompt_is_ours_and_withheld(self, mocker: MockerFixture) -> None:
        """The structure prompt is the deployment's template, rendered in the step: `runtime.unexpected`, a 500 whose message is the operator's."""
        mocker.patch.dict(
            get_config().inference.llm.generic_templates,
            {"output_structure_prompt": RenderTimeTemplateTestData.BROKEN_STRUCTURE_PROMPT},
        )

        error = await _failed_run(
            pipe_code="read_label",
            bundle=RenderTimeTemplateTestData.STRUCTURED_LLM_MTHDS,
            inputs={"note": "To Ada, third floor"},
            pipe_run_mode=PipeRunMode.DRY,
        )

        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.RUNTIME_UNEXPECTED
        assert caller.diagnostics is None
        assert error_code_spec(CoreCode.RUNTIME_UNEXPECTED).status == 500
        # Neither the deployment's template nor what Jinja2 refused in it reaches the caller.
        assert RenderTimeTemplateTestData.UNKNOWN_STRUCTURE_FILTER not in json.dumps(caller.to_wire())
        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        diagnosed_classes = {operator.diagnostics.error_class, *(cause.error_class for cause in operator.diagnostics.causes or [])}
        assert "Jinja2TemplateInvalidError" in diagnosed_classes
