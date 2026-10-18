"""Unit tests for CSV-by-signature (D11 compounding): a bare tabular path — or the exact
``{"url": <tabular path>}`` wrapper — under a declared structured list input (``Person[]``)
reads the table into a ``ListContent[declared]`` with no envelope. Detection is conservative:
non-tabular values, singular declarations, and record dicts with sibling keys all fall through
to the normal shaping arms.
"""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.core.concepts.exceptions import ConceptStructureClassNotFoundError
from pipelex.core.memory.exceptions import MultiplicityCountMismatchError, StructureValidationError, WrongScalarKindError
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.errors.problem import ProblemView
from pipelex.errors.unsupported_reasons import REMOTE_TABLE_UNSUPPORTED_REASON
from pipelex.interpreter_hub import get_concept_library
from pipelex.tools.tabular.exceptions import CsvCoercionError, CsvError
from tests.unit.pipelex.core.memory.input_shaper.data import ShaperPerson, build_input_specs

PEOPLE_CSV_CONTENT = "name\nAda Lovelace\nGrace Hopper\n"


class TestInputShaperCsvBySignature:
    @pytest.fixture
    def people_csv(self, tmp_path: Path) -> Path:
        csv_path = tmp_path / "people.csv"
        csv_path.write_text(PEOPLE_CSV_CONTENT, encoding="utf-8")
        return csv_path

    def _assert_people_list(self, working_memory_stuff_content: StuffContent) -> None:
        assert isinstance(working_memory_stuff_content, ListContent)
        items = cast("ListContent[StuffContent]", working_memory_stuff_content).items
        assert [item.name for item in items if isinstance(item, ShaperPerson)] == ["Ada Lovelace", "Grace Hopper"]

    def test_bare_csv_path_under_declared_list(self, people_csv: Path):
        """A bare absolute CSV path under `ShaperPerson[]` reads rows into ListContent[ShaperPerson]."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        working_memory = InputShaper.shape(
            {"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None
        )

        people_stuff = working_memory.get_stuff("people")
        assert people_stuff.concept.concept_ref == "shaper_test.ShaperPerson"
        self._assert_people_list(people_stuff.content)

    def test_url_dict_csv_under_declared_list(self, people_csv: Path):
        """The exact {"url": <csv>} wrapper under `ShaperPerson[]` reads the same table — no envelope."""
        value: dict[str, Any] = {"url": str(people_csv)}
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        working_memory = InputShaper.shape({"people": value}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        people_stuff = working_memory.get_stuff("people")
        assert people_stuff.concept.concept_ref == "shaper_test.ShaperPerson"
        self._assert_people_list(people_stuff.content)

    @pytest.mark.usefixtures("people_csv")
    def test_relative_csv_resolves_against_base_dir(self, tmp_path: Path):
        """A bare relative CSV path resolves against inputs_base_dir before the table is read."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        working_memory = InputShaper.shape(
            {"people": "people.csv"}, input_specs=input_specs, inputs_base_dir=tmp_path, concept_provider=get_concept_library(), read_scope=None
        )

        self._assert_people_list(working_memory.get_stuff("people").content)

    def test_fixed_count_matching_rows(self, people_csv: Path):
        """A `ShaperPerson[2]` input accepts a two-row CSV."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", 2)])
        working_memory = InputShaper.shape(
            {"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None
        )

        self._assert_people_list(working_memory.get_stuff("people").content)

    def test_fixed_count_mismatch_raises(self, people_csv: Path):
        """A `ShaperPerson[3]` input rejects a two-row CSV with the D2 count-mismatch error."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", 3)])
        with pytest.raises(MultiplicityCountMismatchError, match="'people'"):
            InputShaper.shape({"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

    def test_csv_under_singular_is_wrong_scalar_kind(self, people_csv: Path):
        """A CSV names a TABLE; under a singular `ShaperPerson` a bare path is a wrong-kind error."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", None)])
        with pytest.raises(WrongScalarKindError, match="'people'"):
            InputShaper.shape({"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

    def test_non_tabular_string_falls_through(self):
        """A bare non-tabular string under `ShaperPerson[]` is NOT hijacked as a table — normal D5 error."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        with pytest.raises(WrongScalarKindError, match="'people'"):
            InputShaper.shape({"people": "people.txt"}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

    def test_url_dict_with_sibling_keys_stays_record(self, people_csv: Path):
        """A record dict that merely HAS a url field is not a table ref — validated as a record."""
        value: dict[str, Any] = {"url": str(people_csv), "label": "roster"}
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        with pytest.raises(StructureValidationError, match="'people'"):
            InputShaper.shape({"people": value}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

    def test_remote_csv_url_raises_csv_error(self):
        """A remote tabular url is rejected loudly (local paths only in v1), not read or ignored."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        with pytest.raises(CsvError, match="local file paths only"):
            InputShaper.shape(
                {"people": "https://example.com/people.csv"}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None
            )

    @pytest.mark.parametrize(
        ("topic", "url", "expected_location"),
        [
            ("a scheme Pipelex reads", "s3://bucket/people.csv", "a remote or non-local url, in the scheme 's3'"),
            ("a scheme Pipelex reads, written in capitals", "HTTPS://example.com/people.csv", "a remote or non-local url, in the scheme 'https'"),
            ("a scheme that is the caller's own text", "confidential-patient-diagnosis://records/people.csv", "a remote or non-local url"),
        ],
    )
    def test_a_remote_table_names_its_scheme_only_when_pipelex_reads_it(self, topic: str, url: str, expected_location: str):
        """A url's scheme is the caller's text: the refusal names one Pipelex reads, never one the caller made up."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])

        with pytest.raises(CsvError) as exc_info:
            InputShaper.shape({"people": {"url": url}}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        assert str(exc_info.value) == (
            "CSV input supports local file paths only in v1, but stuff 'people' for concept 'shaper_test.ShaperPerson' points at "
            f"{expected_location}. Download the file locally and reference it by path."
        ), topic
        operator = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert "confidential" not in json.dumps(operator.to_wire()), topic
        # Only a local path is read as a table: the form the input uses is one this runtime does not accept.
        assert operator.code == CoreCode.REQUEST_UNSUPPORTED, topic
        assert operator.params is not None
        assert operator.params.as_wire() == {"field": "inputs.people", "reason": REMOTE_TABLE_UNSUPPORTED_REASON}, topic

    def test_a_table_url_that_does_not_parse_is_an_unreadable_file(self):
        """A url that does not parse names no file to read: the input's file is unreadable, and the url stays out."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])

        with pytest.raises(CsvError) as exc_info:
            InputShaper.shape(
                {"people": {"url": "https://[confidential-patient-diagnosis/people.csv"}},
                input_specs=input_specs,
                concept_provider=get_concept_library(),
                read_scope=None,
            )

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.INPUT_FILE_UNREADABLE
        assert caller.params is not None
        assert caller.params.as_wire() == {"input": "people", "file_type": "csv", "reason": "the URL does not parse"}
        operator = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert "confidential" not in json.dumps(operator.to_wire())

    def test_a_concept_with_no_structure_class_is_the_method_s_concept_failing(self, people_csv: Path, mocker: MockerFixture):
        """A concept whose rows have no class to be read into is no fault of the caller's table: its concept cannot be built."""
        concept_library = get_concept_library()
        concept = concept_library.get_required_concept(concept_ref="shaper_test.ShaperPerson")
        mocker.patch.object(
            type(concept_library), "get_structure_class", side_effect=ConceptStructureClassNotFoundError("no class registered for the concept")
        )

        with pytest.raises(CsvError) as exc_info:
            StuffFactory.try_make_csv_list_content(
                concept, concept_provider=concept_library, content={"url": str(people_csv)}, name="people", read_scope=None
            )

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.METHOD_CONCEPT_INVALID
        assert caller.params is not None
        assert caller.params.as_wire() == {"concept": "shaper_test.ShaperPerson", "finding": "it has no structure class to read rows into"}

    def test_a_row_the_codec_refuses_without_a_location_names_the_input_as_its_field(self, people_csv: Path, mocker: MockerFixture):
        """A row refused as a whole, which pydantic locates nowhere, is the input's own fault, as a table refused whole is."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        mocker.patch(
            "pipelex.core.stuffs.stuff_factory.list_content_from_csv",
            side_effect=CsvCoercionError("Could not coerce row 2 of the CSV file").with_params(field=None),
        )

        with pytest.raises(CsvError) as exc_info:
            InputShaper.shape({"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.INPUT_INVALID
        assert caller.params is not None
        assert caller.params.as_wire() == {"input": "people", "field": "people"}

    def test_a_table_that_does_not_fit_names_the_input_never_the_file(self, tmp_path: Path):
        """The codec knows the file alone: the input it was given as completes the problem's sentence, and the path stays out."""
        csv_path = tmp_path / "confidential-patient-diagnosis.csv"
        csv_path.write_text("name,confidential-column\nAda,x\n", encoding="utf-8")
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])

        with pytest.raises(CsvError) as exc_info:
            InputShaper.shape({"people": str(csv_path)}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.INPUT_INVALID
        assert caller.params is not None
        assert caller.params.as_wire() == {"input": "people", "field": "people"}
        operator = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert "confidential" not in json.dumps(operator.to_wire())
