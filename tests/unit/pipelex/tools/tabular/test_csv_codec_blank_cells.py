"""An empty CSV cell is "no value": a defaulted field that refuses `None` takes its default, as for an omitted column.

A structure field with a `default_value` never holds nothing, so its generated class refuses `None`, and a blank
cell under it must not become one.
"""

from pathlib import Path
from typing import Any

import pytest

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.tabular.csv_codec import list_content_from_csv
from pipelex.tools.tabular.exceptions import CsvCoercionError


class PresenceRow(StructuredContent):
    name: str
    note: str = "fallback"
    count: int = 0
    nickname: str | None = "anon"


def _write_csv(directory: Path, content: str) -> Path:
    path = directory / "data.csv"
    path.write_text(content, encoding="utf-8")
    return path


class TestCsvCodecBlankCells:
    def test_a_blank_cell_under_a_defaulted_field_refusing_none_takes_its_default(self, tmp_path: Path):
        path = _write_csv(tmp_path, "name,note,count,nickname\nalice,,,\nbob,hello,3,bobby\n")

        rows = list_content_from_csv(path, row_model=PresenceRow).items

        assert [(row.name, row.note, row.count, row.nickname) for row in rows] == [
            ("alice", "fallback", 0, None),
            ("bob", "hello", 3, "bobby"),
        ]

    def test_a_blank_cell_under_a_required_field_is_refused(self, tmp_path: Path):
        path = _write_csv(tmp_path, "name,note\n,hello\n")

        with pytest.raises(CsvCoercionError, match="name"):
            list_content_from_csv(path, row_model=PresenceRow)

    def test_a_blank_cell_under_a_generated_defaulted_field_takes_its_default(self, tmp_path: Path):
        row_class: Any
        _, row_class = StructureGenerator(local_domain="csv_blank").generate_from_structure_blueprint(
            class_name="GeneratedRow",
            structure_blueprint={
                "name": ConceptStructureBlueprint(description="a name", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
                "note": ConceptStructureBlueprint(description="a note", type=ConceptStructureBlueprintFieldType.TEXT, default_value="fallback"),
                "remark": ConceptStructureBlueprint(description="a remark", type=ConceptStructureBlueprintFieldType.TEXT),
            },
        )
        path = _write_csv(tmp_path, "name,note,remark\nalice,,\n")

        rows = list_content_from_csv(path, row_model=row_class).items

        assert [row.model_dump() for row in rows] == [{"name": "alice", "note": "fallback", "remark": None}]
