from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from kajson.kajson_manager import KajsonManager
from typing_extensions import runtime_checkable

from pipelex.core.concepts.helpers import strip_multiplicity_from_concept_ref_or_code
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeFactoryError, PipeFactoryErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint, PipeType
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.stuff_spec.stuff_spec_factory import StuffSpecFactory, StuffSpecFactoryError

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
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
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
            for input_name, input_concept_ref_or_code in blueprint.inputs.items():
                stripped_input_concept_ref_or_code = strip_multiplicity_from_concept_ref_or_code(concept_ref_or_code=input_concept_ref_or_code)
                if "." not in stripped_input_concept_ref_or_code:
                    if (
                        not NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=stripped_input_concept_ref_or_code)
                        and stripped_input_concept_ref_or_code not in concept_codes_from_the_same_domain
                    ):
                        msg = (
                            f"Input stuff '{input_name}' with concept '{stripped_input_concept_ref_or_code}' "
                            f"in pipe '{pipe_code}' (domain '{domain_code}') is invalid. "
                            f"The concept must be either native, declared in domain '{domain_code}', or fully qualified with a domain prefix. "
                            f"Declared concepts are: '{concept_codes_from_the_same_domain}'"
                        )
                        raise PipeFactoryError(msg)

        if "." not in blueprint.output:
            stripped_output_concept_ref_or_code = strip_multiplicity_from_concept_ref_or_code(concept_ref_or_code=blueprint.output)
            if (
                not NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=stripped_output_concept_ref_or_code)
                and stripped_output_concept_ref_or_code not in concept_codes_from_the_same_domain
            ):
                msg = (
                    f"Output concept '{stripped_output_concept_ref_or_code}' in pipe '{pipe_code}' (domain '{domain_code}') is invalid. "
                    f"The concept must be either native, declared in domain '{domain_code}', or fully qualified with a domain prefix. "
                    f"Declared concepts are: '{concept_codes_from_the_same_domain}'"
                )
                raise PipeFactoryError(
                    message=msg,
                    error_type=PipeFactoryErrorType.UNKNOWN_CONCEPT,
                    pipe_code=pipe_code,
                    domain_code=domain_code,
                    missing_concept_code=stripped_output_concept_ref_or_code,
                    declared_concepts=concept_codes_from_the_same_domain,
                )

        # Parse common attributes
        try:
            parsed_output = StuffSpecFactory.make_from_blueprint(domain_code=domain_code, output_string=blueprint.output)
        except StuffSpecFactoryError as exc:
            msg = f"Error parsing output string '{blueprint.output}': {exc}"
            raise PipeFactoryError(msg) from exc
        parsed_inputs = InputStuffSpecsFactory.make_from_blueprint(
            domain_code=domain_code,
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
