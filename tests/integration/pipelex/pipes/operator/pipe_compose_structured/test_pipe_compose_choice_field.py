from typing import Any
from uuid import uuid4

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import get_storage_provider
from tests.integration.pipelex.pipeline.cases import RunContentMarkerTestData

READ_SCOPE = "org_choices"


async def _level_input(*, level: str, is_stored: bool) -> dict[str, Any]:
    """The `level` input as the caller sends it: the text itself, or a URL to it in storage, unloaded until a step reads it."""
    if not is_stored:
        return {"level": level}
    level_url = await get_storage_provider().store(
        data=level.encode("utf-8"), key=f"{READ_SCOPE}/uploads/{uuid4().hex}/level.txt", content_type="text/plain; charset=utf-8"
    )
    return {"level": {"concept": "Text", "content": {"url": level_url}}}


async def _make_ticket(*, inputs: dict[str, Any]) -> dict[str, Any]:
    result = await PipelexMTHDSProtocol(storage_scope=f"{READ_SCOPE}/mt_ticket/run_{uuid4().hex}", read_scope=READ_SCOPE).execute(
        pipe_code="make_ticket", mthds_contents=[RunContentMarkerTestData.MTHDS], inputs=inputs
    )
    return result.pipe_output.main_stuff.content.model_dump()


@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeChoiceField:
    @pytest.mark.parametrize("is_stored", [False, True], ids=["inline", "stored"])
    @pytest.mark.parametrize("level", ["low", "high"])
    async def test_a_text_copied_into_a_choice_field_is_its_text(self, level: str, is_stored: bool) -> None:
        """A `choices` field is a choice among strings, so a Text copied into it fills it with its text, loaded when stored."""
        ticket = await _make_ticket(inputs=await _level_input(level=level, is_stored=is_stored))

        assert ticket == {"priority": level}

    @pytest.mark.parametrize("is_stored", [False, True], ids=["inline", "stored"])
    async def test_a_text_that_is_none_of_the_choices_is_refused_as_the_step_s_output(self, is_stored: bool) -> None:
        with pytest.raises(PipelexError) as exc_info:
            await _make_ticket(inputs=await _level_input(level="urgent", is_stored=is_stored))

        assert exc_info.value.to_problem(view=ProblemView.OPERATOR).code == CoreCode.PIPE_OUTPUT_INVALID
