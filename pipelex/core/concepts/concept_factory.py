from typing import cast

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.exceptions import (
    ConceptFactoryError,
    ConceptRefineError,
    ConceptStringError,
)
from pipelex.core.concepts.helpers import normalize_structure_blueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.text_content import TextContent
from pipelex.types import StrEnum


class ConceptDeclarationType(StrEnum):
    """Enum representing the 5 ways a concept can be declared in PLX files.

    Option 1: STRING - Concept is defined as a string
        Example:
            [concept]
            Concept1 = "Definition of Concept1"

    Option 2: BASIC_BLUEPRINT - Concept is defined with a basic blueprint
        Example:
            [concept.Concept2]
            description = "Definition of Concept2"

    Option 3: REFINES - Concept refines another concept
        Example:
            [concept.Concept3]
            description = "A concept3"
            refines = "native.Text"

    Option 4: STRUCTURE_WITH_CLASSNAME
        Example:
            [concept.Concept4]
            description = "A concept4"
            structure = "ExistingClassName"

    Option 5: BLUEPRINT_WITH_STRUCTURE - Concept is defined with a blueprint and a structure
        Example:
            [concept.Concept5]
            description = "A concept5"

            [concept.Concept5.structure]
            field1 = "A field1"
            field2 = {type = "text", description = "A field2"}
    """

    STRING = "string"
    BASIC_BLUEPRINT = "basic_blueprint"
    REFINES = "refines"
    STRUCTURE_WITH_CLASSNAME = "structure_with_classname"
    BLUEPRINT_WITH_STRUCTURE = "blueprint_with_structure"


class DomainAndConceptCode(BaseModel):
    """Small model to represent domain and concept code pair."""

    domain_code: str
    concept_code: str


