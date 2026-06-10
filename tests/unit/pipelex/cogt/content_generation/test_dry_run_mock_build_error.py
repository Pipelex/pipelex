"""Pin the typed terminal mock-build error (eng review D7).

``build_mock_object`` wraps deterministic polyfactory/validation failures into
``DryRunMockBuildError`` (a ``PipelexError``), so the activity error boundary converts it to a
terminal failure instead of letting Temporal retry a failure that can never succeed. The message
must name the class and the ``examples`` / ``mock_format`` remedy.
"""

import pytest
from pydantic import field_validator

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.content_generation.dry_mock import build_mock_object
from pipelex.cogt.content_generation.exceptions import DryRunMockBuildError
from pipelex.core.stuffs.structured_content import StructuredContent


class UnbuildableName(StructuredContent):
    """polyfactory cannot guess a value passing this validator without `examples` / `mock_format`."""

    name: str

    @field_validator("name")
    @classmethod
    def _require_exact(cls, value: str) -> str:
        if value != "the-one-true-name":
            msg = "name must be exactly 'the-one-true-name'"
            raise ValueError(msg)
        return value


class BuildableName(StructuredContent):
    """Control: a plain string field builds fine."""

    name: str


class TestDryRunMockBuildError:
    def test_unbuildable_class_raises_typed_terminal_error(self) -> None:
        """A deterministic build failure surfaces as DryRunMockBuildError naming class and remedy."""
        with pytest.raises(DryRunMockBuildError) as exc_info:
            build_mock_object(UnbuildableName)

        assert isinstance(exc_info.value, PipelexError)
        assert UnbuildableName.__name__ in str(exc_info.value)
        assert "mock_format" in str(exc_info.value)

    def test_buildable_class_builds(self) -> None:
        """Control arm: an unconstrained class builds a valid instance."""
        mock_object = build_mock_object(BuildableName)

        assert isinstance(mock_object, BuildableName)
        assert isinstance(mock_object.name, str)
