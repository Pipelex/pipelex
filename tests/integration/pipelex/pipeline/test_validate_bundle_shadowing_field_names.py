from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
from pydantic import BaseModel

from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.registries.class_registry_access import get_class_registry
from tests.integration.pipelex.pipeline.test_data import ShadowingFieldNamesTestData


@contextmanager
def _validated_library() -> Generator[None]:
    """Tear down the library a successful validation leaves open and current."""
    try:
        yield
    finally:
        library_id = get_current_library_id_or_none()
        if library_id is not None:
            get_library_manager().teardown(library_id=library_id)
        clear_current_library()


def _structure_class(class_name: str) -> type[BaseModel]:
    structure_class = get_class_registry().get_class(name=class_name)
    assert structure_class is not None, f"no class '{class_name}' was registered"
    return cast("type[BaseModel]", structure_class)


def _assert_round_trips(*, structure_class: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    instance = structure_class.model_validate(payload)
    assert structure_class.model_validate(instance.model_dump(mode="json")) == instance
    assert structure_class.model_validate_json(instance.model_dump_json()) == instance
    return instance


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleShadowingFieldNames:
    async def test_a_field_named_date_typed_date_validates_and_its_class_holds_a_date(self):
        """The bundle the hosted `/v1/validate` answered with an internal error validates, and its class holds a date."""
        with _validated_library():
            result = await validate_bundle(mthds_contents=[ShadowingFieldNamesTestData.DATE_FIELD_MTHDS])

            assert result.dry_run_result[f"{ShadowingFieldNamesTestData.DATE_FIELD_DOMAIN}.read_day"].status.is_success
            day_class = _structure_class(ShadowingFieldNamesTestData.DATE_FIELD_CLASS_NAME)
            instance = _assert_round_trips(structure_class=day_class, payload={"date": "2026-09-27"})
            assert instance.model_dump() == {"date": date(2026, 9, 27)}

    async def test_fields_shadowing_several_names_validate_and_their_class_holds_their_values(self):
        """Fields named like builtins, `Field`, `datetime` and a native content class validate together."""
        with _validated_library():
            result = await validate_bundle(mthds_contents=[ShadowingFieldNamesTestData.SEVERAL_NAMES_MTHDS])

            assert result.dry_run_result["shadowing_names.read_entry"].status.is_success
            entry_class = _structure_class("shadowing_names__Entry")
            instance = _assert_round_trips(
                structure_class=entry_class,
                payload={
                    "str": "A title",
                    "Field": "Botany",
                    "datetime": "2026-09-27T10:30:00Z",
                    "TextContent": {"text": "The body"},
                },
            )
            assert instance.model_dump(exclude={"TextContent"}) == {
                "str": "A title",
                "Field": "Botany",
                "datetime": datetime(2026, 9, 27, 10, 30, tzinfo=UTC),
                "note": None,
            }
            assert dict(instance)["TextContent"] == TextContent(text="The body")

    async def test_a_field_named_like_a_class_its_structure_refers_to_is_a_verdict_naming_the_concept_and_the_field(self):
        """The one name no alias can stand for is refused as an invalid verdict, never as an internal error."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[ShadowingFieldNamesTestData.FORWARD_REF_FIELD_MTHDS])

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == "method.invalid"
        items = problem.errors or []
        assert len(items) == 1
        item = items[0]
        concept = ShadowingFieldNamesTestData.FORWARD_REF_FIELD_CONCEPT
        finding = ShadowingFieldNamesTestData.FORWARD_REF_FIELD_FINDING
        assert item.code == "method.concept_invalid"
        assert item.params is not None
        assert item.params.as_wire() == {"concept": concept, "finding": finding}
        assert item.detail == f"The structure of the concept '{concept}' cannot be built ({finding})."
