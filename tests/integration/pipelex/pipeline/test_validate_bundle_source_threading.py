"""Integration: ``validate_bundle`` threads per-content ``mthds_names`` into ``blueprint.source``.

The API submits nameless bundle text (``mthds_contents: list[str]``), so without
a per-item name the in-memory load path sets ``blueprint.source = None`` and
cross-file diagnostics misfire. ``validate_bundle(mthds_names=...)`` pairs each
content with its logical name, so the loaded blueprint — and any
``ValidateBundleError`` it raises — carries a real ``source`` the consumer can map
to the owning file. The CLI's on-disk path keeps using real file paths and is
unaffected.
"""

from collections.abc import Callable

import pytest

from pipelex.base_exceptions import PipelexUnexpectedError, ValidationErrorCategory
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle

_VALID_MTHDS = """
domain = "testapp"
description = "Test domain"

[concept.Customer]
description = "A customer"
"""

# An invalid ``main_pipe`` deterministically fails blueprint validation, producing a
# categorized blueprint-validation error that carries the blueprint's ``source``.
_INVALID_MAIN_PIPE_MTHDS = """
domain = "testapp"
description = "Test domain"
main_pipe = "Not A Valid Pipe Code!"

[concept.Customer]
description = "A customer"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleSourceThreading:
    async def test_valid_bundle_blueprint_carries_threaded_source(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A valid bundle's loaded blueprint records the threaded per-content name as ``source``."""
        load_empty_library()
        result = await validate_bundle(mthds_contents=[_VALID_MTHDS], mthds_names=["api://bundle-0.mthds"])
        assert result.blueprints[0].source == "api://bundle-0.mthds"

    async def test_source_none_without_names(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Without ``mthds_names`` the in-memory path leaves ``source`` unset (unchanged behavior)."""
        load_empty_library()
        result = await validate_bundle(mthds_contents=[_VALID_MTHDS])
        assert result.blueprints[0].source is None

    async def test_invalid_bundle_validation_errors_carry_source(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """An invalid bundle's structured ``validation_errors`` carry the threaded ``source``.

        Pins that the carrier is the *blueprint-validation* item produced by the dict-seeded
        ``source`` (the failure happens before the post-validate object exists), not some
        coincidental other item — so a regression that silently stopped seeding would fail here.
        """
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_INVALID_MAIN_PIPE_MTHDS], mthds_names=["broken.mthds"])
        report = exc_info.value.to_error_report()
        assert report.validation_errors is not None
        seeded_items = [item for item in report.validation_errors if item.source == "broken.mthds"]
        assert seeded_items, "no validation_errors item carried the threaded source"
        assert any(item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION for item in seeded_items)

    async def test_length_mismatch_is_a_host_contract_error(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A ``mthds_names``/``mthds_contents`` length mismatch is a host wiring bug, not user input.

        It must raise an internal error (→ 500, redacted under STRICT), not a caller-facing
        ``ValidateBundleError`` (→ 422) — ``mthds_names`` is never supplied by the end caller.
        """
        load_empty_library()
        with pytest.raises(PipelexUnexpectedError, match="must be a per-item name list matching mthds_contents"):
            await validate_bundle(mthds_contents=[_VALID_MTHDS], mthds_names=["a.mthds", "b.mthds"])
