"""Pin `build_pipe_io_artifacts`: the three validate artifacts built once, off one crate qualification.

The builder is the single sequence `validate_bundles_in_process` used to spell out inline —
contracts, one `qualify_current_library_crate()`, both forms off the same qualification — so a
run's results and a validate report cannot drift on how the artifacts are derived. Needs a loaded
library, like the three builders it wraps.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.build_pipe_io_artifacts import build_pipe_io_artifacts
from pipelex.pipeline.input_form import build_input_form, build_output_form, qualify_current_library_crate
from pipelex.pipeline.pipe_io_contracts import build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle

if TYPE_CHECKING:
    from collections.abc import Callable

_PROBE_BUNDLE_PATH = Path(__file__).parents[3] / "data" / "input_semantics" / "probe_bundle.mthds"


def _teardown_validation_library(outer_library_id: str) -> None:
    validation_library_id = get_current_library_id_or_none()
    if validation_library_id is not None and validation_library_id != outer_library_id:
        set_current_library(library_id=outer_library_id)
        get_library_manager().teardown(library_id=validation_library_id)
    clear_current_library()


@pytest.mark.asyncio(loop_scope="class")
class TestBuildPipeIOArtifacts:
    async def test_equals_the_three_builders_in_sequence_and_shares_one_key_set(self, load_empty_library: Callable[[], str]) -> None:
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_PROBE_BUNDLE_PATH.read_text(encoding="utf-8")])
            artifacts = build_pipe_io_artifacts(result.pipes)
            qualified_crate = qualify_current_library_crate()
            assert artifacts.pipe_io_contracts == build_pipe_io_contracts(result.pipes)
            assert artifacts.input_form == build_input_form(result.pipes, qualified_crate=qualified_crate)
            assert artifacts.output_form == build_output_form(result.pipes, qualified_crate=qualified_crate)
            # A caller holding a qualification already (the validate orchestrator) gets the same artifacts.
            assert build_pipe_io_artifacts(result.pipes, qualified_crate=qualified_crate) == artifacts
        finally:
            _teardown_validation_library(outer_library_id)
        keys = {pipe.pipe_ref for pipe in result.pipes}
        assert keys, "the probe bundle declares pipes"
        assert set(artifacts.pipe_io_contracts) == keys
        assert set(artifacts.input_form) == keys
        assert set(artifacts.output_form) == keys
