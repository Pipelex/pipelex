"""The GraphSpec io item a run writes for a stuff: its multiplicity is read off the value.

A list reads `True` whatever its length, so an empty list never writes `0` (which a GraphSpec
reader refuses) and a one-item list never reads as single. Anything else reads `None`.
"""

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.graphspec import IOSpec, make_io_concept_label
from pipelex.graph.stuff_io_spec import make_stuff_io_spec


def _make_text_stuff(*, name: str) -> Stuff:
    return StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text="hello"),
        name=name,
    )


def _make_text_list_stuff(*, name: str, texts: list[str]) -> Stuff:
    return StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=ListContent[TextContent](items=[TextContent(text=text) for text in texts]),
        name=name,
    )


class TestMakeStuffIoSpec:
    def test_single_stuff_reads_single(self) -> None:
        stuff = _make_text_stuff(name="summary")

        io_spec = make_stuff_io_spec(name="summary", stuff=stuff, include_data=False)

        assert io_spec.multiplicity is None
        assert io_spec.concept == "Text"
        assert io_spec.digest == stuff.stuff_code

    @pytest.mark.parametrize(
        "texts",
        [
            pytest.param(["a", "b", "c"], id="several_items"),
            pytest.param(["a"], id="one_item_is_still_a_list"),
            pytest.param([], id="empty_list_never_writes_zero"),
        ],
    )
    def test_list_stuff_reads_variable_length_whatever_its_length(self, texts: list[str]) -> None:
        stuff = _make_text_list_stuff(name="records", texts=texts)

        io_spec = make_stuff_io_spec(name="records", stuff=stuff, include_data=False)

        assert io_spec.multiplicity is True
        # The concept stays bare: the marker is the multiplicity field's job.
        assert io_spec.concept == "Text"

    def test_data_is_embedded_only_when_asked(self) -> None:
        stuff = _make_text_list_stuff(name="records", texts=["a"])

        assert make_stuff_io_spec(name="records", stuff=stuff, include_data=False).data is None
        assert make_stuff_io_spec(name="records", stuff=stuff, include_data=True).data is not None

    def test_extra_rides_through_and_defaults_empty(self) -> None:
        stuff = _make_text_stuff(name="verdict")

        assert make_stuff_io_spec(name="verdict", stuff=stuff, include_data=False).extra == {}
        assert make_stuff_io_spec(name="verdict", stuff=stuff, include_data=False, extra={"optional": True}).extra == {"optional": True}


class TestIoSpecMultiplicityField:
    @pytest.mark.parametrize(
        "multiplicity",
        [
            pytest.param(True, id="variable_length"),
            pytest.param(3, id="fixed_count"),
            pytest.param(1, id="count_of_one"),
            pytest.param(False, id="false_single"),
            pytest.param(None, id="absent_single"),
        ],
    )
    def test_accepts_what_a_graphspec_reader_accepts(self, multiplicity: bool | int | None) -> None:
        assert IOSpec(name="stuff", multiplicity=multiplicity).multiplicity == multiplicity

    @pytest.mark.parametrize(
        "multiplicity",
        [
            pytest.param(0, id="zero"),
            pytest.param(-2, id="negative"),
            pytest.param("[]", id="authored_suffix_string"),
            pytest.param(2.0, id="float"),
        ],
    )
    def test_refuses_what_a_graphspec_reader_refuses(self, multiplicity: object) -> None:
        with pytest.raises(ValidationError):
            IOSpec.model_validate({"name": "stuff", "multiplicity": multiplicity})

    def test_survives_a_json_round_trip(self) -> None:
        for multiplicity in (True, 3, None):
            io_spec = IOSpec(name="stuff", concept="Record", multiplicity=multiplicity)
            assert IOSpec.model_validate_json(io_spec.model_dump_json()) == io_spec


class TestIoConceptLabel:
    @pytest.mark.parametrize(
        ("multiplicity", "expected"),
        [
            pytest.param(True, "Record[]", id="variable_length"),
            pytest.param(3, "Record[3]", id="fixed_count"),
            pytest.param(1, "Record", id="count_of_one_reads_single"),
            pytest.param(False, "Record", id="false_reads_single"),
            pytest.param(None, "Record", id="absent_reads_single"),
        ],
    )
    def test_marks_the_concept_as_an_author_writes_it(self, multiplicity: bool | int | None, expected: str) -> None:
        assert make_io_concept_label(concept="Record", multiplicity=multiplicity) == expected
        assert IOSpec(name="records", concept="Record", multiplicity=multiplicity).concept_label == expected

    def test_no_concept_has_no_label(self) -> None:
        assert make_io_concept_label(concept=None, multiplicity=True) is None
