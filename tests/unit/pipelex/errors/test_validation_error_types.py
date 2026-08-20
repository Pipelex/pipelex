"""Gates on the closed registry of bundle-validation ``error_type`` values.

``pipelex.validation_error_types.VALIDATION_ERROR_TYPES`` is the enumeration consumers read to
learn which faults the language surface can report — the ``/validate`` contract publishes it, and
the MTHDS Test Corpus will generate its ``error.*`` tag namespace from it. These tests hold
the two properties that enumeration depends on: that it is derived from the enums the runtime
actually raises (so it cannot fall behind them), and that those enums do not collide on a wire
value (so an ``error_type`` still identifies exactly one fault).
"""

import pytest
from pydantic import ValidationError

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.validation_error_types import (
    VALIDATION_ERROR_TYPES,
    PipeFactoryErrorType,
    PipeValidationErrorType,
    ValidationErrorType,
    ValidationResidualErrorType,
)


class TestValidationErrorTypeRegistry:
    def test_registry_holds_every_member_of_every_contributing_enum(self) -> None:
        """The registry is the union of its sources, so nothing the runtime raises is missing.

        Written as a set comparison rather than a length check: a member dropped from the registry
        and a member added to a source enum are both failures, and both should name the member.
        """
        contributed = set(PipeValidationErrorType) | set(PipeFactoryErrorType) | set(ValidationResidualErrorType)
        assert set(VALIDATION_ERROR_TYPES) == contributed

    def test_registry_has_no_duplicate_wire_values(self) -> None:
        """The contributing enums are value-disjoint, so an ``error_type`` identifies one fault.

        Were two enums to share a value, the ``ValidationErrorType`` union would resolve it to
        whichever member pydantic reached first, and a consumer keying on the string — the corpus's
        ``error.*`` tags, conformance's per-error QA cases — would silently conflate two faults.
        """
        wire_values = [error_type.value for error_type in VALIDATION_ERROR_TYPES]
        duplicates = sorted({value for value in wire_values if wire_values.count(value) > 1})
        assert not duplicates, f"Validation error types sharing a wire value: {', '.join(duplicates)}"

    def test_registry_order_is_deterministic(self) -> None:
        """Two reads give the same order, so an artifact generated from the registry is stable."""
        assert tuple(VALIDATION_ERROR_TYPES) == VALIDATION_ERROR_TYPES
        assert list(VALIDATION_ERROR_TYPES) == [*PipeValidationErrorType, *PipeFactoryErrorType, *ValidationResidualErrorType]

    # The three tests below hold that the registry is enforced when an item is parsed, not merely
    # documented. They go through ``model_validate`` rather than the constructor on purpose: the
    # closure that matters is the one a *consumer* meets, reading a plain JSON string off the wire
    # and turning it back into a diagnostic. A typed constructor call proves only that the type
    # checker agrees.

    @pytest.mark.parametrize("error_type", VALIDATION_ERROR_TYPES)
    def test_every_registered_type_is_accepted_by_its_wire_value(self, error_type: ValidationErrorType) -> None:
        """A registry member round-trips through the plain string it serializes as."""
        item = ValidationErrorItem.model_validate(
            {"category": ValidationErrorCategory.PIPE_VALIDATION, "message": "whatever", "error_type": error_type.value}
        )
        assert item.error_type == error_type

    def test_an_unregistered_error_type_is_refused(self) -> None:
        """The failure mode this typing exists to stop: a fault named by an ad-hoc string."""
        with pytest.raises(ValidationError):
            ValidationErrorItem.model_validate(
                {"category": ValidationErrorCategory.PIPE_VALIDATION, "message": "whatever", "error_type": "not_a_registered_error_type"}
            )

    def test_the_parse_level_residual_may_carry_no_error_type(self) -> None:
        """``None`` stays legal — a bundle that never became a blueprint identifies no single fault."""
        item = ValidationErrorItem.model_validate({"category": ValidationErrorCategory.BLUEPRINT_VALIDATION, "message": "Invalid TOML."})
        assert item.error_type is None
