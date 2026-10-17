from typing import Annotated, Any, Literal

import pytest
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field, RootModel, ValidationError

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
