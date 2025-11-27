from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from kajson.kajson_manager import KajsonManager
from typing_extensions import runtime_checkable

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.concepts.helpers import strip_multiplicity_from_concept_string_or_code
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeFactoryError, PipeVariableMultiplicityError
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.inputs.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint, PipeType
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_required_concept

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_abstract import PipeAbstract

PipeBlueprintType = TypeVar("PipeBlueprintType", bound="PipeBlueprint", contravariant=True)
PipeAbstractType = TypeVar("PipeAbstractType", bound="PipeAbstract", covariant=True)


@runtime_checkable
class PipeFactoryProtocol(Protocol[PipeBlueprintType, PipeAbstractType]):
    @classmethod
    def make(
        cls,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str | None,
        inputs: InputRequirements,
        output: Concept,
        blueprint: PipeBlueprintType,
    ) -> PipeAbstractType: ...


class PipeFactory(Generic[PipeAbstractType]):
    @classmethod
    def make_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        blueprint: PipeBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeAbstractType:
        if concept_codes_from_the_same_domain is None:
            concept_codes_from_the_same_domain = []

        # TODO: This test should move to the PipelexBlueprint validation.
        # Validate that the specified concepts are declared in the bundle, or are natives concepts.
        if blueprint.inputs is not None:
            for input_name, input_concept_string_or_code in blueprint.inputs.items():
                stripped_input_concept_string_or_code = strip_multiplicity_from_concept_string_or_code(
                    concept_string_or_code=input_concept_string_or_code
                )
                if "." not in stripped_input_concept_string_or_code:
                    if (
                        not NativeConceptCode.is_native_concept_string_or_code(concept_string_or_code=stripped_input_concept_string_or_code)
                        and stripped_input_concept_string_or_code not in concept_codes_from_the_same_domain
                    ):
                        msg = (
                            f"Input stuff '{input_name}' with concept '{stripped_input_concept_string_or_code}' "
                            f"in pipe '{pipe_code}' (domain '{domain_code}') is invalid. "
                            f"The concept must be either native, declared in domain '{domain_code}', or fully qualified with a domain prefix. "
                            f"Declared concepts are: '{concept_codes_from_the_same_domain}'"
                        )
                        raise PipeFactoryError(msg)

        if "." not in blueprint.output:
            stripped_output_concept_string_or_code = strip_multiplicity_from_concept_string_or_code(concept_string_or_code=blueprint.output)
            if (
                not NativeConceptCode.is_native_concept_string_or_code(concept_string_or_code=stripped_output_concept_string_or_code)
                and stripped_output_concept_string_or_code not in concept_codes_from_the_same_domain
            ):
                msg = (
                    f"Output concept '{stripped_output_concept_string_or_code}' in pipe '{pipe_code}' (domain '{domain_code}') is invalid. "
                    f"The concept must be either native, declared in domain '{domain_code}', or fully qualified with a domain prefix. "
                    f"Declared concepts are: '{concept_codes_from_the_same_domain}'"
                )
                raise PipeFactoryError(msg)

        # Parse common attributes
        parsed_output = cls._parse_output_concept_string(domain=domain_code, pipe_code=pipe_code, output_string=blueprint.output)
        parsed_inputs = InputRequirementsFactory.make_from_blueprint(
            domain=domain_code,
            blueprint=blueprint.inputs or {},
        )

        pipe_type = PipeType(blueprint.type)
        pipe_category = pipe_type.category

        # The factory class name for that specific type of Pipe is the pipe class name with "Factory" suffix
        factory_class_name = f"{pipe_type.value}Factory"
        try:
            pipe_factory: type[PipeFactoryProtocol[Any, Any]] = KajsonManager.get_class_registry().get_required_subclass(
                name=factory_class_name,
                base_class=PipeFactoryProtocol,
            )
        except ClassRegistryNotFoundError as factory_not_found_error:
            msg = f"Pipe '{pipe_code}' couldn't be created: factory '{factory_class_name}' not found: {factory_not_found_error}"
            raise PipeFactoryError(msg) from factory_not_found_error
        except ClassRegistryInheritanceError as factory_inheritance_error:
            msg = f"Pipe '{pipe_code}' couldn't be created: factory '{factory_class_name}' is not a subclass of {type(PipeFactoryProtocol)}."
            raise PipeFactoryError(msg) from factory_inheritance_error

        pipe: PipeAbstractType = pipe_factory.make(
            pipe_category=pipe_category,
            pipe_type=blueprint.type,
            pipe_code=pipe_code,
            domain_code=domain_code,
            description=blueprint.description,
            inputs=parsed_inputs,
            output=parsed_output,
            blueprint=blueprint,
        )
        return pipe

    @classmethod
    def _parse_output_concept_string(
        cls,
        domain: str,
        pipe_code: str,
        output_string: str,
    ) -> Concept:
        """Parse the output concept string and return the Concept object."""
        # Parse output to strip multiplicity brackets
        try:
            output_parse_result = parse_concept_with_multiplicity(output_string)
        except PipeVariableMultiplicityError as exc:
            msg = f"Error parsing concept with multiplicity for pipe '{pipe_code}': {exc}"
            raise PipeFactoryError(msg) from exc

        # Get output concept
        try:
            output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
                domain=domain,
                concept_string_or_code=output_parse_result.concept,
            )
        except ConceptFactoryError as exc:
            msg = f"Error making domain and concept code for pipe '{pipe_code}': {exc}"
            raise PipeFactoryError(msg) from exc

        return get_required_concept(
            concept_string=ConceptFactory.make_concept_string_with_domain(
                domain=output_domain_and_code.domain,
                concept_code=output_domain_and_code.concept_code,
            ),
        )
