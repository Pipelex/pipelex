"""Dry-run coverage for native Date from a `.mthds` file.

Two shapes, both keyless (dry mode mocks only the cogt leaf and rides the live render path):
- Date as a PipeLLM output — the object path mocks a `DateContent` via polyfactory (which
  synthesizes `date`/`time` natively).
- Date as a pipeline input (fed as a `DateContent`) — it renders inline in the downstream prompt.
"""

import datetime
from pathlib import Path

import pytest

from pipelex.core.stuffs.date_content import DateContent
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode

_FIXTURE_DIR = Path(__file__).parent / "date_departure"


@pytest.mark.asyncio(loop_scope="class")
class TestDateDryRun:
    async def test_dry_run_date_output_produces_mock_date(self):
        """A PipeLLM whose output is Date completes in dry mode with a mocked DateContent."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        response = await runner.execute(pipe_code="extract_departure", inputs={"ticket": "Flight AF123, departure 7 Jul 2026 15:40"})

        assert response.state == RunState.COMPLETED
        assert response.pipe_output.main_stuff.is_date
        assert isinstance(response.pipe_output.main_stuff_as_date.date, datetime.date)

    async def test_dry_run_date_input_flows_through(self):
        """A Date pipeline input renders into the downstream prompt and the run completes."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        departure = DateContent(date=datetime.date(2026, 7, 7), time=datetime.time(15, 40, tzinfo=datetime.timezone(datetime.timedelta(hours=2))))
        response = await runner.execute(pipe_code="describe_departure", inputs={"departure": departure})

        assert response.state == RunState.COMPLETED
        departure_stuff = response.pipe_output.working_memory.get_stuff("departure")
        assert departure_stuff.is_date
        assert departure_stuff.as_date.time is not None
        assert response.pipe_output.main_stuff.as_text.text
