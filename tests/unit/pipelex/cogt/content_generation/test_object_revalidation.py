"""The shared leaf-result → caller-class conversion, including the arms only a distributed backend uses.

``object_revalidation`` is the single home of a contract both implementations of
``ContentGeneratorProtocol`` depend on — the in-process one in this repo and the workflow arm of our
distributed-execution plugin, which lives in another repo. The arms that repo exercises (the json dump
mode, and a LIVE ``ValidationError`` surviving untouched so the plugin can convert it to a terminal
error) have no in-tree caller, so they are pinned here rather than riding on nothing.

The in-process arms — the ``isinstance`` short-circuit and the dry fidelity error — are exercised
end-to-end in ``tests/integration/pipelex/cogt/content_generation/``; what this module adds is the
mode-independence of the short-circuit and the two error surfaces of the data arm.
"""

from typing import Literal

import pytest
from pydantic import BaseModel, ValidationError, field_serializer

from pipelex.cogt.content_generation.exceptions import DryRunObjectFidelityError
from pipelex.cogt.content_generation.object_revalidation import revalidate_leaf_data, revalidate_leaf_object


class Marker(BaseModel):
    """The caller's class: what the leaf result must come back as."""

    marker: str


class BoundaryMarker(BaseModel):
    """Stand-in for a leaf result that crossed a payload boundary.

    Its ``marker`` serializes differently in json mode, which is what makes the dump mode observable —
    the reason a distributed backend needs ``mode="json"`` at all is that some values only round-trip
    cleanly through their json form.
    """

    marker: str

    @field_serializer("marker", when_used="json")
    def _serialize_marker(self, value: str) -> str:
        return value.upper()


class MarkerSubclass(Marker):
    """What an in-process leaf hands back: never the caller's class itself, always a subclass of it."""


class TestObjectRevalidation:
    @pytest.mark.parametrize(
        ("dump_mode", "expected_marker"),
        [
            ("python", "boundary"),
            ("json", "BOUNDARY"),
        ],
    )
    def test_dump_mode_reaches_the_dump(self, dump_mode: Literal["json", "python"], expected_marker: str) -> None:
        """The mode is forwarded to model_dump, so a value that needs its json form gets it."""
        raw_obj = BoundaryMarker(marker="boundary")

        result = revalidate_leaf_object(raw_obj, object_class=Marker, is_mock_built=False, dump_mode=dump_mode)

        assert type(result) is Marker
        assert result.marker == expected_marker

    @pytest.mark.parametrize("dump_mode", ["python", "json"])
    def test_instance_short_circuits_in_either_dump_mode(self, dump_mode: Literal["json", "python"]) -> None:
        """An object that already is one is returned untouched whatever the mode — no dump, no second validation.

        The distributed arm never hits this today (a schema-rebuilt class is not a subclass of the
        caller's), and carrying it anyway is the point: a boundary that ever does hand back the real
        class cannot silently reinstate the double validation the in-process path had.
        """
        raw_obj = MarkerSubclass(marker="untouched")

        result = revalidate_leaf_object(raw_obj, object_class=Marker, is_mock_built=False, dump_mode=dump_mode)

        assert result is raw_obj

    def test_data_arm_validates_into_the_caller_class(self) -> None:
        """The data arm's validation is the single one on its path."""
        result = revalidate_leaf_data({"marker": "from-the-wire"}, object_class=Marker, is_mock_built=False)

        assert type(result) is Marker
        assert result.marker == "from-the-wire"

    def test_live_data_failure_keeps_its_validation_error(self) -> None:
        """A LIVE provider's malformed data keeps its ValidationError.

        Load-bearing for the distributed backend: it catches exactly this to convert it into a terminal
        typed error, because a bare ValidationError raised in workflow code retries forever.
        """
        with pytest.raises(ValidationError):
            revalidate_leaf_data({"marker": 123}, object_class=Marker, is_mock_built=False)

    def test_mock_built_data_failure_raises_the_typed_fidelity_error(self) -> None:
        """Mock-built data that fails is the known schema-round-trip gap, named as such with its remedy."""
        with pytest.raises(DryRunObjectFidelityError) as exc_info:
            revalidate_leaf_data({"marker": None}, object_class=Marker, is_mock_built=True)

        assert Marker.__name__ in str(exc_info.value)
        assert "mock_format" in str(exc_info.value)
