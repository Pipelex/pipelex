"""Integration tests for the CSV round-trip (Phase 1 — RED).

Split per the plan (T1) into three independent assertions so each fails for a single,
nameable reason:

- (a) input-codec: a ``.csv`` ``url`` under a flat row concept builds a
  ``ListContent[Person]`` (no pipeline run). RED today because ``stuff_factory`` Case 2.5
  treats ``{"url": ...}`` as a record dict and pydantic rejects it.
- (b) output-codec: a hand-built ``ListContent[PersonSummary]`` writes to CSV with the
  declared header + one row per item. RED today because the codec is unimplemented.
- (c) full pipeline: ``PipeBatch -> PipeSequence(PipeLLM + PipeCompose)`` over the parsed
  rows yields one ``PersonSummary`` per input row, with ``name``/``country`` carried from
  the real CSV rows (verified to hold in dry mode). RED today because the input ``.csv``
  is not parsed yet.

``death_year`` is asserted on the input list only — ``PersonSummary`` drops it.
"""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from mthds.protocol.pipeline_inputs import PipelineInputs

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.interpreter_hub import get_concept_library, get_library_manager
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.tools.tabular.csv_codec import csv_from_list_content

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent

BUNDLE_DIR = Path(__file__).parent / "csv_demo"
PEOPLE_CSV = BUNDLE_DIR / "people.csv"

EXPECTED_NAMES = {"Ada Lovelace", "Grace Hopper", "Vint Cerf"}
EXPECTED_COUNTRIES = {"United Kingdom", "United States"}


def people_inputs() -> PipelineInputs:
    """Pipeline inputs pointing the row concept at the local ``people.csv`` (absolute path)."""
    return {"people": {"concept": "csv_demo.Person", "content": {"url": str(PEOPLE_CSV)}}}


class TestCsvRoundtrip:
    # ----------------------------------------------------------------------------------
    # (a) input-codec — a .csv url under a flat concept becomes ListContent[Person]
    # ----------------------------------------------------------------------------------

    def test_csv_input_builds_typed_list(self, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([BUNDLE_DIR])
        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(people_inputs(), concept_provider=get_concept_library())

        people = working_memory.get_stuff("people").content
        assert isinstance(people, ListContent)
        people_list = cast("ListContent[StuffContent]", people)
        assert len(people_list.items) == 3

        rows = [item.model_dump() for item in people_list.items]
        assert [row["name"] for row in rows] == ["Ada Lovelace", "Grace Hopper", "Vint Cerf"]
        # CSV strings coerced to declared field types.
        assert rows[0]["birth_year"] == 1815
        assert isinstance(rows[0]["birth_year"], int)
        assert rows[0]["death_year"] == 1852
        # Trailing blank death_year cell → None on the optional field (Vint Cerf, still living).
        assert rows[2]["death_year"] is None

    # ----------------------------------------------------------------------------------
    # (b) output-codec — a hand-built ListContent[PersonSummary] writes to CSV
    # ----------------------------------------------------------------------------------

    def test_list_content_writes_to_csv(self, tmp_path: Path, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([BUNDLE_DIR])
        summary_concept = get_library_manager().get_current_library().concept_library.get_required_concept("csv_demo.PersonSummary")
        summary_class = summary_concept.get_structure_class()

        items = [
            summary_class.model_validate({"name": "Ada Lovelace", "country": "United Kingdom", "summary": "A visionary mathematician."}),
            summary_class.model_validate({"name": "Grace Hopper", "country": "United States", "summary": "A pioneering computer scientist."}),
        ]
        list_content: ListContent[StuffContent] = ListContent(items=items)

        out_path = tmp_path / "summaries.csv"
        csv_from_list_content(list_content, row_model=summary_class, path=out_path)

        lines = out_path.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "name,country,summary"
        assert lines[1] == "Ada Lovelace,United Kingdom,A visionary mathematician."
        assert lines[2] == "Grace Hopper,United States,A pioneering computer scientist."

    # ----------------------------------------------------------------------------------
    # (c) full pipeline — CSV in → batch+compose → PersonSummary[] (dry mode)
    # ----------------------------------------------------------------------------------

    @pytest.mark.dry_runnable
    @pytest.mark.llm
    @pytest.mark.inference
    @pytest.mark.asyncio
    async def test_full_pipeline_round_trip(self, pipe_run_mode: PipeRunMode) -> None:
        runner = PipelexMTHDSProtocol(library_dirs=[str(BUNDLE_DIR)], pipe_run_mode=pipe_run_mode)
        response = await runner.execute(pipe_code="summarize_people", inputs=people_inputs())

        content = response.pipe_output.main_stuff.content
        assert isinstance(content, ListContent)
        summaries = cast("ListContent[StuffContent]", content)
        assert len(summaries.items) == 3

        rows = [item.model_dump() for item in summaries.items]
        # PipeCompose carries the real CSV name/country through even in dry mode.
        assert {row["name"] for row in rows} == EXPECTED_NAMES
        assert {row["country"] for row in rows} <= EXPECTED_COUNTRIES
        # The summary is mock text in dry mode — assert it is present, not its content.
        assert all(row["summary"] for row in rows)
