"""Pin: a pydantic ValidationError surfacing through the shared helper produces a clean summary.

The shared bundle-loading cascade ``translate_to_validate_bundle_error`` serves every entry point
(``validate_bundle*``, ``resolve_crate_from_contents``). A pydantic ``ValidationError`` raised
during model construction surfaces as a single ``ValidateBundleError`` whose top-line ``message``
must NOT leak the pydantic repr (``Value errors: '<field>': Value error, …``) nor the old
``Could not load blueprints/concepts because of:`` framing prefix that rode on it. Instead the
message is the clean, author-facing summary the constructor derives from the structured error
items (``ValidateBundleError.__init__`` → ``_summarize_bundle_validation_message``) — the same
text a consumer reads off the first ``validation_errors[]`` item. The invariant lives on the
constructor, so it is entry-point-independent.
"""

import tempfile
from pathlib import Path
from typing import Callable

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.pipeline import validate_bundle as validate_bundle_module
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle, validate_bundles_from_directory


class _BrokenResult(BaseModel):
    """Stand-in for the real result class that fails pydantic validation on construction."""

    forced_required_field: int


_VALID_MTHDS = """
domain = "testapp"
description = "Test domain"

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }
"""


def _assert_clean_summary(exc: ValidateBundleError) -> None:
    """The top-line message is the clean item summary — no pydantic-repr / framing leak."""
    assert "Value error" not in exc.message
    assert "Validation error(s)" not in exc.message
    assert "Could not load blueprints because of" not in exc.message
    assert "Could not load concepts because of" not in exc.message
    # The summary is derived from the structured items: a single item projects its message verbatim.
    items = list(exc.to_error_report().validation_errors or [])
    assert items, "an invalid verdict must carry structured items"
    assert exc.message == items[0].message


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleCleanSummary:
    async def test_validate_bundle_message_is_clean_summary(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_VALID_MTHDS])
        _assert_clean_summary(exc_info.value)

    async def test_validate_bundles_from_directory_message_is_clean_summary(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.mthds").write_text(_VALID_MTHDS, encoding="utf-8")
            with pytest.raises(ValidateBundleError) as exc_info:
                await validate_bundles_from_directory(directory=Path(tmp_dir))
        _assert_clean_summary(exc_info.value)
