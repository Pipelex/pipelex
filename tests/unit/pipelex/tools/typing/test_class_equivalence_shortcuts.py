import itertools

import pydantic.main as pydantic_main
import pytest
from pydantic import BaseModel
from pydantic_core import PydanticOmit
from pytest_mock import MockerFixture

from pipelex.core.concepts.helpers import make_qualified_structure_class_name
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.mermaid_content import MermaidContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.typing import class_utils
from pipelex.tools.typing.class_utils import are_classes_equivalent
from tests.unit.pipelex.tools.typing.test_data import (
    CodeAliasedAsRef,
    Coded,
    ConstrainedPerson,
    GeneratedStructureTestCases,
    Invoice,
    Named,
    NamedWithHiddenBySchemaExtraClassmethod,
    NamedWithHiddenByTitle,
    NamedWithHiddenByTypedExtras,
    NamedWithHiddenListByTitle,
    NamedWithOmittingAwareDatetime,
    NamedWithOmittingAwareTime,
    NamedWithOmittingDefault,
    NamedWithSkippedField,
    NamedWithSkippedGeneric,
    NamedWithSkippedInteger,
    NamedWithTitledByInteger,
    Person,
    PersonTwin,
    PersonWithTextAge,
    StampedInUtc,
    Titled,
    TitledByAlias,
    TitledByAliasChoices,
    TitledByGenerator,
    TitledByOmission,
    TreeNode,
    UpperTitled,
    WithOmittingTypedExtras,
)

_SHORTCUT_NAME = "_are_property_sets_certainly_different"


def _generate_structure_classes() -> list[type[BaseModel]]:
    """Generate the test structures the way a library load does, resolving their references to each other."""
    generated_classes: dict[str, type[BaseModel]] = {}
    for concept_code, structure_blueprint in GeneratedStructureTestCases.BLUEPRINTS.items():
        class_name = make_qualified_structure_class_name(domain_code=GeneratedStructureTestCases.DOMAIN, concept_code=concept_code)
        _, generated_class = StructureGenerator(local_domain=GeneratedStructureTestCases.DOMAIN).generate_from_structure_blueprint(
            class_name=class_name, structure_blueprint=structure_blueprint
        )
        assert issubclass(generated_class, BaseModel)
        generated_classes[class_name] = generated_class
    for generated_class in generated_classes.values():
        generated_class.model_rebuild(_types_namespace=generated_classes)
        assert generated_class.__pydantic_complete__
    return list(generated_classes.values())


def _content_classes() -> list[type[BaseModel]]:
    """Every native content class pipelex ships as a pydantic model, and a handful of generated structures."""
    native_classes: list[type[BaseModel]] = []
    for native_code in NativeConceptCode:
        structure_class = native_code.structure_class
        if structure_class is not None and issubclass(structure_class, BaseModel) and structure_class not in native_classes:
            native_classes.append(structure_class)
    extra_classes: list[type[BaseModel]] = [StuffContent, StructuredContent, MermaidContent, ListContent, ListContent[TextContent]]
    return [*native_classes, *extra_classes, *_generate_structure_classes()]


