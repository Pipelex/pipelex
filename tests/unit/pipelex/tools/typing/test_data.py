from typing import Annotated, Any, ClassVar, TypeVar, cast

from annotated_types import Gt
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field
from pydantic.config import JsonDict
from pydantic.json_schema import SkipJsonSchema
from pydantic.types import Strict
from pydantic_core import PydanticOmit
from typing_extensions import TypeAliasType

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

# Plain models: built only from the vocabulary the class-equivalence shortcut reads.


class Person(BaseModel):
    name: str
    age: int


class PersonTwin(BaseModel):
    name: str
    age: int


class PersonWithTextAge(BaseModel):
    name: str
    age: str


class Invoice(BaseModel):
    title: str
    summary: str
    score: int
    flag: bool


class Named(BaseModel):
    name: str


class Titled(BaseModel):
    title: str


class ConstrainedPerson(BaseModel):
    name: str = Field(min_length=1, strict=True)
    age: int = Field(default=1, gt=0)
    scores: list[Annotated[int, Gt(0), Strict()]] = Field(default_factory=empty_list_factory_of(int))


class TreeNode(BaseModel):
    label: str
    children: list["TreeNode"] | None = None


# Shapes a deny-list walk counted as published, though pydantic drops them from the JSON schema: each model here
# publishes the same properties as `Named`, so it is equivalent to it.

_T = TypeVar("_T")
SkippedGeneric = TypeAliasType("SkippedGeneric", SkipJsonSchema[_T], type_params=(_T,))
SkippedInteger = TypeAliasType("SkippedInteger", SkipJsonSchema[int])


def omit_model_title(_model_class: type) -> str:
    raise PydanticOmit


def omit_model_schema_extra(_model_class: type, _schema: JsonDict) -> None:
    raise PydanticOmit


class HiddenByTitle(BaseModel):
    model_config = ConfigDict(model_title_generator=omit_model_title)
    value: int


class HiddenBySchemaExtraClassmethod(BaseModel):
    model_config = ConfigDict(json_schema_extra=cast("Any", classmethod(omit_model_schema_extra)))
    value: int


class HiddenByTypedExtras(BaseModel):
    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, SkipJsonSchema[int]]  # pyright: ignore[reportIncompatibleVariableOverride]
    value: int


class NamedWithSkippedGeneric(BaseModel):
    name: str
    hidden: SkippedGeneric[int] = 0


class NamedWithSkippedInteger(BaseModel):
    name: str
    hidden: SkippedInteger = 0


class NamedWithHiddenByTitle(BaseModel):
    name: str
    hidden: HiddenByTitle | None = None


class NamedWithHiddenListByTitle(BaseModel):
    name: str
    hidden: list[HiddenByTitle] = Field(default_factory=empty_list_factory_of(HiddenByTitle))


class NamedWithHiddenBySchemaExtraClassmethod(BaseModel):
    name: str
    hidden: HiddenBySchemaExtraClassmethod | None = None


class NamedWithHiddenByTypedExtras(BaseModel):
    name: str
    hidden: HiddenByTypedExtras | None = None


class OmittingDefault:
    """A value whose type drops any property it is the default of: pydantic encodes a default through its own type."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:  # ruff: ignore[bad-dunder-method-name] - pydantic hook
        raise PydanticOmit


class NamedWithOmittingDefault(BaseModel):
    name: str
    hidden: int = cast("int", OmittingDefault())


class NamedWithSkippedField(BaseModel):
    name: str
    hidden: SkipJsonSchema[int] = 0


# Shapes whose JSON schema cannot be generated: the error must reach the caller, not be hidden behind a `False`.


def integer_model_title(_model_class: type) -> Any:
    return 42


class TitledByOmission(BaseModel):
    model_config = ConfigDict(model_title_generator=omit_model_title)
    name: str
    age: int


class WithOmittingTypedExtras(BaseModel):
    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, SkipJsonSchema[int]]  # pyright: ignore[reportIncompatibleVariableOverride]
    name: str
    age: int


class TitledByInteger(BaseModel):
    model_config = ConfigDict(model_title_generator=integer_model_title)
    value: int


class NamedWithTitledByInteger(BaseModel):
    name: str
    nested: TitledByInteger | None = None


# Aliases: a published name that is not the field name, so the shortcut must leave these to the schemas.


class TitledByAlias(BaseModel):
    name: str = Field(alias="title")


class TitledByAliasChoices(BaseModel):
    name: str = Field(validation_alias=AliasChoices(AliasPath("payload", 0), "title"))


class UpperTitled(BaseModel):
    TITLE: str


class TitledByGenerator(BaseModel):
    model_config = ConfigDict(alias_generator=str.upper)
    title: str


class CodeAliasedAsRef(BaseModel):
    code: str = Field(alias="ref")


class Coded(BaseModel):
    code: str


class GeneratedStructureTestCases:
    DOMAIN: ClassVar[str] = "shortcut"
    BLUEPRINTS: ClassVar[dict[str, dict[str, ConceptStructureBlueprint]]] = {
        "Scorecard": {
            "title": ConceptStructureBlueprint(description="The title", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "summary": ConceptStructureBlueprint(description="The summary", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "score": ConceptStructureBlueprint(description="The score", type=ConceptStructureBlueprintFieldType.INTEGER, required=True),
            "flag": ConceptStructureBlueprint(description="The flag", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=True),
        },
        "Measurement": {
            "value": ConceptStructureBlueprint(description="The value", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "unit": ConceptStructureBlueprint(description="The unit", choices=["cm", "m"], required=True),
            "taken_on": ConceptStructureBlueprint(description="The day", type=ConceptStructureBlueprintFieldType.DATE),
            "taken_at": ConceptStructureBlueprint(description="The moment", type=ConceptStructureBlueprintFieldType.DATETIME),
            "time_of_day": ConceptStructureBlueprint(description="The time of day", type=ConceptStructureBlueprintFieldType.TIME),
            "notes": ConceptStructureBlueprint(description="Notes", type=ConceptStructureBlueprintFieldType.TEXT, default_value="none"),
        },
        "Tagged": {
            "tags": ConceptStructureBlueprint(description="The tags", type=ConceptStructureBlueprintFieldType.LIST, item_type="text"),
            "attributes": ConceptStructureBlueprint(
                description="The attributes", type=ConceptStructureBlueprintFieldType.DICT, key_type="text", value_type="integer"
            ),
            "payload": ConceptStructureBlueprint(description="Anything", type=ConceptStructureBlueprintFieldType.LIST),
        },
        "Illustrated": {
            "picture": ConceptStructureBlueprint(
                description="The picture", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="native.Image", required=True
            ),
            "gallery": ConceptStructureBlueprint(
                description="More pictures", type=ConceptStructureBlueprintFieldType.LIST, item_type="concept", item_concept_ref="native.Image"
            ),
        },
        "Node": {
            "label": ConceptStructureBlueprint(description="The label", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "children": ConceptStructureBlueprint(
                description="The children", type=ConceptStructureBlueprintFieldType.LIST, item_type="concept", item_concept_ref="shortcut.Node"
            ),
        },
        "Quote": {
            "text": ConceptStructureBlueprint(description="The text", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
        },
    }
