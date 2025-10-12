from pathlib import Path
from typing import Any

from pipelex.builder.builder import PipelexBundleSpec
from pipelex.builder.flow import Flow, FlowElementUnion
from pipelex.builder.pipe.pipe_signature import PipeSignature
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint


class FlowFactory:
    """Factory for creating Flow from PipelexBundleSpec or PLX files.

    Converts a complete bundle specification into a simplified flow view
    by keeping pipe controllers as-is and converting pipe operators to signatures.
    """

    @staticmethod
    def make_from_plx_file(plx_file_path: Path | str) -> Flow:
        """Create Flow from a PLX file.

        Args:
            plx_file_path: Path to the PLX file to load.

        Returns:
            Flow with controllers preserved and operators as signatures.
        """
        plx_path = Path(plx_file_path) if isinstance(plx_file_path, str) else plx_file_path
        bundle_blueprint = PipelexInterpreter(file_path=plx_path).make_pipelex_bundle_blueprint()
        return FlowFactory.make_from_bundle_blueprint(bundle_blueprint)

    @staticmethod
    def make_from_bundle_blueprint(bundle_blueprint: PipelexBundleBlueprint) -> Flow:
        """Convert a PipelexBundleBlueprint to a Flow.

        Args:
            bundle_blueprint: The bundle blueprint to convert.

        Returns:
            Flow with controllers preserved and operators as signatures.
        """
        flow_elements: dict[str, FlowElementUnion] = {}

        if bundle_blueprint.pipe:
            for pipe_code, pipe_blueprint in bundle_blueprint.pipe.items():
                if pipe_blueprint.pipe_category == AllowedPipeCategories.PIPE_CONTROLLER:
                    # Keep controllers as-is (they are already blueprints which match spec structure)
                    # Type check to ensure we only assign controller blueprints
                    if isinstance(
                        pipe_blueprint,
                        PipeBatchBlueprint | PipeConditionBlueprint | PipeParallelBlueprint | PipeSequenceBlueprint,
                    ):  # pyright: ignore[reportUnnecessaryIsInstance]
                        flow_elements[pipe_code] = pipe_blueprint
                else:
                    # Convert operators to signatures
                    flow_elements[pipe_code] = FlowFactory._convert_blueprint_to_signature(pipe_code, pipe_blueprint)

        return Flow(
            domain=bundle_blueprint.domain,
            description=bundle_blueprint.description,
            flow_elements=flow_elements,
        )

    @staticmethod
    def _convert_blueprint_to_signature(pipe_code: str, pipe_blueprint: Any) -> PipeSignature:
        """Convert a pipe blueprint to a pipe signature.

        Args:
            pipe_code: The code identifying the pipe.
            pipe_blueprint: The pipe blueprint to convert.

        Returns:
            PipeSignature containing the contract information.
        """
        # Extract inputs as strings from InputRequirementBlueprint
        inputs: dict[str, str] = {}
        if pipe_blueprint.inputs:
            for input_name, input_requirement in pipe_blueprint.inputs.items():
                if hasattr(input_requirement, "concept"):
                    inputs[input_name] = input_requirement.concept
                else:
                    inputs[input_name] = str(input_requirement)

        return PipeSignature(
            code=pipe_code,
            pipe_category="PipeSignature",
            type=pipe_blueprint.type,
            description=pipe_blueprint.description or "",
            inputs=inputs,
            result=pipe_code,
            output=pipe_blueprint.output,
            pipe_dependencies=[],
        )

    @staticmethod
    def make_from_bundle_spec(bundle_spec: PipelexBundleSpec) -> Flow:
        """Convert a PipelexBundleSpec to a Flow.

        Args:
            bundle_spec: The complete bundle specification to convert.

        Returns:
            Flow with controllers preserved and operators as signatures.
        """
        # Convert the spec to blueprint first, then use the blueprint converter
        bundle_blueprint = bundle_spec.to_blueprint()
        return FlowFactory.make_from_bundle_blueprint(bundle_blueprint)
