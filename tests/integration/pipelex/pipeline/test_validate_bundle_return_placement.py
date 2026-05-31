"""Pin: result-class construction errors are translated to ``ValidateBundleError`` uniformly.

All four bundle-loading entry points (``validate_bundle``,
``validate_bundles_from_directory``, ``load_concepts_only``,
``load_concepts_only_from_directory``) must place their final ``return`` inside
the ``with _translate_to_validate_bundle_error()`` block. A
``pydantic.ValidationError`` raised from result-class construction therefore
surfaces as a single ``ValidateBundleError`` envelope regardless of entry point.

Without this guarantee, the four entry points split into two shapes — two
returning inside the ``with`` (translated) and two outside (raw
``pydantic.ValidationError`` propagates) — and downstream handlers that only
``except ValidateBundleError`` would miss the latter two.
"""

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.pipeline import validate_bundle as validate_bundle_module
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import (
    load_concepts_only,
    load_concepts_only_from_directory,
    validate_bundle,
    validate_bundles_from_directory,
)


class _BrokenResult(BaseModel):
    """Stand-in for the real result class that fails pydantic validation on construction.

    Declares one required field and accepts no kwargs from the production call
    sites — building this with ``ValidateBundleResult(blueprints=..., pipes=..., dry_run_result=...)``
    raises ``pydantic.ValidationError`` for the missing required field.
    """

    forced_required_field: int


_VALID_MTHDS = """
domain = "testapp"
description = "Test domain"

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }
"""


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleResultConstructionErrorTranslation:
    async def test_validate_bundle_translates_result_construction_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        with pytest.raises(ValidateBundleError):
            await validate_bundle(mthds_contents=[_VALID_MTHDS])

    async def test_validate_bundles_from_directory_translates_result_construction_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.mthds").write_text(_VALID_MTHDS, encoding="utf-8")
            with pytest.raises(ValidateBundleError):
                await validate_bundles_from_directory(directory=Path(tmp_dir))

    async def test_load_concepts_only_translates_result_construction_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "LoadConceptsOnlyResult", _BrokenResult)

        with pytest.raises(ValidateBundleError):
            load_concepts_only(mthds_contents=[_VALID_MTHDS])

    async def test_load_concepts_only_from_directory_translates_result_construction_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "LoadConceptsOnlyResult", _BrokenResult)

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.mthds").write_text(_VALID_MTHDS, encoding="utf-8")
            with pytest.raises(ValidateBundleError):
                load_concepts_only_from_directory(directory=Path(tmp_dir))
