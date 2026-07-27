"""Unit tests for CSV-by-signature (D11 compounding): a bare tabular path — or the exact
``{"url": <tabular path>}`` wrapper — under a declared structured list input (``Person[]``)
reads the table into a ``ListContent[declared]`` with no envelope. Detection is conservative:
non-tabular values, singular declarations, and record dicts with sibling keys all fall through
to the normal shaping arms.
"""

from pathlib import Path
from typing import Any, cast

import pytest

from pipelex.core.memory.exceptions import MultiplicityCountMismatchError, StructureValidationError, WrongScalarKindError
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.interpreter_hub import get_concept_library
from pipelex.tools.tabular.exceptions import CsvError
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
        working_memory = InputShaper.shape({"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library())

        people_stuff = working_memory.get_stuff("people")
        assert people_stuff.concept.concept_ref == "shaper_test.ShaperPerson"
        self._assert_people_list(people_stuff.content)

    def test_url_dict_csv_under_declared_list(self, people_csv: Path):
        """The exact {"url": <csv>} wrapper under `ShaperPerson[]` reads the same table — no envelope."""
        value: dict[str, Any] = {"url": str(people_csv)}
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        working_memory = InputShaper.shape({"people": value}, input_specs=input_specs, concept_provider=get_concept_library())

        people_stuff = working_memory.get_stuff("people")
        assert people_stuff.concept.concept_ref == "shaper_test.ShaperPerson"
        self._assert_people_list(people_stuff.content)

    @pytest.mark.usefixtures("people_csv")
    def test_relative_csv_resolves_against_base_dir(self, tmp_path: Path):
        """A bare relative CSV path resolves against inputs_base_dir before the table is read."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        working_memory = InputShaper.shape(
            {"people": "people.csv"}, input_specs=input_specs, inputs_base_dir=tmp_path, concept_provider=get_concept_library()
        )

        self._assert_people_list(working_memory.get_stuff("people").content)

    def test_fixed_count_matching_rows(self, people_csv: Path):
        """A `ShaperPerson[2]` input accepts a two-row CSV."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", 2)])
        working_memory = InputShaper.shape({"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library())

        self._assert_people_list(working_memory.get_stuff("people").content)

    def test_fixed_count_mismatch_raises(self, people_csv: Path):
        """A `ShaperPerson[3]` input rejects a two-row CSV with the D2 count-mismatch error."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", 3)])
        with pytest.raises(MultiplicityCountMismatchError, match="'people'"):
            InputShaper.shape({"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library())

    def test_csv_under_singular_is_wrong_scalar_kind(self, people_csv: Path):
        """A CSV names a TABLE; under a singular `ShaperPerson` a bare path is a wrong-kind error."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", None)])
        with pytest.raises(WrongScalarKindError, match="'people'"):
            InputShaper.shape({"people": str(people_csv)}, input_specs=input_specs, concept_provider=get_concept_library())

    def test_non_tabular_string_falls_through(self):
        """A bare non-tabular string under `ShaperPerson[]` is NOT hijacked as a table — normal D5 error."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        with pytest.raises(WrongScalarKindError, match="'people'"):
            InputShaper.shape({"people": "people.txt"}, input_specs=input_specs, concept_provider=get_concept_library())

    def test_url_dict_with_sibling_keys_stays_record(self, people_csv: Path):
        """A record dict that merely HAS a url field is not a table ref — validated as a record."""
        value: dict[str, Any] = {"url": str(people_csv), "label": "roster"}
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        with pytest.raises(StructureValidationError, match="'people'"):
            InputShaper.shape({"people": value}, input_specs=input_specs, concept_provider=get_concept_library())

    def test_remote_csv_url_raises_csv_error(self):
        """A remote tabular url is rejected loudly (local paths only in v1), not read or ignored."""
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        with pytest.raises(CsvError, match="local file paths only"):
            InputShaper.shape({"people": "https://example.com/people.csv"}, input_specs=input_specs, concept_provider=get_concept_library())
