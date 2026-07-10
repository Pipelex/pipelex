"""Pin properties of ``translate_to_validate_bundle_error``'s runtime contract.

``PipeValidationError`` and ``pydantic.ValidationError`` are siblings, not
parent-child — the helper's ``except`` cascade orders
``except PipeValidationError`` BEFORE ``except ValidationError`` and relies
on ``PipeValidationError(ValueError)`` NOT being a subclass of
``pydantic.ValidationError``. A future refactor that unifies the hierarchy
would silently route pydantic errors into the wrong arm.
"""

from pydantic import ValidationError

from pipelex.core.pipes.exceptions import PipeValidationError


class TestTranslateToValidateBundleErrorContract:
    def test_pipe_validation_error_is_not_a_pydantic_validation_error_subclass(self) -> None:
        """Cascade ordering in ``translate_to_validate_bundle_error`` depends on this.

        If a future refactor makes ``PipeValidationError`` inherit from
        ``pydantic.ValidationError``, the helper's ``except PipeValidationError``
        clause would also catch pydantic ``ValidationError`` exceptions — and
        the ``except ValidationError`` clause below it (running
        ``categorize_pipe_validation_error``) would become dead code.
        """
        assert not issubclass(PipeValidationError, ValidationError)
