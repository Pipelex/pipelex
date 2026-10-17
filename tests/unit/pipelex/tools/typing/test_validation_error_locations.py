from typing import Annotated, Any, Literal

import pytest
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field, RootModel, TypeAdapter, ValidationError
from pydantic_core import SchemaValidator
from pytest_mock import MockerFixture

from pipelex.tools.typing import pydantic_utils
from pipelex.tools.typing.pydantic_utils import (
    PAYLOAD_KEY_PLACEHOLDER,
    empty_dict_factory_of,
    empty_list_factory_of,
    format_validation_error_without_input,
    validation_error_locations,
)

# A key of the run's own data, which no location carries.
_PAYLOAD_KEY = "confidential-patient-diagnosis"


class _Leaf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int


class _Cat(BaseModel):
    kind: Literal["cat"]
    meow: int


class _Dog(BaseModel):
    kind: Literal["dog"]
    bark: int


class _Outer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: dict[str, _Leaf] = Field(default_factory=dict)
    ids: dict[int, int] = Field(default_factory=empty_dict_factory_of(int, _val=int))
    items: list[_Leaf] = Field(default_factory=empty_list_factory_of(_Leaf))
    maybe: _Leaf | None = None
    either: int | _Leaf = 0
    pet: Annotated[_Cat | _Dog, Field(discriminator="kind")] | None = None
    aliased: int = Field(default=0, alias="Aliased")
    pair: tuple[int, _Leaf] | None = None
    loose: dict[str, Any] = Field(default_factory=dict)


class _Aliases(BaseModel):
    nested: int = Field(default=0, validation_alias=AliasPath("outer", 0))
    chosen: int = Field(default=0, validation_alias=AliasChoices("chosen_one", AliasPath("chosen_path", "inner")))


class _Ledger(RootModel[dict[str, _Leaf]]):
    pass


def _locations(*, model: type[BaseModel], document: object) -> list[str | None]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(document)
    return validation_error_locations(validation_error=caught.value, validated_type=model)