class TestClassEquivalenceShortcuts:
    def test_a_class_is_equivalent_to_itself_without_a_schema(self, mocker: MockerFixture):
        """Identity answers True before any JSON schema is generated, plain model or not."""
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        for model_class in (Person, ImageContent, CompositeContent, NamedWithSkippedField, TitledByOmission):
            assert are_classes_equivalent(model_class, class_2=model_class) is True
        assert schema_spy.call_count == 0

    @pytest.mark.parametrize(
        ("class_1", "class_2"),
        [
            pytest.param(Person, Invoice, id="disjoint-fields"),
            pytest.param(Person, Named, id="subset-of-fields"),
            pytest.param(Invoice, ImageContent, id="structure-vs-native-image"),
            pytest.param(ConstrainedPerson, Named, id="inert-constraints-gt-strict-min-length"),
            pytest.param(TreeNode, Titled, id="self-referencing-model"),
            pytest.param(StampedInUtc, Person, id="aware-temporal-defaults-in-stdlib-time-zones"),
        ],
    )
    def test_plain_models_with_different_fields_are_rejected_without_a_schema(
        self, mocker: MockerFixture, class_1: type[BaseModel], class_2: type[BaseModel]
    ):
        """Two plain models whose field names differ are not equivalent, and that is settled without model_json_schema."""
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        assert are_classes_equivalent(class_1, class_2=class_2) is False
        assert are_classes_equivalent(class_2, class_2=class_1) is False
        assert schema_spy.call_count == 0

    @pytest.mark.parametrize(
        ("class_1", "class_2", "expected"),
        [
            pytest.param(Person, PersonTwin, True, id="same-fields-same-types"),
            pytest.param(Person, PersonWithTextAge, False, id="same-fields-different-types"),
        ],
    )
    def test_plain_models_with_the_same_fields_are_decided_by_the_schema(
        self, mocker: MockerFixture, class_1: type[BaseModel], class_2: type[BaseModel], expected: bool
    ):
        """Same field names: the shortcut steps aside and the full schema comparison gives the verdict."""
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        assert are_classes_equivalent(class_1, class_2=class_2) is expected
        assert schema_spy.call_count == 2

    @pytest.mark.parametrize(
        "class_1",
        [
            pytest.param(NamedWithSkippedGeneric, id="subscripted-generic-type-alias-to-skip-json-schema"),
            pytest.param(NamedWithSkippedInteger, id="type-alias-to-skip-json-schema"),
            pytest.param(NamedWithHiddenByTitle, id="nested-model-title-generator-omits"),
            pytest.param(NamedWithHiddenListByTitle, id="list-of-nested-model-title-generator-omits"),
            pytest.param(NamedWithHiddenBySchemaExtraClassmethod, id="nested-json-schema-extra-classmethod-omits"),
            pytest.param(NamedWithHiddenByTypedExtras, id="nested-typed-extras-omit"),
            pytest.param(NamedWithOmittingDefault, id="default-whose-type-omits"),
            pytest.param(NamedWithSkippedField, id="skip-json-schema-field"),
            pytest.param(NamedWithOmittingAwareDatetime, id="datetime-default-whose-time-zone-omits"),
            pytest.param(NamedWithOmittingAwareTime, id="time-default-whose-time-zone-omits"),
        ],
    )
    def test_a_field_pydantic_omits_falls_through_and_stays_equivalent(self, mocker: MockerFixture, class_1: type[BaseModel]):
        """The field names differ from `Named`'s but the published properties do not: the schema path decides, and says True."""
        assert set(class_1.model_fields) != set(Named.model_fields)
        assert set(class_1.model_json_schema()["properties"]) == set(Named.model_json_schema()["properties"])
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        assert are_classes_equivalent(class_1, class_2=Named) is True
        assert are_classes_equivalent(Named, class_2=class_1) is True
        assert schema_spy.call_count == 4

    @pytest.mark.parametrize(
        ("class_1", "class_2", "expected_error"),
        [
            pytest.param(TitledByOmission, Named, PydanticOmit, id="model-title-generator-omits"),
            pytest.param(WithOmittingTypedExtras, Named, PydanticOmit, id="typed-extras-omit"),
            pytest.param(NamedWithTitledByInteger, Person, TypeError, id="nested-model-title-generator-returns-an-integer"),
        ],
    )
    def test_a_schema_that_cannot_be_generated_raises_instead_of_answering(
        self, class_1: type[BaseModel], class_2: type[BaseModel], expected_error: type[BaseException]
    ):
        """Where generating the schema raises, the shortcut does not answer False in its place: the error reaches the caller."""
        assert set(class_1.model_fields) != set(class_2.model_fields)

        with pytest.raises(expected_error):
            are_classes_equivalent(class_1, class_2=class_2)

    @pytest.mark.parametrize(
        ("class_1", "class_2", "expected"),
        [
            pytest.param(TitledByAlias, Titled, True, id="alias"),
            pytest.param(TitledByAliasChoices, Titled, True, id="alias-choices-first-single-string-path"),
            pytest.param(TitledByGenerator, UpperTitled, True, id="alias-generator"),
            pytest.param(CodeAliasedAsRef, Coded, False, id="same-field-names-different-aliases"),
        ],
    )
    def test_an_aliased_field_falls_through_to_the_schema(
        self, mocker: MockerFixture, class_1: type[BaseModel], class_2: type[BaseModel], expected: bool
    ):
        """An alias publishes a property under another name than the field's, so only the schemas can compare it."""
        schema_spy = mocker.spy(pydantic_main, "model_json_schema")

        assert are_classes_equivalent(class_1, class_2=class_2) is expected
        assert schema_spy.call_count == 2

    def test_the_shortcut_agrees_with_the_schema_on_pipelex_content_classes(self, mocker: MockerFixture):
        """Wherever the shortcut answers "certainly different" over pipelex's own content classes, the schema path says not equivalent.

        Both paths are symmetric in their two classes, so each unordered pair is asked once.
        """
        content_classes = _content_classes()
        shortcut_spy = mocker.spy(class_utils, _SHORTCUT_NAME)

        answered_pairs: list[tuple[type[BaseModel], type[BaseModel]]] = []
        for class_1, class_2 in itertools.combinations(content_classes, 2):
            are_classes_equivalent(class_1, class_2=class_2)
            if shortcut_spy.spy_return is True:
                answered_pairs.append((class_1, class_2))
        mocker.stop(shortcut_spy)
        assert any({class_1, class_2} == {ImageContent, TextContent} for class_1, class_2 in answered_pairs)

        mocker.patch.object(class_utils, _SHORTCUT_NAME, return_value=False)
        disagreements = [
            (class_1.__name__, class_2.__name__)
            for class_1, class_2 in answered_pairs
            if are_classes_equivalent(class_1, class_2=class_2) is not False
        ]
        assert not disagreements
