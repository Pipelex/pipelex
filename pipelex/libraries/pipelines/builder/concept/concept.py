from typing import Any, Dict, Optional, Union, cast

from pydantic import ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint as ConceptBlueprintCore
from pipelex.core.concepts.concept_blueprint import ConceptBlueprintError, ConceptStructureBlueprintError, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.concept_blueprint import ConceptStructureBlueprint as ConceptStructureBlueprintCore
from pipelex.core.concepts.concept_native import NativeConceptEnum, is_native_concept
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringError, ConceptStringOrConceptCodeError
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.tools.misc.string_utils import is_pascal_case
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_list


class ConceptSpec(StructuredContent):
    the_concept_code: str = Field(description="Concept code. Must be PascalCase.")
    description: str = Field(description="Description of the concept, in natural language.")
    structure: str = Field(
        description="A description of a dict with fieldnames as keys, and values being a dict with: definition, type, required, default_value"
    )
    refines: Optional[str] = Field(
        default=None,
        description="The native concept this concept extends (Text, Image, PDF, TextAndImages, Number, Page) "
        "in PascalCase format. Cannot be used together with 'structure'.",
    )


class ConceptStructureBlueprint(StructuredContent):
    """Blueprint defining a field in the structure of a concept, used as a Pydantic V2 model.

    This class represents the schema for a single field in a concept's structure. It supports
    various field types including text, list, dict, integer, boolean, number, and date, as well
    as choice-based fields (enums).

    Attributes:
        the_field_name: Field name. Must be snake_case.
        definition: Natural language description of the field's purpose and usage.
        type: The field's data type.
        required: Whether the field is mandatory. Defaults to True unless explicitly set to False.
        default_value: Default value for the field. Must match the specified type, and for choice
                      fields must be one of the valid choices. When provided, type must be specified
                      (unless choices are provided).

    Validation Rules:
        3. Default values: When default_value is provided:
           - For typed fields: type must be specified and default_value must match that type
           - Type validation includes: text (str), integer (int), boolean (bool),
             number (int/float), dict (dict)

    Raises:
        ConceptStructureBlueprintError: When validation rules are violated.
    """

    definition: str
    type: Optional[ConceptStructureBlueprintFieldType] = Field(default=None, description="The type of the field.")
    item_type: Optional[str] = None
    # key_type: Optional[str] = Field(default=None, description="When type is 'dict', key_type must not be empty.")
    # value_type: Optional[str] = Field(default=None, description="When type is 'dict', value_type must not be empty.")
    # choices: Optional[List[str]] = Field(default=None, description="If type is None, choices must not be empty and contain elements.
    #  it is an enum field.")
    required: Optional[bool] = True
    default_value: Optional[Any] = None

    # TODO: date translator for default_value

    @model_validator(mode="after")
    def validate_structure_blueprint(self) -> Self:
        """Validate the structure blueprint according to type rules."""
        # If type is None (array), choices must not be None
        # if self.type is None and not self.choices:
        #     raise ConceptStructureBlueprintError(
        #         f"When type is None (array), choices must not be empty. Actual type: {self.type}, choices: {self.choices}"
        #     )

        # # If type is "dict", key_type and value_type must not be empty
        # if self.type == ConceptStructureBlueprintFieldType.DICT:
        #     if not self.key_type:
        #         raise ConceptStructureBlueprintError(
        #             f"When type is '{ConceptStructureBlueprintFieldType.DICT}', key_type must not be empty. Actual key_type: {self.key_type}"
        #         )
        #     if not self.value_type:
        #         raise ConceptStructureBlueprintError(
        #             f"When type is '{ConceptStructureBlueprintFieldType.DICT}', value_type must not be empty. Actual value_type: {self.value_type}"
        #         )

        # Check when default_value is not None, type is not None (except for choice fields)
        # if self.default_value is not None and self.type is None and not self.choices:
        #     raise ConceptStructureBlueprintError(
        #         f"When default_value is not None, type must be specified (unless choices are provided). "
        #         f"Actual type: {self.type}, default_value: {self.default_value}, choices: {self.choices}"
        #     )

        # Check default_value type is the same as type
        if self.default_value is not None and self.type is not None:
            self._validate_default_value_type()

        # Check default_value is valid for choice fields
        # if self.default_value is not None and self.type is None and self.choices:
        #     if self.default_value not in self.choices:
        #         raise ConceptStructureBlueprintError(
        #             f"default_value must be one of the valid choices. Got '{self.default_value}', valid choices: {self.choices}"
        #         )

        return self

    def _validate_default_value_type(self) -> None:
        """Validate that default_value matches the specified type."""
        if self.type is None or self.default_value is None:
            return

        match self.type:
            case ConceptStructureBlueprintFieldType.TEXT:
                if not isinstance(self.default_value, str):
                    self._raise_type_mismatch_error("str", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.INTEGER:
                if not isinstance(self.default_value, int):
                    self._raise_type_mismatch_error("int", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.BOOLEAN:
                if not isinstance(self.default_value, bool):
                    self._raise_type_mismatch_error("bool", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.NUMBER:
                if not isinstance(self.default_value, (int, float)):
                    self._raise_type_mismatch_error("number (int or float)", type(self.default_value).__name__)
            case _:
                raise ConceptStructureBlueprintError(f"Unknown type: {self.type} in structure blueprint with definition: {self.definition}")

    def _raise_type_mismatch_error(self, expected_type_name: str, actual_type_name: str) -> None:
        """Raise a type mismatch error with consistent formatting."""
        raise ConceptStructureBlueprintError(
            f"default_value type mismatch: expected {expected_type_name} for type '{self.type}', but got {actual_type_name}"
        )

    def to_core_blueprint(self) -> ConceptStructureBlueprintCore:
        """Convert this ConceptStructureBlueprint to the core ConceptStructureBlueprint."""
        return ConceptStructureBlueprintCore(
            definition=self.definition,
            type=self.type,
            item_type=self.item_type,
            # key_type=self.key_type,
            # value_type=self.value_type,
            # choices=self.choices,
            required=self.required,
            default_value=self.default_value,
        )


class ConceptStructureSpecBlueprint(ConceptStructureBlueprint):
    the_field_name: str = Field(description="Field name. Must be snake_case.")


class ConceptBlueprint(StructuredContent):
    """Blueprint defining a concept that can be used in the Pipelex framework.

    A concept represents a structured data type that can either define its own structure
    or refine an existing native concept. Concepts are fundamental building blocks in
    Pipelex workflows for data validation and transformation.

    Attributes:
        the_concept_code: Concept code. Must be PascalCase.
        definition: Natural language description of what the concept represents and its purpose.
        structure: The concept's field structure. Can be either:
                  - A string referring to another concept
                  - A dictionary where keys are field names (in snake_case) and values are
                    either strings (concept references) or ConceptStructureBlueprint instances
                  Cannot be used together with 'refines'.
        refines: The native concept this concept extends (Text, Image, PDF, TextAndImages,
                Number, Page) in PascalCase format. Cannot be used together with 'structure'.

    Validation Rules:
        1. Mutual exclusivity: A concept must have either 'structure' or 'refines', but not both.
        2. Field names: When structure is a dict, all keys must be valid snake_case identifiers.
        3. Concept codes: Must be in PascalCase format (letters and numbers only, starting
           with uppercase, no dots).
        4. Concept strings: Format is "domain.ConceptCode" where domain is lowercase and
           ConceptCode is PascalCase.
        5. Native concepts: When refining, must be one of the valid native concepts.
        6. Structure values: In structure dict, values must be either valid concept strings
           or ConceptStructureBlueprint instances.


    Raises:
        ConceptBlueprintError: When validation rules are violated.
        ConceptCodeError: When concept code format is invalid.
        ConceptStringError: When concept string format is invalid.
    """

    model_config = ConfigDict(extra="forbid")

    definition: str
    structure: Optional[Union[str, Dict[str, Union[str, ConceptStructureBlueprint]]]] = None
    refines: Optional[str] = None

    @classmethod
    def is_native_concept_code(cls, concept_code: str) -> bool:
        ConceptBlueprint.validate_concept_code(concept_code=concept_code)
        return concept_code in [native_concept.value for native_concept in NativeConceptEnum]

    @classmethod
    def is_native_concept_string_or_concept_code(cls, concept_string_or_concept_code: str) -> bool:
        if "." in concept_string_or_concept_code:
            domain, concept_code = concept_string_or_concept_code.split(".", 1)
            if domain == SpecialDomain.NATIVE.value and concept_code in [native_concept.value for native_concept in NativeConceptEnum]:
                return True
        else:
            if is_native_concept(concept_string_or_concept_code):
                return True
        return False

    @classmethod
    def validate_concept_code(cls, concept_code: str) -> None:
        if not is_pascal_case(concept_code):
            raise ConceptCodeError(
                f"Concept code '{concept_code}' must be PascalCase (letters and numbers only, starting with uppercase, without `.`)"
            )

    @classmethod
    def validate_concept_string_or_concept_code(cls, concept_string_or_concept_code: str) -> None:
        if concept_string_or_concept_code.count(".") > 1:
            raise ConceptStringOrConceptCodeError(
                f"concept_string_or_concept_code '{concept_string_or_concept_code}' is invalid. "
                "It should either contain a domain in snake_case and a concept code in PascalCase separated by one dot, "
                "or be a concept code in PascalCase."
            )

        elif concept_string_or_concept_code.count(".") == 1:
            domain, concept_code = concept_string_or_concept_code.split(".")
            DomainBlueprint.validate_domain_code(code=domain)
            cls.validate_concept_code(concept_code=concept_code)
        else:
            cls.validate_concept_code(concept_code=concept_string_or_concept_code)

    @staticmethod
    def validate_concept_string(concept_string: str) -> None:
        """Validate that a concept code follows PascalCase convention."""
        if "." not in concept_string:
            raise ConceptStringError(
                f"Concept string '{concept_string}' is invalid. It should contain a domain in snake_case "
                "and a concept code in PascalCase separated by one dot."
            )
        elif concept_string.count(".") > 1:
            raise ConceptStringError(
                f"Concept string '{concept_string}' is invalid. It should contain a domain in snake_case "
                "and a concept code in PascalCase separated by one dot."
            )
        else:
            domain, concept_code = concept_string.split(".", 1)

        # Validate domain
        DomainBlueprint.validate_domain_code(domain)

        # Validate concept code
        if not is_pascal_case(concept_code):
            raise ConceptCodeError(
                f"Concept code '{concept_code}' must be PascalCase (letters and numbers only, starting with uppercase, without `.`)"
            )

        # Validate that if the concept code is among the native concepts, the domain MUST be native.
        if concept_code in [native_concept.value for native_concept in NativeConceptEnum]:
            if domain != SpecialDomain.NATIVE.value:
                raise ConceptStringError(
                    f"Concept string '{concept_string}' is invalid. "
                    f"Concept code '{concept_code}' is a native concept, so the domain must be '{SpecialDomain.NATIVE.value}', "
                    f"or nothing, but not '{domain}'"
                )

        # Validate that if the domain is native, the concept code is a native concept
        if domain == SpecialDomain.NATIVE.value:
            if concept_code not in [native_concept.value for native_concept in NativeConceptEnum]:
                raise ConceptStringError(
                    f"Concept string '{concept_string}' is invalid. "
                    f"Concept code '{concept_code}' is not a native concept, so the domain must not be '{SpecialDomain.NATIVE.value}'."
                )

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: Optional[str] = None) -> Optional[str]:
        if refines is not None:
            if not is_native_concept(refines):
                raise ConceptBlueprintError(f"Forbidden to refine a non-native concept: '{refines}'. Refining non-native concepts will come soon.")
            cls.validate_concept_string_or_concept_code(concept_string_or_concept_code=refines)
        return refines

    @model_validator(mode="before")
    def model_validate_blueprint(cls, values: Union[Dict[str, Any], "ConceptBlueprint"]) -> Union[Dict[str, Any], "ConceptBlueprint"]:
        if isinstance(values, dict):
            if values.get("refines") and values.get("structure"):
                raise ConceptBlueprintError(
                    f"Forbidden to have refines and structure at the same time: `{values.get('refines')}` "
                    f"and `{values.get('structure')}` for concept that has the definition `{values.get('definition')}`"
                )
        elif hasattr(values, "refines") and hasattr(values, "structure"):
            if has_more_than_one_among_attributes_from_list(obj=values, attributes_list=["refines", "structure"]):
                raise ConceptBlueprintError(
                    f"Forbidden to have refines and structure at the same time: `{values.refines}` "
                    f"and `{values.structure}` for concept that has the definition `{values.definition}`"
                )
        return values

    def to_core_blueprint(self) -> ConceptBlueprintCore:
        """Convert this ConceptBlueprint to the original core ConceptBlueprint."""
        converted_structure: Optional[Union[str, Dict[str, Union[str, ConceptStructureBlueprintCore]]]] = None
        if self.structure:
            # Convert structure dict with ConceptStructureBlueprint objects to ConceptStructureBlueprintCore objects
            converted_structure = {}
            if isinstance(self.structure, str):
                converted_structure = self.structure
            else:
                for field_name, field_spec in cast(Dict[str, ConceptStructureBlueprint], self.structure).items():
                    converted_structure[field_name] = field_spec.to_core_blueprint()

        return ConceptBlueprintCore(definition=self.definition, structure=converted_structure, refines=self.refines)


class ConceptSpecBlueprint(ConceptBlueprint):
    the_concept_code: str = Field(description="Concept code. Must be PascalCase.")


async def create_concept_spec_blueprint(working_memory: WorkingMemory) -> ConceptSpecBlueprint:
    """Create a ConceptSpecBlueprint manually from ConceptSpec and ConceptStructureSpecBlueprint."""
    # Get the inputs from working memory
    concept_spec = working_memory.get_stuff_as(name="concept_spec", content_type=ConceptSpec)
    concept_spec_structures_stuff = working_memory.get_stuff_as_list(name="concept_spec_structures", item_type=ConceptStructureSpecBlueprint)

    structure_dict: Dict[str, Union[str, ConceptStructureBlueprint]] = {}
    for structure_item in concept_spec_structures_stuff.items:
        structure_blueprint = ConceptStructureBlueprint(
            definition=structure_item.definition,
            type=structure_item.type,
            item_type=structure_item.item_type,
            # key_type=structure_item.key_type,
            # value_type=structure_item.value_type,
            # choices=structure_item.choices,
            required=structure_item.required,
            default_value=structure_item.default_value,
        )
        structure_dict[structure_item.the_field_name] = structure_blueprint

    # Create the ConceptSpecBlueprint
    concept_spec_blueprint = ConceptSpecBlueprint(
        the_concept_code=concept_spec.the_concept_code,
        definition=concept_spec.description,
        structure=structure_dict,
        refines=concept_spec.refines,
    )

    return concept_spec_blueprint
