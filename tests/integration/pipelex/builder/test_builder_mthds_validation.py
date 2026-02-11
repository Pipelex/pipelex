"""Tests for validating builder domain MTHDS files.

This module tests that builder.mthds and agentic_builder.mthds are valid and that
input/output types are correctly declared, especially for pipes that receive
batched outputs (lists) from previous steps.
"""

from pathlib import Path
from typing import ClassVar

import pytest

from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipeline.validate_bundle import validate_bundle

BUILDER_DIR = Path(__file__).parent.parent.parent.parent.parent / "pipelex" / "builder"


class TestData:
    """Test data for builder MTHDS validation tests."""

    BUILDER_MTHDS_PATH: ClassVar[Path] = BUILDER_DIR / "builder.mthds"
    AGENTIC_BUILDER_MTHDS_PATH: ClassVar[Path] = BUILDER_DIR / "agentic_builder.mthds"
    PIPE_DESIGN_MTHDS_PATH: ClassVar[Path] = BUILDER_DIR / "pipe" / "pipe_design.mthds"


class TestBuilderMthdsValidation:
    """Tests that builder domain MTHDS files are valid and type-consistent."""

    @pytest.mark.asyncio(loop_scope="class")
    async def test_builder_mthds_loads_and_validates(self):
        """Test that builder.mthds can be loaded and validated successfully."""
        result = await validate_bundle(
            mthds_file_path=TestData.BUILDER_MTHDS_PATH,
            library_dirs=[BUILDER_DIR, BUILDER_DIR / "pipe"],
        )

        assert result is not None
        assert len(result.blueprints) == 1
        assert result.blueprints[0].domain == "builder"
        assert len(result.pipes) > 0

    @pytest.mark.asyncio(loop_scope="class")
    async def test_agentic_builder_mthds_loads_and_validates(self):
        """Test that agentic_builder.mthds can be loaded and validated successfully."""
        result = await validate_bundle(
            mthds_file_path=TestData.AGENTIC_BUILDER_MTHDS_PATH,
            library_dirs=[BUILDER_DIR, BUILDER_DIR / "pipe"],
        )

        assert result is not None
        assert len(result.blueprints) == 1
        assert result.blueprints[0].domain == "agentic_builder"
        assert len(result.pipes) > 0

    @pytest.mark.asyncio(loop_scope="class")
    async def test_pipe_design_mthds_loads_and_validates(self):
        """Test that pipe_design.mthds can be loaded and validated successfully."""
        result = await validate_bundle(
            mthds_file_path=TestData.PIPE_DESIGN_MTHDS_PATH,
            library_dirs=[BUILDER_DIR, BUILDER_DIR / "pipe"],
        )

        assert result is not None
        assert len(result.blueprints) == 1
        assert result.blueprints[0].domain == "pipe_design"
        assert len(result.pipes) > 0

    def test_assemble_pipelex_bundle_spec_has_list_inputs_in_builder(self):
        """Test that assemble_pipelex_bundle_spec declares list inputs correctly in builder.mthds.

        This test catches the bug where pipe_specs was incorrectly declared as
        "pipe_design.PipeSpec" instead of "pipe_design.PipeSpec[]" when the pipe
        receives the output of a batch_over operation which produces a list.

        See: builder.mthds line 31 (batch_over produces list) and line 332 (input declaration)
        """
        blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=TestData.BUILDER_MTHDS_PATH)

        assert blueprint.pipe is not None
        assert "assemble_pipelex_bundle_spec" in blueprint.pipe

        pipe_blueprint = blueprint.pipe["assemble_pipelex_bundle_spec"]
        assert pipe_blueprint.inputs is not None

        # Verify pipe_specs is declared as a list (with [] notation)
        pipe_specs_input = pipe_blueprint.inputs.get("pipe_specs")
        assert pipe_specs_input is not None, "assemble_pipelex_bundle_spec must have pipe_specs input"
        assert "[]" in pipe_specs_input, f"pipe_specs must be declared as a list (with []) since it receives batch output. Got: {pipe_specs_input}"

        # Verify concept_specs is declared as a list
        concept_specs_input = pipe_blueprint.inputs.get("concept_specs")
        assert concept_specs_input is not None, "assemble_pipelex_bundle_spec must have concept_specs input"
        assert "[]" in concept_specs_input, f"concept_specs must be declared as a list (with []). Got: {concept_specs_input}"

    def test_detail_all_pipe_specs_outputs_list_in_agentic_builder(self):
        """Test that detail_all_pipe_specs declares list output in agentic_builder.mthds.

        This test verifies that the PipeBatch that generates pipe_specs correctly
        declares its output as a list, which is then consumed by assemble_pipelex_bundle_spec.
        """
        blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=TestData.AGENTIC_BUILDER_MTHDS_PATH)

        assert blueprint.pipe is not None
        assert "detail_all_pipe_specs" in blueprint.pipe

        pipe_blueprint = blueprint.pipe["detail_all_pipe_specs"]
        assert pipe_blueprint.output is not None

        # PipeBatch output should be declared as a list
        assert "[]" in pipe_blueprint.output, f"detail_all_pipe_specs (PipeBatch) must declare list output. Got: {pipe_blueprint.output}"

    def test_batch_over_result_consistency_with_subsequent_inputs(self):
        """Test that batch_over results are consumed by pipes with matching list inputs.

        In builder.mthds, pipe_builder uses batch_over on detail_pipe_spec to produce pipe_specs.
        The subsequent assemble_pipelex_bundle_spec must declare pipe_specs as a list input.
        """
        blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=TestData.BUILDER_MTHDS_PATH)

        assert blueprint.pipe is not None

        # Find the pipe_builder sequence (we know it's a PipeSequenceBlueprint)
        pipe_builder = blueprint.pipe.get("pipe_builder")
        assert pipe_builder is not None
        assert isinstance(pipe_builder, PipeSequenceBlueprint), "pipe_builder should be a PipeSequenceBlueprint"
        assert pipe_builder.steps is not None

        # Find the step that uses batch_over and its result name
        batch_result_name: str | None = None
        for step in pipe_builder.steps:
            if step.batch_over:
                batch_result_name = step.result
                break

        assert batch_result_name is not None, "pipe_builder should have a batch_over step with a result"

        # Find the assemble step that should consume this batch result
        has_assemble_step = False
        for step in pipe_builder.steps:
            if step.pipe == "assemble_pipelex_bundle_spec":
                has_assemble_step = True
                break

        assert has_assemble_step, "pipe_builder should have assemble_pipelex_bundle_spec step"

        # Verify the assemble pipe declares the batch result as a list input
        assemble_pipe = blueprint.pipe.get("assemble_pipelex_bundle_spec")
        assert assemble_pipe is not None
        assert assemble_pipe.inputs is not None

        batch_input = assemble_pipe.inputs.get(batch_result_name)
        assert batch_input is not None, f"assemble_pipelex_bundle_spec must have {batch_result_name} input to receive batch result"
        assert "[]" in batch_input, (
            f"assemble_pipelex_bundle_spec.{batch_result_name} must be declared as a list since it receives batch_over output. Got: {batch_input}"
        )
