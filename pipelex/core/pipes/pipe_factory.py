from typing import Any, Protocol, TypeVar

from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from kajson.kajson_manager import KajsonManager
from typing_extensions import override, runtime_checkable

from pipelex.core.concepts.helpers import strip_multiplicity_from_concept_string_or_code
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeFactoryError
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint

PipeBlueprintType = TypeVar("PipeBlueprintType", bound="PipeBlueprint", contravariant=True)
PipeAbstractType = TypeVar("PipeAbstractType", bound="PipeAbstract", covariant=True)


@runtime_checkable
class PipeFactoryProtocol(Protocol[PipeBlueprintType, PipeAbstractType]):
    @classmethod
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeBlueprintType,
    ) -> PipeAbstractType: ...


class PipeFactory(PipeFactoryProtocol[PipeBlueprint, PipeAbstract]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeAbstract:
        if concept_codes_from_the_same_domain is None:
            concept_codes_from_the_same_domain = []

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
                            f"in pipe '{pipe_code}' (domain '{domain}') is invalid. "
                            f"The concept must be either native, declared in domain '{domain}', or fully qualified with a domain prefix. "
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
                    f"Output concept '{stripped_output_concept_string_or_code}' in pipe '{pipe_code}' (domain '{domain}') is invalid. "
                    f"The concept must be either native, declared in domain '{domain}', or fully qualified with a domain prefix. "
                    f"Declared concepts are: '{concept_codes_from_the_same_domain}'"
                )
                raise PipeFactoryError(msg)

        # The factory class name for that specific type of Pipe is the pipe class name with "Factory" suffix
        factory_class_name = f"{blueprint.type}Factory"
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

        pipe_from_blueprint: PipeAbstract = pipe_factory.make_from_blueprint(
            domain=domain,
            pipe_code=pipe_code,
            blueprint=blueprint,
        )
        return pipe_from_blueprint