class ConceptFactory:
    @classmethod
    def make(cls, concept_code: str, domain_code: str, description: str, structure_class_name: str, refines: str | None = None) -> Concept:
        return Concept(
            code=concept_code,
            domain_code=domain_code,
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
                    domain_code=SpecialDomain.NATIVE,
                    description="A dynamic concept",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.TEXT:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="A text",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.IMAGE:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="An image",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.DOCUMENT:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="A document",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.TEXT_AND_IMAGES:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="A text and an image",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.NUMBER:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="A number",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.IMG_GEN_PROMPT:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="A prompt for an image generator",
                    structure_class_name=NativeConceptCode.TEXT.structure_class_name,
                )
            case NativeConceptCode.PAGE:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="The content of a page of a document, comprising text and linked images and an optional page view image",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.ANYTHING:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="Anything",
                    structure_class_name=structure_class_name,
                )
            case NativeConceptCode.JSON:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="A JSON object",
                    structure_class_name=structure_class_name,
                )

    @classmethod
    def make_domain_and_concept_code_from_concept_ref_or_code(
        cls,
        concept_ref_or_code: str,
        domain_code: str | None = None,
    ) -> DomainAndConceptCode:
        if "." not in concept_ref_or_code and not domain_code:
            msg = f"Not enough information to make a domain and concept code from '{concept_ref_or_code}'"
            raise ConceptFactoryError(msg)
        try:
            validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
        except ConceptStringError as exc:
            msg = f"Concept string or code '{concept_ref_or_code}' is not a valid concept string or code"
            raise ConceptFactoryError(msg) from exc

        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
            natice_concept_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref_or_code)
            return DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code=natice_concept_ref.split(".")[1])

        if "." in concept_ref_or_code:
            domain_code, concept_code = concept_ref_or_code.rsplit(".")
            return DomainAndConceptCode(domain_code=domain_code, concept_code=concept_code)
        elif domain_code:
            return DomainAndConceptCode(domain_code=domain_code, concept_code=concept_ref_or_code)
        else:
            msg = f"Not enough information to make a domain and concept code from '{concept_ref_or_code}'"
            raise ConceptFactoryError(msg)

    @classmethod
    def make_concept_ref_with_domain(cls, domain_code: str, concept_code: str) -> str:
        return f"{domain_code}.{concept_code}"

    @classmethod
    def make_concept_ref_with_domain_from_concept_ref_or_code(cls, domain_code: str, concept_sring_or_code: str) -> str:
        input_domain_and_code = cls.make_domain_and_concept_code_from_concept_ref_or_code(
            concept_ref_or_code=concept_sring_or_code,
            domain_code=domain_code,
        )

        return cls.make_concept_ref_with_domain(
            domain_code=input_domain_and_code.domain_code,
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
        return NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=refine)

    @classmethod
    def _handle_structure_with_classname(
        cls,
        blueprint: ConceptBlueprint,
        concept_code: str,
        domain_code: str,
    ) -> str:
        """Handle STRUCTURE_WITH_CLASSNAME declaration type.

        Structure is defined as a string class name - check if the class is in the registry and is valid.

        Returns:
            The structure class name
        """
        structure_class_name = blueprint.structure
        if not isinstance(structure_class_name, str):
            msg = f"Expected structure to be a string, got {type(structure_class_name)}"
            raise ConceptFactoryError(msg)
        if not Concept.is_valid_structure_class(structure_class_name=structure_class_name):
            msg = (
                f"Structure class '{structure_class_name}' set for concept '{concept_code}' in domain '{domain_code}' "
                "is not a registered subclass of StuffContent, or was not found in the library."
            )
            raise ConceptFactoryError(msg)
        return structure_class_name

    @classmethod
    def _handle_blueprint_with_structure(
        cls,
        blueprint: ConceptBlueprint,
        concept_code: str,
        domain_code: str,
    ) -> str:
        """Handle BLUEPRINT_WITH_STRUCTURE declaration type.

        Structure is defined as a ConceptStructureBlueprint dict - run the structure generator
        and register it in the class registry.

        Returns:
            The structure class name (which is the concept_code)
        """
        if not isinstance(blueprint.structure, dict):
            msg = f"Expected structure to be a dict, got {type(blueprint.structure)}"
            raise ConceptFactoryError(msg)

        # Normalize the structure blueprint to ensure all values are ConceptStructureBlueprint objects
        normalized_structure = normalize_structure_blueprint(blueprint.structure)

        try:
            _, the_generated_class = StructureGenerator().generate_from_structure_blueprint(
                class_name=concept_code,
                structure_blueprint=normalized_structure,
            )
        except ConceptStructureGeneratorError as exc:
            msg = f"Error generating python code for structure class of concept '{concept_code}' in domain '{domain_code}': {exc}"
            raise ConceptFactoryError(msg) from exc

        # Register the generated class
        KajsonManager.get_class_registry().register_class(the_generated_class)

        return concept_code

    @classmethod
    def _handle_basic_blueprint(
        cls,
        concept_code: str,
        domain_code: str,
    ) -> tuple[str, str | None]:
        """Handle BASIC_BLUEPRINT declaration type.

        Returns:
            Tuple of (structure_class_name, refine_string)
        """
        # Generate a new class that inherits from TextContent and register it
        # (unless a valid structure class already exists for this concept_code)
        if Concept.is_valid_structure_class(structure_class_name=concept_code):
            return concept_code, None

        # Because native concepts have structure class names diffrent than other (with "Content")
        if concept_code in NativeConceptCode.values_list():
            return NativeConceptCode.TEXT.structure_class_name, NativeConceptCode.TEXT.concept_ref

        try:
            _, the_generated_class = StructureGenerator().generate_from_structure_blueprint(
                class_name=concept_code,
                structure_blueprint={},
                base_class_name=TextContent.__name__,
            )
        except ConceptStructureGeneratorError as exc:
            msg = f"Error generating structure class for concept '{concept_code}' in domain '{domain_code}': {exc}"
            raise ConceptFactoryError(msg) from exc
        # Register the generated class
        KajsonManager.get_class_registry().register_class(the_generated_class)

        return concept_code, NativeConceptCode.TEXT.concept_ref

    @classmethod
    def _handle_refines(
        cls,
        blueprint: ConceptBlueprint,
        concept_code: str,
        domain_code: str,
    ) -> tuple[str, str]:
        """Handle REFINES declaration type.

        Concept refines another concept - generate a new class that inherits from the refined
        structure class.

        Returns:
            Tuple of (structure_class_name, refine_string)
        """
        if blueprint.refines is None:
            msg = "Expected refines to be set"
            raise ConceptFactoryError(msg)

        try:
            current_refine = cls.make_refine(refine=blueprint.refines)
        except ConceptRefineError as exc:
            msg = f"Could not validate refine '{blueprint.refines}' for concept '{concept_code}' in domain '{domain_code}': {exc}"
            raise ConceptFactoryError(msg) from exc

        # Get the refined concept's structure class name
        refined_structure_class_name = current_refine.split(".")[1] + "Content"

        # Generate a new class that inherits from the refined structure class
        # This creates an empty class that can be extended with additional fields in the future
        try:
            _, the_generated_class = StructureGenerator().generate_from_structure_blueprint(
                class_name=concept_code,
                structure_blueprint={},  # Empty structure - just inherits from refined class
                base_class_name=refined_structure_class_name,
            )
        except ConceptStructureGeneratorError as exc:
            msg = (
                f"Error generating structure class for concept '{concept_code}' refining '{refined_structure_class_name}' "
                f"in domain '{domain_code}': {exc}"
            )
            raise ConceptFactoryError(msg) from exc

        # Register the generated class
        KajsonManager.get_class_registry().register_class(the_generated_class)

        return concept_code, current_refine

    @classmethod
    def make_from_blueprint(
        cls,
        domain_code: str,
        concept_code: str,
        blueprint_or_string_description: ConceptBlueprint | str,
    ) -> Concept:
        # Determine declaration type
        declaration_type: ConceptDeclarationType
        if isinstance(blueprint_or_string_description, str):
            declaration_type = ConceptDeclarationType.STRING
        elif blueprint_or_string_description.structure is not None:
            if isinstance(blueprint_or_string_description.structure, str):
                declaration_type = ConceptDeclarationType.STRUCTURE_WITH_CLASSNAME
            else:
                declaration_type = ConceptDeclarationType.BLUEPRINT_WITH_STRUCTURE
        elif blueprint_or_string_description.refines is not None:
            declaration_type = ConceptDeclarationType.REFINES
        else:
            declaration_type = ConceptDeclarationType.BASIC_BLUEPRINT

        domain_and_concept_code = cls.make_domain_and_concept_code_from_concept_ref_or_code(
            concept_ref_or_code=concept_code,
            domain_code=domain_code,
        )

        match declaration_type:
            case ConceptDeclarationType.STRING:
                structure_class_name, _ = cls._handle_basic_blueprint(
                    concept_code=concept_code,
                    domain_code=domain_code,
                )
                return Concept(
                    domain_code=domain_and_concept_code.domain_code,
                    code=domain_and_concept_code.concept_code,
                    description=cast("str", blueprint_or_string_description),
                    structure_class_name=structure_class_name,
                )

            case ConceptDeclarationType.BASIC_BLUEPRINT:
                structure_class_name, refines = cls._handle_basic_blueprint(
                    concept_code=concept_code,
                    domain_code=domain_code,
                )
                return Concept(
                    domain_code=domain_and_concept_code.domain_code,
                    code=domain_and_concept_code.concept_code,
                    description=cast("ConceptBlueprint", blueprint_or_string_description).description,
                    structure_class_name=structure_class_name,
                    refines=refines,
                )

            case ConceptDeclarationType.STRUCTURE_WITH_CLASSNAME:
                blueprint = cast("ConceptBlueprint", blueprint_or_string_description)
                return Concept(
                    domain_code=domain_and_concept_code.domain_code,
                    code=domain_and_concept_code.concept_code,
                    description=blueprint.description,
                    structure_class_name=cls._handle_structure_with_classname(
                        blueprint=blueprint,
                        concept_code=concept_code,
                        domain_code=domain_code,
                    ),
                    refines=None,
                )

            case ConceptDeclarationType.BLUEPRINT_WITH_STRUCTURE:
                blueprint = cast("ConceptBlueprint", blueprint_or_string_description)
                return Concept(
                    domain_code=domain_and_concept_code.domain_code,
                    code=domain_and_concept_code.concept_code,
                    description=blueprint.description,
                    structure_class_name=cls._handle_blueprint_with_structure(
                        blueprint=blueprint,
                        concept_code=concept_code,
                        domain_code=domain_code,
                    ),
                    refines=None,
                )

            case ConceptDeclarationType.REFINES:
                blueprint = cast("ConceptBlueprint", blueprint_or_string_description)
                structure_class_name, current_refine = cls._handle_refines(
                    blueprint=blueprint,
                    concept_code=concept_code,
                    domain_code=domain_code,
                )
                return Concept(
                    domain_code=domain_and_concept_code.domain_code,
                    code=domain_and_concept_code.concept_code,
                    description=blueprint.description,
                    structure_class_name=structure_class_name,
                    refines=current_refine,
                )
