"""Pin properties of ``_translate_to_validate_bundle_error``'s runtime contract.

- ``PipeValidationError`` and ``pydantic.ValidationError`` are siblings, not
  parent-child — the helper's ``except`` cascade orders
  ``except PipeValidationError`` BEFORE ``except ValidationError`` and relies
  on ``PipeValidationError(ValueError)`` NOT being a subclass of
  ``pydantic.ValidationError``. A future refactor that unifies the hierarchy
  would silently route pydantic errors into the wrong arm.
- The ``match category:`` in the ``except ValidationError`` arm is exhaustive
  over ``Literal["pipe", "concept"]`` and now ends with
  ``case _ as unreachable: assert_never(unreachable)``. A bad runtime value
  (passed via ``# type: ignore`` or dynamic dispatch) must raise a loud
  ``AssertionError`` rather than fall through to an ``UnboundLocalError`` on
  ``msg``.
"""

from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipeline.validate_bundle import (
    _translate_to_validate_bundle_error,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
)


class _ForceValidationError(BaseModel):
    """Pydantic model whose ``model_validate({})`` raises ``ValidationError``.

    Used to drive the helper's ``except ValidationError`` arm without
    constructing a ``pydantic.ValidationError`` directly (the class forbids
    direct instantiation outside pydantic internals).
    """

    required_field: int


class TestTranslateToValidateBundleErrorContract:
    def test_pipe_validation_error_is_not_a_pydantic_validation_error_subclass(self) -> None:
        """Cascade ordering in ``_translate_to_validate_bundle_error`` depends on this.

        If a future refactor makes ``PipeValidationError`` inherit from
        ``pydantic.ValidationError``, the helper's ``except PipeValidationError``
        clause would also catch pydantic ``ValidationError`` exceptions — and
        the ``except ValidationError`` clause below it (running
        ``categorize_pipe_validation_error``) would become dead code.
        """
        assert not issubclass(PipeValidationError, ValidationError)

    def test_unknown_category_raises_assertion_error_at_runtime(self) -> None:
        """An unexpected ``category`` value reaches ``assert_never`` and raises.

        The ``category`` parameter is ``Literal["pipe", "concept"]`` — pyright
        catches a bad call site statically. The runtime guard exists because
        ``# type: ignore`` or dynamic dispatch can still slip an unexpected
        value past the static check. The helper must then raise a loud
        ``AssertionError`` rather than fall through to an ``UnboundLocalError``
        on the unbound ``msg`` variable — the latter would silently break the
        helper's translation contract.
        """
        # ``cast("str", ...)`` strips the Literal narrowing so the runtime value
        # reaches the helper as a plain ``str`` — mirrors a real-world bypass
        # via ``# type: ignore`` or dynamic dispatch.
        bad_category = cast("str", "concepts")
        with (
            pytest.raises(AssertionError),
            _translate_to_validate_bundle_error(category=bad_category),  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        ):
            _ForceValidationError.model_validate({})
