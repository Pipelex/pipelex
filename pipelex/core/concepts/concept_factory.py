from typing import NamedTuple, cast

from kajson.class_registry_abstract import ClassRegistryAbstract
from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.exceptions import (
    ConceptFactoryError,
    ConceptRefineError,
    ConceptStringError,
)
from pipelex.core.concepts.helpers import make_qualified_structure_class_name, normalize_structure_blueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.stuffs.text_content import TextContent
from pipelex.types import StrEnum


def _get_class_registry() -> ClassRegistryAbstract:
    """Lazy import to break circular dependency with hub.py."""
    import importlib  # noqa: PLC0415

    hub = importlib.import_module("pipelex.hub")
    return hub.get_class_registry()  # type: ignore[no-any-return]


class StructureNameAndRefine(NamedTuple):
    structure_class_name: str
    refine_string: str | None


class ConceptDeclarationType(StrEnum):
    """Enum representing the 5 ways a concept can be declared in MTHDS files.

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
            case NativeConceptCode.HTML:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="HTML content",
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
            case NativeConceptCode.SEARCH_RESULT:
                return Concept(
                    code=native_concept_code,
                    domain_code=SpecialDomain.NATIVE,
                    description="A search result with answer and sources",
                    structure_class_name=structure_class_name,
                )

    @classmethod
    def make_domain_and_concept_code_from_concept_ref_or_code(
        cls,
        concept_ref_or_code: str,
        domain_code: str | None = None,
    ) -> DomainAndConceptCode:
        # Handle cross-package references (alias->domain.ConceptCode)
        if QualifiedRef.has_cross_package_prefix(concept_ref_or_code):
            alias, remainder = QualifiedRef.split_cross_package_ref(concept_ref_or_code)
            ref = QualifiedRef.parse_concept_ref(remainder)
            if ref.domain_path is None:
                msg = f"Cross-package concept ref '{concept_ref_or_code}' must include a domain"
                raise ConceptFactoryError(msg)
            return DomainAndConceptCode(domain_code=f"{alias}->{ref.domain_path}", concept_code=ref.local_code)

        if "." not in concept_ref_or_code and not domain_code:
            msg = f"Not enough information to make a domain and concept code from '{concept_ref_or_code}'"
            raise ConceptFactoryError(msg)
        try:
            validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
        except ConceptStringError as exc:
            msg = f"Concept string or code '{concept_ref_or_code}' is not a valid concept string or code"
            raise ConceptFactoryError(msg) from exc

        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
            native_concept_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref_or_code)
            ref = QualifiedRef.parse(native_concept_ref)
            return DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code=ref.local_code)

        if "." in concept_ref_or_code:
            ref = QualifiedRef.parse(concept_ref_or_code)
            assert ref.domain_path is not None
            return DomainAndConceptCode(domain_code=ref.domain_path, concept_code=ref.local_code)
        elif domain_code:
            return DomainAndConceptCode(domain_code=domain_code, concept_code=concept_ref_or_code)
        else:
            msg = f"Not enough information to make a domain and concept code from '{concept_ref_or_code}'"
            raise ConceptFactoryError(msg)

    @classmethod
    def make_concept_ref_with_domain(cls, domain_code: str, concept_code: str) -> str:
        return f"{domain_code}.{concept_code}"

    @classmethod
    def make_concept_ref_with_domain_from_concept_ref_or_code(cls, domain_code: str, concept_ref_or_code: str) -> str:
        input_domain_and_code = cls.make_domain_and_concept_code_from_concept_ref_or_code(
            concept_ref_or_code=concept_ref_or_code,
            domain_code=domain_code,
        )

        return cls.make_concept_ref_with_domain(
            domain_code=input_domain_and_code.domain_code,
            concept_code=input_domain_and_code.concept_code,
        )

    @classmethod
    def make_refine(cls, refine: str, domain_code: str) -> str:
        """Validate and normalize a refine string.

        If the refine is a native concept code without domain (e.g., 'Text'),
        it will be normalized to include the native domain prefix (e.g., 'native.Text').
        If the refine is a local concept code without domain (e.g., 'MyCustomConcept'),
        it will be prefixed with the given domain_code.
        Cross-package refs (e.g., 'alias->domain.Concept') are passed through as-is.

        Args:
            refine: The refine string to validate and normalize
            domain_code: The domain code to use for prefixing local concept references

        Returns:
            The normalized refine string with domain prefix

        Raises:
            ConceptFactoryError: If the refine is invalid

        """
        # Cross-package refs pass through unchanged
        if QualifiedRef.has_cross_package_prefix(refine):
            return refine
        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=refine):
            return NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=refine)
        elif "." in refine:
            return refine
        else:
            return f"{domain_code}.{refine}"

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

        Args:
            blueprint: The concept blueprint
            concept_code: The concept code
            domain_code: The domain code

        Returns:
            The structure class name (which is the concept_code)
        """
        if not isinstance(blueprint.structure, dict):
            msg = f"Expected structure to be a dict, got {type(blueprint.structure)}"
            raise ConceptFactoryError(msg)

        # Normalize the structure blueprint to ensure all values are ConceptStructureBlueprint objects
        normalized_structure = normalize_structure_blueprint(blueprint.structure)

        qualified_class_name = make_qualified_structure_class_name(domain_code, concept_code)
        try:
            _, the_generated_class = StructureGenerator(local_domain=domain_code).generate_from_structure_blueprint(
                class_name=qualified_class_name,
                structure_blueprint=normalized_structure,
                description=blueprint.description,
            )
        except ConceptStructureGeneratorError as exc:
            msg = f"Error generating python code for structure class of concept '{concept_code}' in domain '{domain_code}': {exc}"
            raise ConceptFactoryError(msg) from exc

        # Register the generated class
        _get_class_registry().register_class(the_generated_class)

        return qualified_class_name

    @classmethod
    def _handle_basic_blueprint(
        cls,
        concept_code: str,
        domain_code: str,
        description: str,
    ) -> StructureNameAndRefine:
        """Handle BASIC_BLUEPRINT declaration type."""
        qualified_class_name = make_qualified_structure_class_name(domain_code, concept_code)

        # Check if a valid structure class already exists — first by bare concept_code
        # (for pre-existing Python classes registered under their own name), then by
        # qualified name (for previously generated dynamic classes)
        if Concept.is_valid_structure_class(structure_class_name=concept_code):
            return StructureNameAndRefine(structure_class_name=concept_code, refine_string=None)
        if Concept.is_valid_structure_class(structure_class_name=qualified_class_name):
            return StructureNameAndRefine(structure_class_name=qualified_class_name, refine_string=None)

        # Because native concepts have structure class names diffrent than other (with "Content")
        if concept_code in NativeConceptCode.values_list():
            return StructureNameAndRefine(
                structure_class_name=NativeConceptCode.TEXT.structure_class_name,
                refine_string=NativeConceptCode.TEXT.concept_ref,
            )

        try:
            _, the_generated_class = StructureGenerator().generate_from_structure_blueprint(
                class_name=qualified_class_name,
                structure_blueprint={},
                base_class_name=TextContent.__name__,
                description=description,
            )
        except ConceptStructureGeneratorError as exc:
            msg = f"Error generating structure class for concept '{concept_code}' in domain '{domain_code}': {exc}"
            raise ConceptFactoryError(msg) from exc
        # Register the generated class
        _get_class_registry().register_class(the_generated_class)

        return StructureNameAndRefine(structure_class_name=qualified_class_name, refine_string=NativeConceptCode.TEXT.concept_ref)

    @classmethod
    def _handle_refines(
        cls,
        blueprint: ConceptBlueprint,
        concept_code: str,
        domain_code: str,
    ) -> StructureNameAndRefine:
        """Handle REFINES declaration type.

        Concept refines another concept - generate a new class that inherits from the refined
        structure class.
        """
        if blueprint.refines is None:
            msg = "Expected refines to be set"
            raise ConceptFactoryError(msg)

        try:
            current_refine = cls.make_refine(refine=blueprint.refines, domain_code=domain_code)
        except ConceptRefineError as exc:
            msg = f"Could not validate refine '{blueprint.refines}' for concept '{concept_code}' in domain '{domain_code}': {exc}"
            raise ConceptFactoryError(msg) from exc

        qualified_class_name = make_qualified_structure_class_name(domain_code, concept_code)

        # Cross-package refines: base class isn't available locally, so generate
        # a standalone TextContent subclass. The refinement relationship is tracked
        # in the concept model's refines field for runtime compatibility checks.
        if QualifiedRef.has_cross_package_prefix(current_refine):
            try:
                _, the_generated_class = StructureGenerator().generate_from_structure_blueprint(
                    class_name=qualified_class_name,
                    structure_blueprint={},
                    description=blueprint.description,
                )
            except ConceptStructureGeneratorError as exc:
                msg = (
                    f"Error generating structure class for concept '{concept_code}' "
                    f"with cross-package refines '{current_refine}' in domain '{domain_code}': {exc}"
                )
                raise ConceptFactoryError(msg) from exc

            _get_class_registry().register_class(the_generated_class)
            return StructureNameAndRefine(structure_class_name=qualified_class_name, refine_string=current_refine)

        # Get the refined concept's structure class name
        # For native concepts, the structure class name is "ConceptCode" + "Content" (e.g., TextContent)
        # For custom concepts, the structure class name is domain-qualified (e.g., my_domain__Customer)
        refined_ref = QualifiedRef.parse(current_refine)
        refined_concept_code = refined_ref.local_code
        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=current_refine):
            refined_structure_class_name = refined_concept_code + "Content"
        else:
            refined_domain_code = refined_ref.domain_path or domain_code
            refined_structure_class_name = make_qualified_structure_class_name(refined_domain_code, refined_concept_code)

        # Generate a new class that inherits from the refined structure class
        # This creates an empty class that can be extended with additional fields in the future
        try:
            _, the_generated_class = StructureGenerator().generate_from_structure_blueprint(
                class_name=qualified_class_name,
                structure_blueprint={},  # Empty structure - just inherits from refined class
                base_class_name=refined_structure_class_name,
                description=blueprint.description,
            )
        except ConceptStructureGeneratorError as exc:
            msg = (
                f"Error generating structure class for concept '{concept_code}' refining '{refined_structure_class_name}' "
                f"in domain '{domain_code}': {exc}"
            )
            raise ConceptFactoryError(msg) from exc

        # Register the generated class
        _get_class_registry().register_class(the_generated_class)

        return StructureNameAndRefine(structure_class_name=qualified_class_name, refine_string=current_refine)

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
                assert isinstance(blueprint_or_string_description, str)
                structure_class_name, _ = cls._handle_basic_blueprint(
                    concept_code=concept_code,
                    domain_code=domain_code,
                    description=blueprint_or_string_description,
                )
                return Concept(
                    domain_code=domain_and_concept_code.domain_code,
                    code=domain_and_concept_code.concept_code,
                    description=blueprint_or_string_description,
                    structure_class_name=structure_class_name,
                )

            case ConceptDeclarationType.BASIC_BLUEPRINT:
                assert isinstance(blueprint_or_string_description, ConceptBlueprint)
                structure_class_name, refines = cls._handle_basic_blueprint(
                    concept_code=concept_code,
                    domain_code=domain_code,
                    description=blueprint_or_string_description.description,
                )
                return Concept(
                    domain_code=domain_and_concept_code.domain_code,
                    code=domain_and_concept_code.concept_code,
                    description=blueprint_or_string_description.description,
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
