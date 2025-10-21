from pathlib import Path
from typing import Any

from pipelex import log
from pipelex.builder.builder import PipelexBundleSpec
from pipelex.builder.flow import Flow, FlowElement
from pipelex.builder.pipe.pipe_signature import PipeSignature
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories
from pipelex.exceptions import PipelexException
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint


class FlowFactoryError(PipelexException):
    """Exception raised by FlowFactory."""


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
        flow_elements: dict[str, FlowElement] = {}

        if bundle_blueprint.pipe:
            for pipe_code, pipe_blueprint in bundle_blueprint.pipe.items():
                if pipe_blueprint.pipe_category == AllowedPipeCategories.PIPE_CONTROLLER:
                    # Keep controllers as-is (they are already blueprints which match spec structure)
                    # Type check to ensure we only assign controller blueprints
                    if isinstance(
                        pipe_blueprint,
                        PipeBatchBlueprint | PipeConditionBlueprint | PipeParallelBlueprint | PipeSequenceBlueprint,
                    ):  # pyright: ignore[reportUnnecessaryIsInstance]
                        flow_elements[pipe_code] = FlowElement(controller_blueprint=pipe_blueprint)
                        log.verbose(
                            f"Adding controller {pipe_code} to flow: category is '{pipe_blueprint.pipe_category}' and type is '{pipe_blueprint.type}'"
                        )
                    else:
                        msg = f"Pipe {pipe_code} is not a controller"
                        raise FlowFactoryError(message=msg)
                else:
                    # Convert operators to signatures
                    signature_from_blueprint = FlowFactory._convert_blueprint_to_signature(pipe_code=pipe_code, pipe_blueprint=pipe_blueprint)
                    flow_elements[pipe_code] = FlowElement(operator_signature=signature_from_blueprint)
                    log.verbose(
                        f"Adding operator {pipe_code} to flow: category is '{pipe_blueprint.pipe_category}' and type is '{pipe_blueprint.type}'"
                    )
                    log.verbose(signature_from_blueprint, title="Signature from blueprint")
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
        return PipeSignature(
            code=pipe_code,
            pipe_category=pipe_blueprint.pipe_category,
            type=pipe_blueprint.type,
            description=pipe_blueprint.description or "",
            inputs=pipe_blueprint.inputs,
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
