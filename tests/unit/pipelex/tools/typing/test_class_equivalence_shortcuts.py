from typing import Any

import pydantic.main as pydantic_main
import pytest
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema
from pytest_mock import MockerFixture

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.tools.typing.class_utils import are_classes_equivalent, normalize_properties_for_comparison


class Person(BaseModel):
    name: str
    age: int


class PersonTwin(BaseModel):
    name: str
    age: int


class Invoice(BaseModel):
    title: str
    summary: str
    score: int
    flag: bool


class Titled(BaseModel):
    title: str


class TitledByAlias(BaseModel):
    name: str = Field(alias="title")


class TitledByAliasChoices(BaseModel):
    name: str = Field(validation_alias=AliasChoices(AliasPath("payload", 0), "title"))


class UpperTitled(BaseModel):
    TITLE: str


class TitledByGenerator(BaseModel):
    model_config = ConfigDict(alias_generator=str.upper)
    title: str


class NamedWithSkippedSecret(BaseModel):
    name: str
    secret: SkipJsonSchema[int] = 0


class Named(BaseModel):
    name: str


class CodeAliasedAsRef(BaseModel):
    code: str = Field(alias="ref")


class Coded(BaseModel):
    code: str


class TestClassEquivalenceShortcuts:
    def test_a_class_is_equivalent_to_itself_without_a_schema(self, mocker: MockerFixture):
        """Identity answers True before any JSON schema is generated."""
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        assert are_classes_equivalent(Person, class_2=Person) is True
        assert are_classes_equivalent(ImageContent, class_2=ImageContent) is True
        assert schema_spy.call_count == 0

    @pytest.mark.parametrize(
        ("class_1", "class_2"),
        [
            pytest.param(Person, Invoice, id="disjoint-fields"),
            pytest.param(Person, Named, id="subset-of-fields"),
            pytest.param(Invoice, ImageContent, id="structure-vs-native-image"),
        ],
    )
    def test_different_property_sets_are_rejected_without_a_schema(self, mocker: MockerFixture, class_1: type[Any], class_2: type[Any]):
        """Two models whose published property names differ are not equivalent, and that is settled without model_json_schema."""
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        assert are_classes_equivalent(class_1, class_2=class_2) is False
        assert are_classes_equivalent(class_2, class_2=class_1) is False
        assert schema_spy.call_count == 0

    @pytest.mark.parametrize(
        ("class_1", "class_2"),
        [
            pytest.param(TitledByAlias, Titled, id="alias"),
            pytest.param(TitledByAliasChoices, Titled, id="alias-choices-first-single-string-path"),
            pytest.param(TitledByGenerator, UpperTitled, id="alias-generator"),
        ],
    )
    def test_an_aliased_pair_the_full_comparison_accepts_stays_equivalent(self, class_1: type[BaseModel], class_2: type[BaseModel]):
        """Field names differ but published names match: the shortcut must not reject what the schemas accept."""
        schema_1 = class_1.model_json_schema()
        schema_2 = class_2.model_json_schema()
        assert normalize_properties_for_comparison(schema_1["properties"]) == normalize_properties_for_comparison(schema_2["properties"])
        assert set(class_1.model_fields) != set(class_2.model_fields)

        assert are_classes_equivalent(class_1, class_2=class_2) is True

    @pytest.mark.parametrize(
        ("class_1", "class_2", "expected"),
        [
            pytest.param(NamedWithSkippedSecret, Named, True, id="skip-json-schema-field"),
            pytest.param(CodeAliasedAsRef, Coded, False, id="same-field-names-different-aliases"),
        ],
    )
    def test_undecidable_pairs_fall_through_to_the_full_comparison(
        self, mocker: MockerFixture, class_1: type[Any], class_2: type[Any], expected: bool
    ):
        """A skipped field hides from the schema and an alias changes only one naming: neither may be decided by the shortcut."""
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        assert are_classes_equivalent(class_1, class_2=class_2) is expected
        assert schema_spy.call_count == 2

    def test_a_genuinely_equivalent_pair_of_distinct_classes_is_equivalent(self, mocker: MockerFixture):
        """Same published property names: the shortcut steps aside and the full comparison says True."""
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        assert are_classes_equivalent(Person, class_2=PersonTwin) is True
        assert schema_spy.call_count == 2
