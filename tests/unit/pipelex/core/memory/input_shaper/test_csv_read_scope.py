"""A table given as a CSV input is a local file, so a run with a read scope refuses it before reading.

Every shaping route that reaches the table reader is covered: the bare path and the ``{"url": ...}``
wrapper read by signature, and the explicit envelope the bottom-up factory reads (Case 2.5).
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.list_content import ListContent
from pipelex.interpreter_hub import get_concept_library
from pipelex.kernel.memory_ops import shape_inputs
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError
from tests.unit.pipelex.core.memory.input_shaper.data import build_input_specs

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent

PEOPLE_CSV_CONTENT = "name\nAda Lovelace\nGrace Hopper\n"


class TestCsvInputReadScope:
    @pytest.fixture
    def people_csv(self, tmp_path: Path) -> Path:
        csv_path = tmp_path / "people.csv"
        csv_path.write_text(PEOPLE_CSV_CONTENT, encoding="utf-8")
        return csv_path

    def _values(self, people_csv: Path) -> list[Any]:
        return [
            str(people_csv),
            {"url": str(people_csv)},
            f"file://{people_csv}",
            {"concept": "shaper_test.ShaperPerson", "content": {"url": str(people_csv)}},
        ]

    def test_a_scoped_run_refuses_every_route_to_the_table_reader(self, people_csv: Path) -> None:
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        for value in self._values(people_csv):
            with pytest.raises(UriReadRefusedError) as exc_info:
                InputShaper.shape({"people": value}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope="org_abc")
            assert exc_info.value.reason == UriReadRefusalReason.LOCAL_PATH
            assert "input 'people'" in str(exc_info.value)
            assert str(people_csv) not in str(exc_info.value)

    def test_the_kernel_shaping_op_refuses_it_too(self, people_csv: Path) -> None:
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        with pytest.raises(UriReadRefusedError):
            shape_inputs(inputs={"people": str(people_csv)}, concept_provider=get_concept_library(), input_specs=input_specs, read_scope="org_abc")

    def test_an_unscoped_run_reads_every_route(self, people_csv: Path) -> None:
        input_specs = build_input_specs([("people", "shaper_test.ShaperPerson", True)])
        for value in self._values(people_csv):
            working_memory = InputShaper.shape({"people": value}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)
            people_content = working_memory.get_stuff("people").content
            assert isinstance(people_content, ListContent)
            assert len(cast("ListContent[StuffContent]", people_content).items) == 2
