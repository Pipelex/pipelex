from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.errors.unsupported_reasons import REMOTE_TABLE_UNSUPPORTED_REASON
from pipelex.interpreter_hub import get_concept_library
from pipelex.tools.tabular.exceptions import CsvError
from tests.unit.pipelex.core.memory.input_shaper.data import Exhibit, Photo, ShaperExpenseWorkbook, ShaperPerson, build_input_specs

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent

STORAGE_XLSX_URL = "pipelex-storage://org_test/uploads/0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0.xlsx"
HTTPS_CSV_URL = "https://example.com/exports/expenses.csv"
MALFORMED_XLSX_URL = "https://[example.com/exports/expenses.xlsx"

PEOPLE_CSV_CONTENT = "name\nAda Lovelace\nGrace Hopper\n"


class TestFileConceptTableRefs:
    @pytest.fixture
    def people_csv(self, tmp_path: Path) -> Path:
        csv_path = tmp_path / "people.csv"
        csv_path.write_text(PEOPLE_CSV_CONTENT, encoding="utf-8")
        return csv_path

    @pytest.mark.parametrize(
        ("topic", "concept_ref", "expected_class"),
        [
            ("native Document", "native.Document", DocumentContent),
            ("native Image", "native.Image", ImageContent),
            ("a concept refining Document", "shaper_test.Exhibit", Exhibit),
            ("a concept refining a concept refining Document", "shaper_test.ShaperExpenseWorkbook", ShaperExpenseWorkbook),
            ("a concept refining Image", "shaper_test.Photo", Photo),
        ],
    )
    def test_a_file_concept_is_a_file_concept(self, topic: str, concept_ref: str, expected_class: type[Any]):
        concept_library = get_concept_library()
        concept = concept_library.get_required_concept(concept_ref=concept_ref)

        assert concept_library.is_file_concept(concept=concept), topic
        assert issubclass(concept_library.get_structure_class(concept=concept), expected_class), topic

    @pytest.mark.parametrize(
        ("topic", "concept_ref"),
        [
            ("a list-of-rows structure", "shaper_test.ShaperPerson"),
            ("a concept refining Text", "shaper_test.Question"),
            ("native Text", "native.Text"),
            ("native JSON", "native.JSON"),
        ],
    )
    def test_any_other_concept_is_not_a_file_concept(self, topic: str, concept_ref: str):
        concept_library = get_concept_library()
        concept = concept_library.get_required_concept(concept_ref=concept_ref)

        assert not concept_library.is_file_concept(concept=concept), topic

    @pytest.mark.parametrize(
        ("topic", "concept_ref", "url", "expected_class"),
        [
            ("a refined Document with an .xlsx storage url", "shaper_test.Exhibit", STORAGE_XLSX_URL, Exhibit),
            ("a refined Document with a .csv url", "shaper_test.Exhibit", HTTPS_CSV_URL, Exhibit),
            ("a twice-refined Document with an .xlsx storage url", "shaper_test.ShaperExpenseWorkbook", STORAGE_XLSX_URL, ShaperExpenseWorkbook),
            ("a refined Image with a .csv url", "shaper_test.Photo", HTTPS_CSV_URL, Photo),
            ("a native Document with an .xlsx storage url", "native.Document", STORAGE_XLSX_URL, DocumentContent),
        ],
    )
    def test_an_envelope_of_a_file_concept_is_read_as_its_file(
        self, topic: str, concept_ref: str, url: str, expected_class: type[Any], mocker: MockerFixture
    ):
        """The envelope every client's input preparation sends reaches the bottom-up factory's table detection."""
        table_reader = mocker.patch("pipelex.core.stuffs.stuff_factory.list_content_from_table_file")
        input_specs = build_input_specs([("workbook", concept_ref, None)])

        working_memory = InputShaper.shape(
            {"workbook": {"concept": concept_ref, "content": {"url": url}}},
            input_specs=input_specs,
            concept_provider=get_concept_library(),
            read_scope=None,
        )

        workbook = working_memory.get_stuff("workbook")
        assert workbook.concept.concept_ref == concept_ref, topic
        assert type(workbook.content) is expected_class, topic
        assert isinstance(workbook.content, DocumentContent | ImageContent), topic
        assert workbook.content.url == url, topic
        table_reader.assert_not_called()

    @pytest.mark.parametrize(
        ("topic", "concept_ref", "url"),
        [
            ("a refined Document with an .xlsx storage url", "shaper_test.Exhibit", STORAGE_XLSX_URL),
            ("a twice-refined Document with a .csv url", "shaper_test.ShaperExpenseWorkbook", HTTPS_CSV_URL),
        ],
    )
    def test_a_bare_url_under_a_declared_file_concept_is_read_as_its_file(self, topic: str, concept_ref: str, url: str):
        input_specs = build_input_specs([("workbook", concept_ref, None)])

        working_memory = InputShaper.shape(
            {"workbook": {"url": url}}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None
        )

        workbook = working_memory.get_stuff("workbook")
        assert isinstance(workbook.content, DocumentContent), topic
        assert workbook.content.url == url, topic

    @pytest.mark.parametrize(
        ("topic", "concept_ref"),
        [
            ("a refined Document", "shaper_test.Exhibit"),
            ("a twice-refined Document", "shaper_test.ShaperExpenseWorkbook"),
            ("a refined Image", "shaper_test.Photo"),
        ],
    )
    def test_a_url_that_does_not_parse_under_a_file_concept_is_no_table_error(self, topic: str, concept_ref: str):
        """A url `urlsplit` refuses is the file concept's own to judge, never refused as an unreadable table."""
        concept_library = get_concept_library()
        concept = concept_library.get_required_concept(concept_ref=concept_ref)

        list_content = StuffFactory.try_make_csv_list_content(
            concept, concept_provider=concept_library, content={"url": MALFORMED_XLSX_URL}, name="workbook", read_scope=None
        )

        assert list_content is None, topic

    def test_a_local_csv_under_a_refined_document_is_not_read_as_rows(self, people_csv: Path, mocker: MockerFixture):
        table_reader = mocker.patch("pipelex.core.stuffs.stuff_factory.list_content_from_table_file")
        concept_library = get_concept_library()
        concept = concept_library.get_required_concept(concept_ref="shaper_test.Exhibit")

        list_content = StuffFactory.try_make_csv_list_content(
            concept, concept_provider=concept_library, content={"url": str(people_csv)}, name="workbook", read_scope=None
        )

        assert list_content is None
        table_reader.assert_not_called()

    def test_a_list_of_rows_concept_still_reads_its_csv(self, people_csv: Path):
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])

        working_memory = InputShaper.shape(
            {"people": {"concept": "shaper_test.ShaperPerson", "content": {"url": str(people_csv)}}},
            input_specs=input_specs,
            concept_provider=get_concept_library(),
            read_scope=None,
        )

        people = working_memory.get_stuff("people").content
        assert isinstance(people, ListContent)
        items = cast("ListContent[StuffContent]", people).items
        assert [item.name for item in items if isinstance(item, ShaperPerson)] == ["Ada Lovelace", "Grace Hopper"]

    def test_a_list_of_rows_concept_still_refuses_a_remote_table(self):
        concept_library = get_concept_library()
        concept = concept_library.get_required_concept(concept_ref="shaper_test.ShaperPerson")

        with pytest.raises(CsvError) as exc_info:
            StuffFactory.try_make_csv_list_content(
                concept, concept_provider=concept_library, content={"url": HTTPS_CSV_URL}, name="people", read_scope=None
            )

        assert exc_info.value.given_params.get("reason") == REMOTE_TABLE_UNSUPPORTED_REASON

    @pytest.mark.parametrize(
        ("topic", "url"),
        [
            ("a data URL that is not base64", "data:text/csv,name%0Ahello.csv"),
            ("a data URL in upper case", "DATA:text/csv,name%0Ahello.xlsx"),
        ],
    )
    def test_a_list_of_rows_concept_refuses_a_data_url_table_as_a_remote_one(self, topic: str, url: str):
        concept_library = get_concept_library()
        concept = concept_library.get_required_concept(concept_ref="shaper_test.ShaperPerson")

        for read_scope in (None, "org_test"):
            with pytest.raises(CsvError) as exc_info:
                StuffFactory.try_make_csv_list_content(
                    concept, concept_provider=concept_library, content={"url": url}, name="people", read_scope=read_scope
                )

            assert exc_info.value.given_params.get("reason") == REMOTE_TABLE_UNSUPPORTED_REASON, topic
