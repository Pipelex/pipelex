"""Pin: ValidationError surfacing through the helper carries category-specific copy.

The shared helper ``_translate_to_validate_bundle_error`` is invoked from four
entry points with two distinct categories — ``"pipe"`` from
``validate_bundle*`` and ``"concept"`` from ``load_concepts_only*``. A pydantic
``ValidationError`` raised during model construction surfaces as a single
``ValidateBundleError``; the helper's category controls the user-facing
framing so a concept-side validation error is not framed as a pipe-validation
error (which it would be without the parameter).
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


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleCategoryFraming:
    async def test_validate_bundle_frames_validation_error_as_pipe(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_VALID_MTHDS])
        assert "Could not load blueprints because of" in exc_info.value.message
        assert "Could not load concepts" not in exc_info.value.message

    async def test_validate_bundles_from_directory_frames_validation_error_as_pipe(
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
        assert "Could not load blueprints because of" in exc_info.value.message
        assert "Could not load concepts" not in exc_info.value.message

    async def test_load_concepts_only_frames_validation_error_as_concept(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "LoadConceptsOnlyResult", _BrokenResult)

        with pytest.raises(ValidateBundleError) as exc_info:
            load_concepts_only(mthds_contents=[_VALID_MTHDS])
        assert "Could not load concepts because of" in exc_info.value.message
        assert "Could not load blueprints" not in exc_info.value.message

    async def test_load_concepts_only_from_directory_frames_validation_error_as_concept(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        mocker.patch.object(validate_bundle_module, "LoadConceptsOnlyResult", _BrokenResult)

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.mthds").write_text(_VALID_MTHDS, encoding="utf-8")
            with pytest.raises(ValidateBundleError) as exc_info:
                load_concepts_only_from_directory(directory=Path(tmp_dir))
        assert "Could not load concepts because of" in exc_info.value.message
        assert "Could not load blueprints" not in exc_info.value.message
