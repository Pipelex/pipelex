"""End-to-end coverage for signature-driven input shaping (Smart Inputs, Phase 2).

The seam is now live: a caller's *bare* values are interpreted top-down against the entry
pipe's declared signature. A bare string becomes the declared `Question` (not `native.Text`),
a bare number the declared `Priority`, a bare dict the declared `Invoice`, a list of bare
strings a `Tag[]`. The two failure modes the phase turns on — a wrong scalar kind (D4) and an
undeclared input name (D8) — surface as loud shaping errors.

All keyless (dry mode mocks only the cogt leaf and rides the live render + shaping path). The
`inputs` dicts are typed `dict[str, Any]` on purpose: the runtime admits the bare scalars the
narrow `PipelineInputs` alias does not (D10 widening is release-gated), which is exactly the
shape a real caller sends.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from pipelex.core.memory.exceptions import UnknownInputNameError, WrongScalarKindError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent

_FIXTURE_DIR = Path(__file__).parent / "smart_inputs_triage"


@pytest.mark.asyncio(loop_scope="class")
class TestSmartInputsDryRun:
    async def test_bare_values_shape_to_declared_concepts(self):
        """Bare string/number/dict/list inputs each carry the DECLARED concept, not native.Text."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        inputs: dict[str, Any] = {
            "question": "What are the late fees?",
            "priority": 3,
            "invoice": {"invoice_number": "INV-042", "amount": 1250.0},
            "tags": ["urgent", "billing"],
        }
        response = await runner.execute(pipe_code="triage_case", inputs=inputs)

        assert response.state == RunState.COMPLETED
        working_memory = response.pipe_output.working_memory

        question_stuff = working_memory.get_stuff("question")
        assert question_stuff.concept.concept_ref == "smart_inputs_demo.Question"
        assert isinstance(question_stuff.content, TextContent)
        assert question_stuff.content.text == "What are the late fees?"

        priority_stuff = working_memory.get_stuff("priority")
        assert priority_stuff.concept.concept_ref == "smart_inputs_demo.Priority"
        assert isinstance(priority_stuff.content, NumberContent)
        assert priority_stuff.content.number == 3

        invoice_stuff = working_memory.get_stuff("invoice")
        assert invoice_stuff.concept.concept_ref == "smart_inputs_demo.Invoice"
        assert isinstance(invoice_stuff.content, StructuredContent)
        assert invoice_stuff.content.model_dump() == {"invoice_number": "INV-042", "amount": 1250.0}

        tags_stuff = working_memory.get_stuff("tags")
        assert tags_stuff.concept.concept_ref == "smart_inputs_demo.Tag"
        tags_content: StuffContent = tags_stuff.content
        assert isinstance(tags_content, ListContent)
        tags_list = cast("ListContent[StuffContent]", tags_content)
        tag_items = [item.text for item in tags_list.items if isinstance(item, TextContent)]
        assert tag_items == ["urgent", "billing"]

    async def test_empty_list_input_builds_empty_list_content(self):
        """An empty list for a declared `Tag[]` input is legal: an empty ListContent, run completes."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        inputs: dict[str, Any] = {
            "question": "Any blockers?",
            "priority": 1,
            "invoice": {"invoice_number": "INV-000", "amount": 0.0},
            "tags": [],
        }
        response = await runner.execute(pipe_code="triage_case", inputs=inputs)

        assert response.state == RunState.COMPLETED
        tags_stuff = response.pipe_output.working_memory.get_stuff("tags")
        assert tags_stuff.concept.concept_ref == "smart_inputs_demo.Tag"
        tags_content: StuffContent = tags_stuff.content
        assert isinstance(tags_content, ListContent)
        tags_list = cast("ListContent[StuffContent]", tags_content)
        assert tags_list.items == []

    async def test_wrong_scalar_kind_raises_shaping_error(self):
        """A string for the Number-refining `priority` is a loud D4 shaping error naming the input."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        inputs: dict[str, Any] = {
            "question": "What are the late fees?",
            "priority": "high",
            "invoice": {"invoice_number": "INV-042", "amount": 1250.0},
            "tags": ["urgent"],
        }
        with pytest.raises(WrongScalarKindError, match="expects a number") as exc_info:
            await runner.execute(pipe_code="triage_case", inputs=inputs)
        message = str(exc_info.value)
        assert "'priority'" in message
        assert "Expected shape:" in message

    async def test_unknown_input_name_raises(self):
        """An undeclared input name (a typo) is a hard D8 error listing the declared names."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        inputs: dict[str, Any] = {
            "quesion": "typo'd input name",
            "priority": 3,
            "invoice": {"invoice_number": "INV-042", "amount": 1250.0},
            "tags": ["urgent"],
        }
        with pytest.raises(UnknownInputNameError, match="not declared") as exc_info:
            await runner.execute(pipe_code="triage_case", inputs=inputs)
        message = str(exc_info.value)
        assert "'quesion'" in message
        assert "'question'" in message
