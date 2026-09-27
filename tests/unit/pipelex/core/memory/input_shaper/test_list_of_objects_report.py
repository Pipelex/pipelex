"""The report that widened this arm: a list of plain JSON objects sent to an input slot.

It hit the bottom-up fallback's `Cannot create Stuff from list of <class 'dict'>` without naming the
slot. Every declaration below now either takes the list or refuses it with a typed input error, so
a `StuffFactoryError` can never again reach a caller from a bare value.
"""

from typing import Any

import pytest

from pipelex.core.memory.exceptions import InputShapingError, ListWhereSingularError, StructureValidationError, WrongScalarKindError
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import ShaperRecord, build_input_specs

LIST_OF_OBJECTS: list[dict[str, Any]] = [{"a": 1}, {"b": 2}]

# (concept_ref, multiplicity, expected: the content it shapes into, or the error class it raises)
REPORT_CASES: list[tuple[str, VariableMultiplicity | None, StuffContent | type[InputShapingError]]] = [
    ("native.Anything", True, ListContent(items=[JSONContent(json_obj={"a": 1}), JSONContent(json_obj={"b": 2})])),
    ("native.JSON", True, ListContent(items=[JSONContent(json_obj={"a": 1}), JSONContent(json_obj={"b": 2})])),
    ("shaper_test.ShaperRecord", True, ListContent(items=[ShaperRecord(a=1), ShaperRecord(b=2)])),
    ("native.Anything", None, ListWhereSingularError),
    ("native.JSON", None, ListWhereSingularError),
    ("shaper_test.ShaperRecord", None, ListWhereSingularError),
    ("native.Text", None, ListWhereSingularError),
    ("native.Text", True, WrongScalarKindError),
    ("native.Number", True, WrongScalarKindError),
    ("native.YesNo", True, WrongScalarKindError),
    ("native.Date", True, WrongScalarKindError),
    ("native.Time", True, WrongScalarKindError),
    ("native.Image", True, StructureValidationError),
    ("native.Document", True, StructureValidationError),
    ("native.Dynamic", None, StructureValidationError),
    ("native.Dynamic", True, StructureValidationError),
    ("native.Composite", None, StructureValidationError),
    ("native.Composite", True, StructureValidationError),
    ("native.Html", None, StructureValidationError),
    ("native.Html", True, StructureValidationError),
    ("native.TextAndImages", None, StructureValidationError),
    ("native.TextAndImages", True, StructureValidationError),
    ("native.SearchResult", None, StructureValidationError),
    ("native.SearchResult", True, StructureValidationError),
    ("native.Page", None, StructureValidationError),
    ("native.Page", True, StructureValidationError),
]


class TestListOfObjectsReport:
    @pytest.mark.parametrize(("concept_ref", "multiplicity", "expected"), REPORT_CASES)
    def test_a_list_of_plain_objects_is_taken_or_refused_by_name(
        self,
        concept_ref: str,
        multiplicity: VariableMultiplicity | None,
        expected: StuffContent | type[InputShapingError],
    ) -> None:
        input_specs = build_input_specs([("records", concept_ref, multiplicity)])
        records_input: dict[str, Any] = {"records": LIST_OF_OBJECTS}

        if isinstance(expected, StuffContent):
            working_memory = InputShaper.shape(records_input, input_specs=input_specs, concept_provider=get_concept_library())
            stuff = working_memory.root["records"]
            assert stuff.concept.concept_ref == concept_ref
            assert stuff.content == expected
            return

        with pytest.raises(expected, match="Input 'records'"):
            InputShaper.shape(records_input, input_specs=input_specs, concept_provider=get_concept_library())