class TestValidationErrorLocations:
    @pytest.mark.parametrize(
        ("topic", "model", "document", "expected"),
        [
            ("an invalid value under a dict's key", _Outer, {"entries": {_PAYLOAD_KEY: {"score": "high"}}}, ["entries.<key>.score"]),
            ("an extra key under a dict's key", _Outer, {"entries": {_PAYLOAD_KEY: {"score": 1, _PAYLOAD_KEY: 2}}}, ["entries.<key>.<key>"]),
            ("an extra key of a nested model", _Outer, {"maybe": {"score": 1, _PAYLOAD_KEY: 2}}, ["maybe.<key>"]),
            ("an extra key of the model itself", _Outer, {_PAYLOAD_KEY: 1}, ["<key>"]),
            ("a dict's key refused itself", _Outer, {"ids": {_PAYLOAD_KEY: 1}}, ["ids.<key>.[key]"]),
            ("an int key of a dict", _Outer, {"ids": {"5": "five"}}, ["ids.<key>"]),
            ("a position in a list", _Outer, {"items": [{"score": 1}, {"score": "high"}]}, ["items.1.score"]),
            ("a position in a tuple", _Outer, {"pair": [1, {"score": "high"}]}, ["pair.1.score"]),
            ("the choices of a union", _Outer, {"either": "high"}, ["either.int", "either._Leaf"]),
            ("a tagged union's tag", _Outer, {"pet": {"kind": "cat", "meow": "loud"}}, ["pet.cat.meow"]),
            ("a field's alias", _Outer, {"Aliased": "high"}, ["Aliased"]),
            ("a root model's dict", _Ledger, {_PAYLOAD_KEY: {"score": "high"}}, ["<key>.score"]),
            ("an alias path", _Aliases, {"outer": ["high"]}, ["outer.0"]),
            ("an alias choice's path", _Aliases, {"chosen_path": {"inner": "high"}}, ["chosen_path.inner"]),
        ],
    )
    def test_a_location_names_what_the_schema_names_and_hides_the_input_s_keys(
        self, topic: str, model: type[BaseModel], document: object, expected: list[str | None]
    ) -> None:
        locations = _locations(model=model, document=document)

        assert locations == expected, topic
        assert all(_PAYLOAD_KEY not in (location or "") for location in locations), topic

    def test_an_error_of_another_model_is_given_no_location(self) -> None:
        """A location is read off the schema only when the error came from it: another model's would name the wrong things."""
        with pytest.raises(ValidationError) as caught:
            _Outer.model_validate({"entries": {_PAYLOAD_KEY: {"score": "high"}}})

        assert validation_error_locations(validation_error=caught.value, validated_type=_Leaf) == [None]
        assert validation_error_locations(validation_error=caught.value, validated_type=None) == [None]

    def test_the_formatted_error_reads_the_same_locations(self) -> None:
        with pytest.raises(ValidationError) as caught:
            _Outer.model_validate({"entries": {_PAYLOAD_KEY: {"score": "high", _PAYLOAD_KEY: 2}}})

        formatted = format_validation_error_without_input(validation_error=caught.value, validated_type=_Outer)

        assert formatted == (
            f"entries.{PAYLOAD_KEY_PLACEHOLDER}.score: Input should be a valid integer, unable to parse string as an integer; "
            f"entries.{PAYLOAD_KEY_PLACEHOLDER}.{PAYLOAD_KEY_PLACEHOLDER}: Extra inputs are not permitted"
        )

    def test_an_authored_document_is_located_as_pydantic_gives_it(self) -> None:
        """A method author's own document, or a value Pipelex built, holds no run's data: its keys are written as they are."""
        with pytest.raises(ValidationError) as caught:
            _Outer.model_validate({"entries": {"opening_hours": {"score": "high"}}})

        assert validation_error_locations(validation_error=caught.value, validated_type=None, is_authored_input=True) == [
            "entries.opening_hours.score"
        ]
        assert format_validation_error_without_input(validation_error=caught.value, is_authored_input=True) == (
            "entries.opening_hours.score: Input should be a valid integer, unable to parse string as an integer"
        )

    def test_a_type_adapter_locates_what_it_validated(self) -> None:
        """A type that is no model, such as a list or a union of models, is validated by a TypeAdapter, which locates it the same way."""
        adapter: TypeAdapter[list[_Outer]] = TypeAdapter(list[_Outer])
        with pytest.raises(ValidationError) as caught:
            adapter.validate_python([{}, {"entries": {_PAYLOAD_KEY: {"score": "high"}}}])

        assert validation_error_locations(validation_error=caught.value, validated_type=adapter) == ["1.entries.<key>.score"]

    def test_each_located_reason_is_written_once_in_the_order_it_first_comes(self) -> None:
        with pytest.raises(ValidationError) as caught:
            _Outer.model_validate({"items": [{"score": "high"}, {"score": 1, _PAYLOAD_KEY: 2}, {"score": "low"}], "maybe": {"score": "x"}})

        formatted = format_validation_error_without_input(validation_error=caught.value, validated_type=_Outer)

        assert formatted == (
            "items.0.score: Input should be a valid integer, unable to parse string as an integer; "
            f"items.1.{PAYLOAD_KEY_PLACEHOLDER}: Extra inputs are not permitted; "
            "items.2.score: Input should be a valid integer, unable to parse string as an integer; "
            "maybe.score: Input should be a valid integer, unable to parse string as an integer"
        )
        assert format_validation_error_without_input(validation_error=caught.value) == (
            "Input should be a valid integer, unable to parse string as an integer; Extra inputs are not permitted"
        )

    def test_a_union_choice_s_label_is_read_once_per_schema(self, mocker: MockerFixture) -> None:
        """The label of a union's choice is pydantic's title for it, read once for the validated type, not once per error."""

        class _Choices(BaseModel):
            either: list[int | _Leaf]

        spy = mocker.patch.object(pydantic_utils, "SchemaValidator", wraps=SchemaValidator)
        with pytest.raises(ValidationError) as caught:
            _Choices.model_validate({"either": ["a", "b", "c"]})

        first = validation_error_locations(validation_error=caught.value, validated_type=_Choices)
        second = validation_error_locations(validation_error=caught.value, validated_type=_Choices)

        assert first == second == [f"either.{position}.{choice}" for position in range(3) for choice in ("int", "_Leaf")]
        assert spy.call_count == 2
