from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import (
    ConceptFactoryError,
    ConceptRefineError,
    ConceptStringError,
)
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.concepts.validation import is_concept_code_valid, validate_concept_string_or_code
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.text_content import TextContent


class DomainAndConceptCode(BaseModel):
    """Small model to represent domain and concept code pair."""

    domain: str
    concept_code: str


class ConceptFactory:
    @classmethod
    def normalize_structure_blueprint(cls, structure_dict: dict[str, str | ConceptStructureBlueprint]) -> dict[str, ConceptStructureBlueprint]:
        """Convert a mixed structure dictionary to a proper ConceptStructureBlueprint dictionary.

        Args:
            structure_dict: Dictionary that may contain strings or ConceptStructureBlueprint objects

        Returns:
            Dictionary with all values as ConceptStructureBlueprint objects

        """
        normalized: dict[str, ConceptStructureBlueprint] = {}

        for field_name, field_value in structure_dict.items():
            if isinstance(field_value, str):
                # Convert string definition to ConceptStructureBlueprint for text field
                normalized[field_name] = ConceptStructureBlueprint(
                    description=field_value,
                    type=ConceptStructureBlueprintFieldType.TEXT,  # Explicitly set as text field
                    required=True,  # Default for simple string definitions
                )
            else:
                normalized[field_name] = field_value

        return normalized

    @classmethod
    def make(cls, concept_code: str, domain: str, description: str, structure_class_name: str, refines: str | None = None) -> Concept:
        return Concept(
            code=concept_code,
            domain=domain,
            description=description,
            structure_class_name=structure_class_name,
            refines=refines,
        )

    @classmethod
    def make_native_concept(cls, native_concept_code: NativeConceptCode) -> Concept:
        structure_class_name = native_concept_code.structure_class_name
        match native_concept_code:
            case NativeConceptCode.DYNAMIC:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="A dynamic concept",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.TEXT:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="A text",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.IMAGE:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="An image",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.PDF:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="A PDF",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.TEXT_AND_IMAGES:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="A text and an image",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.NUMBER:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="A number",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.IMG_GEN_PROMPT:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="A prompt for an image generator",
                    structure_class_name=NativeConceptCode.TEXT.structure_class_name,
                )
            case NativeConceptCode.PAGE:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="The content of a page of a document, comprising text and linked images and an optional page view image",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.ANYTHING:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="Anything",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.JSON:
                return Concept(
                    code=native_concept_code,
                    domain=SpecialDomain.NATIVE,
                    description="A JSON object",
                    structure_class_name=structure_class_name,
                )

    @classmethod
    def make_all_native_concepts(cls) -> list[Concept]:
        return [cls.make_native_concept(native_concept_code=native_concept) for native_concept in NativeConceptCode.values_list()]

    @classmethod
    def make_domain_and_concept_code_from_concept_string_or_code(
        cls,
        concept_string_or_code: str,
        domain: str | None = None,
    ) -> DomainAndConceptCode:
        if "." not in concept_string_or_code and not domain:
            msg = f"Not enough information to make a domain and concept code from '{concept_string_or_code}'"
            raise ConceptFactoryError(msg)
        try:
            validate_concept_string_or_code(concept_string_or_code=concept_string_or_code)
        except ConceptStringError as exc:
            msg = f"Concept string or code '{concept_string_or_code}' is not a valid concept string or code"
            raise ConceptFactoryError(msg) from exc

        if NativeConceptCode.is_native_concept_string_or_code(concept_string_or_code=concept_string_or_code):
            natice_concept_string = NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=concept_string_or_code)
            return DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code=natice_concept_string.split(".")[1])

        if "." in concept_string_or_code:
            domain_code, concept_code = concept_string_or_code.rsplit(".")
            return DomainAndConceptCode(domain=domain_code, concept_code=concept_code)
        elif domain:
            return DomainAndConceptCode(domain=domain, concept_code=concept_string_or_code)
        else:
            msg = f"Not enough information to make a domain and concept code from '{concept_string_or_code}'"
            raise ConceptFactoryError(msg)

    @classmethod
    def make_concept_string_with_domain(cls, domain: str, concept_code: str) -> str:
        return f"{domain}.{concept_code}"

    @classmethod
    def make_concept_string_with_domain_from_concept_string_or_code(cls, domain: str, concept_sring_or_code: str) -> str:
        input_domain_and_code = cls.make_domain_and_concept_code_from_concept_string_or_code(
            concept_string_or_code=concept_sring_or_code,
            domain=domain,
        )

        return cls.make_concept_string_with_domain(
            domain=input_domain_and_code.domain,
            concept_code=input_domain_and_code.concept_code,
        )

    @classmethod
    def make_refine(cls, refine: str) -> str:
        """Validate and normalize a refine string.

        If the refine is a native concept code without domain (e.g., 'Text'),
        it will be normalized to include the native domain prefix (e.g., 'native.Text').

        Args:
            refine: The refine string to validate and normalize

        Returns:
            The normalized refine string with domain prefix

        Raises:
            ConceptFactoryError: If the refine is invalid

        """
        return NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=refine)

    @classmethod
    def make_from_blueprint_or_description(
        cls,
        domain: str,
        concept_code: str,
        concept_blueprint_or_description: ConceptBlueprint | str,
    ) -> Concept:
        blueprint: ConceptBlueprint
        if isinstance(concept_blueprint_or_description, str):
            blueprint = ConceptBlueprint(description=concept_blueprint_or_description)
        else:
            blueprint = concept_blueprint_or_description
        return cls.make_from_blueprint(
            domain=domain,
            concept_code=concept_code,
            blueprint=blueprint,
        )

    @classmethod
    def make_from_blueprint(
        cls,
        domain: str,
        concept_code: str,
        blueprint: ConceptBlueprint,
    ) -> Concept:
        if not is_concept_code_valid(concept_code=concept_code):
            msg = f"Concept code '{concept_code}' is not a valid concept code"
            raise ConceptFactoryError(msg)
        structure_class_name: str
        current_refine: str | None = None

        # Handle structure definition
        if blueprint.structure:
            if isinstance(blueprint.structure, str):
                # Structure is defined as a string - check if the class is in the registry and is valid
                if not Concept.is_valid_structure_class(structure_class_name=blueprint.structure):
                    msg = (
                        f"Structure class '{blueprint.structure}' set for concept '{concept_code}' in domain '{domain}' "
                        "is not a registered subclass of StuffContent"
                    )
                    raise ConceptFactoryError(msg)
                structure_class_name = blueprint.structure
            else:
                # Structure is defined as a ConceptStructureBlueprint - run the structure generator and put it in the class registry
                # Normalize the structure blueprint to ensure all values are ConceptStructureBlueprint objects
                normalized_structure = cls.normalize_structure_blueprint(blueprint.structure)

                try:
                    _, the_generated_class = StructureGenerator().generate_from_structure_blueprint(
                        class_name=concept_code,
                        structure_blueprint=normalized_structure,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = f"Error generating python code for structure class of concept '{concept_code}' in domain '{domain}': {exc}"
                    raise ConceptFactoryError(
                        msg,
                    ) from exc

                # Register the generated class
                KajsonManager.get_class_registry().register_class(the_generated_class)

                # The structure_class_name of the concept is the concept_code
                structure_class_name = concept_code

        # Handle refines definition
        elif blueprint.refines:
            # If we have refines, validate that there is not already a structure related to this concept code in the class registry
            # TODO: This test should NOT BE HERE, but in the `validate_with_libraries`.
            if Concept.is_valid_structure_class(structure_class_name=concept_code):
                msg = (
                    f"Concept '{concept_code}' in domain '{domain}' has refines but also has a structure class registered. "
                    "A concept cannot have both structure and refines."
                )
                raise ConceptFactoryError(msg)
            try:
                current_refine = cls.make_refine(refine=blueprint.refines)
            except ConceptRefineError as exc:
                msg = f"Could not validate refine '{blueprint.refines}' for concept '{concept_code}' in domain '{domain}': {exc}"
                raise ConceptFactoryError(msg) from exc
            structure_class_name = current_refine.split(".")[1] + "Content" if current_refine else TextContent.__name__
        # Handle neither structure nor refines - check the class registry
        # If there is a class, use it. structure_class_name is then the concept_code
        elif Concept.is_valid_structure_class(structure_class_name=concept_code):
            structure_class_name = concept_code
        else:
            # If there is NO class, the fallback class is TextContent.__name__
            structure_class_name = TextContent.__name__

        domain_and_concept_code = cls.make_domain_and_concept_code_from_concept_string_or_code(
            concept_string_or_code=concept_code,
            domain=domain,
        )

        return Concept(
            domain=domain_and_concept_code.domain,
            code=domain_and_concept_code.concept_code,
            description=blueprint.description,
            structure_class_name=structure_class_name,
            refines=current_refine,
        )
