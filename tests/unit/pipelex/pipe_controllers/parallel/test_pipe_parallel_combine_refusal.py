from typing import Any

import pytest
from pydantic import BaseModel, ValidationError, model_validator

from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.pipe_controllers.parallel.pipe_parallel import _refused_field_names  # pyright: ignore[reportPrivateUsage]


class _FieldRefusal(BaseModel):
    ideas: int
    overview: int


class _WholeStructureRefusal(BaseModel):
    ideas: int

    @model_validator(mode="before")
    @classmethod
    def refuse_everything(cls, data: Any) -> Any:
        msg = f"the structure refuses this combination: {data!r}"
        raise ValueError(msg)


def _combine_refusal(*, model_class: type[BaseModel], obj: dict[str, Any]) -> StuffFactoryError:
    try:
        model_class.model_validate(obj)
    except ValidationError as exc:
        refusal = StuffFactoryError("Error combining stuffs")
        refusal.__cause__ = exc
        return refusal
    pytest.fail("the model accepted what it was expected to refuse")


class TestPipeParallelCombineRefusal:
    def test_field_refusals_are_named(self) -> None:
        refusal = _combine_refusal(model_class=_FieldRefusal, obj={"ideas": "many", "overview": "short"})
        assert _refused_field_names(exc=refusal) == {"ideas", "overview"}

    def test_a_refusal_of_the_whole_structure_is_unclassified(self) -> None:
        """A model-level refusal belongs to no field, so no multiplicity sentence can explain it."""
        refusal = _combine_refusal(model_class=_WholeStructureRefusal, obj={"ideas": 1})
        assert _refused_field_names(exc=refusal) is None

    def test_a_refusal_without_a_pydantic_cause_is_unclassified(self) -> None:
        assert _refused_field_names(exc=StuffFactoryError("Error combining stuffs")) is None
