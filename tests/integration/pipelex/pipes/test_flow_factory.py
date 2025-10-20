import os
from pathlib import Path

import pytest

from pipelex import log, pretty_print
from pipelex.builder.flow_factory import FlowFactory
from pipelex.builder.pipe.pipe_signature import PipeSignature
from pipelex.core.pipes.pipe_blueprint import AllowedPipeTypes
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.tools.misc.file_utils import get_incremental_directory_path, remove_folder
from pipelex.tools.misc.json_utils import save_as_json_to_path
from tests.conftest import TEST_OUTPUTS_DIR


@pytest.mark.asyncio(loop_scope="class")
class TestFlowFactory:
    """Test FlowFactory loading PLX files and converting to flow view."""

    @pytest.mark.parametrize(
        ("plx_name", "plx_file"),
        [
            ("discord_newsletter", "discord_newsletter.plx"),
            ("tricky_questions", "tricky_questions.plx"),
        ],
    )
    async def test_load_plx_and_convert_to_flow(
        self,
        plx_name: str,
        plx_file: str,
    ):
        """Load a PLX file, convert to Flow, and save as JSON.

        This test demonstrates the FlowFactory's ability to:
        1. Load a PLX file
        2. Convert it to a simplified flow view
        3. Serialize the result to JSON for inspection

        The flow view shows:
        - Pipe controllers with full details (sequence, parallel, condition, batch)
        - Pipe operators as signatures only (contract without implementation)
        """
        # Setup result directory
        result_dir_path = get_incremental_directory_path(
            base_path=TEST_OUTPUTS_DIR,
            base_name=f"flow_{plx_name}",
        )

        try:
            # Load PLX file from test pipelines directory
            test_pipelines_dir = Path(__file__).parent.parent.parent.parent / "test_pipelines"
            plx_file_path = test_pipelines_dir / plx_file

            log.info(f"Loading PLX file: {plx_file_path}")

            # Convert to pipeline flow
            flow = FlowFactory.make_from_plx_file(plx_file_path)

            # Pretty print for console output
            pretty_print(flow, title=f"Pipeline flow: {plx_name}")

            # Save as JSON to results directory
            json_output_path = os.path.join(result_dir_path, "pipeline_flow.json")
            save_as_json_to_path(object_to_save=flow, path=json_output_path)

            log.info(f"Saved flow to: {json_output_path}")

            # Verify the flow was created correctly
            assert flow is not None
            assert flow.domain is not None
            assert flow.flow_elements is not None
            assert len(flow.flow_elements) > 0

            # Log some details about what we found
            controller_count = sum(1 for element in flow.flow_elements.values() if element.controller_blueprint is not None)
            operator_count = sum(1 for element in flow.flow_elements.values() if element.operator_signature is not None)

            log.info(f"flow contains {len(flow.flow_elements)} pipes: {controller_count} controllers, {operator_count} operators (as signatures)")

        finally:
            # Cleanup - remove the temporary result directory
            remove_folder(result_dir_path)

    async def test_flow_preserves_sequence_structure(self):
        """Verify that PipeSequence controllers preserve their step structure."""
        test_pipelines_dir = Path(__file__).parent.parent.parent.parent / "test_pipelines"
        plx_file_path = test_pipelines_dir / "discord_newsletter.plx"

        flow = FlowFactory.make_from_plx_file(plx_file_path)

        # Find the sequence pipe
        sequence_element = flow.flow_elements.get("write_discord_newsletter")
        assert sequence_element is not None
        assert sequence_element.controller_blueprint is not None
        assert sequence_element.controller_blueprint.type == "PipeSequence"

        # Type narrow to PipeSequenceBlueprint for type safety
        assert isinstance(sequence_element.controller_blueprint, PipeSequenceBlueprint)

        # Verify steps are preserved
        assert len(sequence_element.controller_blueprint.steps) > 0

        log.info(f"Sequence pipe has {len(sequence_element.controller_blueprint.steps)} steps:")
        for step in sequence_element.controller_blueprint.steps:
            log.info(f"  - {step.pipe} -> {step.result}")

    async def test_flow_converts_operators_to_signatures(self):
        """Verify that pipe operators are converted to signatures (simplified view)."""
        test_pipelines_dir = Path(__file__).parent.parent.parent.parent / "test_pipelines"
        plx_file_path = test_pipelines_dir / "discord_newsletter.plx"

        flow = FlowFactory.make_from_plx_file(plx_file_path)

        # Find an operator pipe (LLM pipe) - converted to signature
        operator_element = flow.flow_elements.get("summarize_discord_channel_update_for_new_members")
        assert operator_element is not None
        assert operator_element.operator_signature is not None
        assert isinstance(operator_element.operator_signature, PipeSignature)
        assert operator_element.operator_signature.type == AllowedPipeTypes.PIPE_LLM

        # Verify it has the signature properties
        assert hasattr(operator_element.operator_signature, "code")
        assert hasattr(operator_element.operator_signature, "inputs")
        assert hasattr(operator_element.operator_signature, "output")
        assert hasattr(operator_element.operator_signature, "description")

        # Verify it doesn't have implementation details (like prompt)
        assert not hasattr(operator_element, "prompt")

        log.info(f"Operator pipe '{operator_element.operator_signature.code}' converted to signature:")
        log.info(f"  Inputs: {operator_element.operator_signature.inputs}")
        log.info(f"  Output: {operator_element.operator_signature.output}")
