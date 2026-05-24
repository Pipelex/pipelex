"""Pin: ``PipeValidationError`` and ``pydantic.ValidationError`` are siblings, not parent-child.

The ``except`` cascade in ``_translate_to_validate_bundle_error`` orders
``except PipeValidationError`` BEFORE ``except ValidationError``. This works
today because ``PipeValidationError(ValueError)`` is NOT a subclass of
``pydantic.ValidationError`` — both are siblings under ``ValueError`` /
``Exception``. A future refactor that unifies the hierarchy (e.g. to share
categorization machinery) would silently route pydantic ``ValidationError``
exceptions into the ``PipeValidationError`` arm and lose the
``categorize_pipe_validation_error`` path entirely.
"""

from pydantic import ValidationError

from pipelex.core.pipes.exceptions import PipeValidationError


class TestPipeValidationErrorSiblingContract:
    def test_pipe_validation_error_is_not_a_pydantic_validation_error_subclass(self) -> None:
        """Cascade ordering in ``_translate_to_validate_bundle_error`` depends on this.

        If a future refactor makes ``PipeValidationError`` inherit from
        ``pydantic.ValidationError``, the helper's ``except PipeValidationError``
        clause would also catch pydantic ``ValidationError`` exceptions — and
        the ``except ValidationError`` clause below it (running
        ``categorize_pipe_validation_error``) would become dead code.
        """
        assert not issubclass(PipeValidationError, ValidationError)
