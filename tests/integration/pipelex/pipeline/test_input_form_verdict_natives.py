"""`YesNo` is read by position: a `boolean` where a caller supplies it, an `object` where a producer reports it.

`Choice` and `Rating` are objects on both sides, with their pinned fields. The position is set once by
`build_input_form` and `build_output_form` and read in `YesNo`'s row alone, so these tests reach a
`YesNo` at every depth on each side: at the top, as a list's item, as a nested structure field, through
a refinement, and through a reflected class field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from kajson.kajson_manager import KajsonManager
from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.pipeline.input_form import FieldKind, InputFormField, InputFormItem, ObjectField, ObjectItem, build_input_form, build_output_form
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.helpers.input_form import as_list, fields_by_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from mthds.protocol.output_form import PipeOutputFormDescriptor

    from pipelex.pipeline.input_form import PipeInputFormDescriptor


def _teardown_validation_library(outer_library_id: str) -> None:
    """Tear down the library `validate_bundle` left open on success, restoring the outer one."""
    validation_library_id = get_current_library_id_or_none()
    if validation_library_id is not None and validation_library_id != outer_library_id:
        set_current_library(library_id=outer_library_id)
        get_library_manager().teardown(library_id=validation_library_id)
    clear_current_library()


def _field_by_name(descriptor: PipeInputFormDescriptor, name: str) -> InputFormField:
    by_name = {field.name: field for field in descriptor.fields}
    assert name in by_name, f"Expected a field named {name!r}, got {sorted(by_name)}"
    return by_name[name]


class InputFormVerdictPayload(StructuredContent):
    """A registered structure class holding a `YesNo` field, reached by reflection rather than by a structure table."""

    approved: YesNoContent = Field(description="PROBE_desc_reflected_approved")


_VERDICTS_MTHDS = """
domain = "verdict_forms"
description = "The verdict natives on both sides of a pipe, at every depth"

[concept.Assessment]
description = "An assessment carrying verdicts as fields"

[concept.Assessment.structure]
urgent = { type = "concept", concept_ref = "native.YesNo", description = "Whether it is urgent", required = true }
flags = { type = "list", item_type = "concept", item_concept_ref = "native.YesNo", description = "One verdict per flag" }

[concept.Escalation]
description = "Whether to escalate"
refines = "YesNo"

[concept.Reviewed]
description = "A class-backed concept whose class holds a verdict"
structure = "InputFormVerdictPayload"

[concept.Team]
description = "The team a message is routed to"
refines = "Choice"

[pipe.verdicts_in]
type = "PipeCompose"
description = "Every verdict native as an input"
output = "Text"
template = "$answer $answers $team $grade $assessment $escalation $reviewed"

[pipe.verdicts_in.inputs]
answer = "YesNo"
answers = "YesNo[]"
team = "Choice"
grade = "Rating"
assessment = "Assessment"
escalation = "Escalation"
reviewed = "Reviewed"

[pipe.yes_no_out]
type = "PipeLLM"
description = "A yes/no answer"
output = "YesNo"
prompt = "Is it raining?"

[pipe.yes_no_list_out]
type = "PipeLLM"
description = "Several yes/no answers"
output = "YesNo[]"
prompt = "Is it raining, and is it cold?"

[pipe.assessment_out]
type = "PipeLLM"
description = "An assessment"
output = "Assessment"
prompt = "Assess it."

[pipe.escalation_out]
type = "PipeLLM"
description = "Whether to escalate"
output = "Escalation"
prompt = "Escalate?"

[pipe.reviewed_out]
type = "PipeLLM"
description = "A review"
output = "Reviewed"
prompt = "Review it."

[pipe.choice_out]
type = "PipeLLM"
description = "A team"
output = "Team"
prompt = "Pick a team."

[pipe.rating_out]
type = "PipeLLM"
description = "A grade"
output = "Rating"
prompt = "Grade it."
"""


def _assert_yes_no_object(node: InputFormField | InputFormItem) -> None:
    """The output-side `YesNo`: an object with the verdict required and the probability optional."""
    assert isinstance(node, (ObjectField, ObjectItem)), f"Expected an object node, got {node.kind!r}"
    fields = {field.name: field for field in node.fields}
    assert list(fields) == ["yes_no", "probability"], "Pinned-blueprint fields, in pinned order"
    assert fields["yes_no"].kind == FieldKind.BOOLEAN
    assert fields["yes_no"].required is True
    assert fields["probability"].kind == FieldKind.NUMBER
    assert fields["probability"].required is False


@pytest.mark.asyncio(loop_scope="class")
class TestVerdictNativesByPosition:
    """`YesNo` is a `boolean` where a caller supplies it and an `object` where a producer reports it.

    `Choice` and `Rating` are objects on both sides.
    """

    async def _derive(self, load_empty_library: Callable[[], str]) -> tuple[dict[str, PipeInputFormDescriptor], dict[str, PipeOutputFormDescriptor]]:
        outer_library_id = load_empty_library()
        registry = KajsonManager.get_class_registry()
        try:
            registry.register_class(InputFormVerdictPayload)
            result = await validate_bundle(mthds_contents=[_VERDICTS_MTHDS])
            return build_input_form(result.pipes), build_output_form(result.pipes)
        finally:
            registry.unregister_class(InputFormVerdictPayload)
            _teardown_validation_library(outer_library_id)

    async def test_a_yes_no_input_is_a_boolean_at_every_depth(self, load_empty_library: Callable[[], str]) -> None:
        input_form, _ = await self._derive(load_empty_library)
        verdicts = input_form["verdict_forms.verdicts_in"]
        assert _field_by_name(verdicts, "answer").kind == FieldKind.BOOLEAN
        assert as_list(_field_by_name(verdicts, "answers")).item.kind == FieldKind.BOOLEAN
        escalation = _field_by_name(verdicts, "escalation")
        assert escalation.kind == FieldKind.BOOLEAN, "A concept refining YesNo reads as YesNo"
        assert escalation.refines == ["native.YesNo"]
        assessment = fields_by_name(_field_by_name(verdicts, "assessment"))
        assert assessment["urgent"].kind == FieldKind.BOOLEAN
        assert as_list(assessment["flags"]).item.kind == FieldKind.BOOLEAN
        assert fields_by_name(_field_by_name(verdicts, "reviewed"))["approved"].kind == FieldKind.BOOLEAN

    async def test_a_yes_no_output_is_an_object_at_every_depth(self, load_empty_library: Callable[[], str]) -> None:
        _, output_form = await self._derive(load_empty_library)
        _assert_yes_no_object(output_form["verdict_forms.yes_no_out"].field)
        _assert_yes_no_object(as_list(output_form["verdict_forms.yes_no_list_out"].field).item)
        escalation = output_form["verdict_forms.escalation_out"].field
        _assert_yes_no_object(escalation)
        assert escalation.refines == ["native.YesNo"]
        assessment = fields_by_name(output_form["verdict_forms.assessment_out"].field)
        _assert_yes_no_object(assessment["urgent"])
        _assert_yes_no_object(as_list(assessment["flags"]).item)
        _assert_yes_no_object(fields_by_name(output_form["verdict_forms.reviewed_out"].field)["approved"])

    async def test_choice_and_rating_are_objects_on_both_sides(self, load_empty_library: Callable[[], str]) -> None:
        input_form, output_form = await self._derive(load_empty_library)
        verdicts = input_form["verdict_forms.verdicts_in"]
        for team in (_field_by_name(verdicts, "team"), output_form["verdict_forms.choice_out"].field):
            assert team.kind == FieldKind.OBJECT
            team_fields = fields_by_name(team)
            assert list(team_fields) == ["choice", "confidence", "probabilities"], "Pinned-blueprint fields, in pinned order"
            assert team_fields["choice"].kind == FieldKind.TEXT
            assert team_fields["choice"].required is True
            assert team_fields["confidence"].kind == FieldKind.NUMBER
            assert team_fields["confidence"].required is False
            assert team_fields["probabilities"].kind == FieldKind.UNKNOWN, "A dict field has no form kind"
        assert output_form["verdict_forms.choice_out"].field.refines == ["native.Choice"]
        for grade in (_field_by_name(verdicts, "grade"), output_form["verdict_forms.rating_out"].field):
            assert grade.kind == FieldKind.OBJECT
            grade_fields = fields_by_name(grade)
            assert list(grade_fields) == ["level", "confidence", "probabilities", "position"], "Pinned-blueprint fields, in pinned order"
            assert grade_fields["level"].kind == FieldKind.NUMBER
            assert grade_fields["level"].integer is True
            assert grade_fields["level"].required is True
            assert grade_fields["position"].required is False
