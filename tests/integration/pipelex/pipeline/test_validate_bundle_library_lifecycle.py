"""Pin: an opened library is torn down when bundle-validation fails.

Every bundle-loading entry point (``validate_bundle``,
``validate_bundles_from_directory``, ``load_concepts_only``,
``load_concepts_only_from_directory``) calls ``library_manager.open_library()``
before doing any work. When the body raises (including a translated
``ValidateBundleError`` from ``_translate_to_validate_bundle_error``), the
opened library must be torn down so the process does not accumulate one
un-torn-down ``Library`` per failed validation.

The IDE/server use case is the amplifier: a process that calls ``validate_bundle``
once per user save accumulates leaked libraries proportional to how often the
caller validates failing bundles — which is "every save while syntax-erroring"
for the IDE/agent build flow.
"""

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.hub import get_library_manager
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

    Forces a ``ValidationError`` inside the helper's ``with`` block, so the
    function exits via the translated re-raise path — exactly the path the
    library-leak fix protects.
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
class TestValidateBundleLibraryLifecycle:
    async def test_validate_bundle_tears_down_library_on_translated_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        teardown_calls_before = teardown_spy.call_count
        with pytest.raises(ValidateBundleError):
            await validate_bundle(mthds_contents=[_VALID_MTHDS])
        # The fix calls teardown(library_id=<the leaked id>) exactly once on the failure path.
        # The fixture's own teardown runs after the test, so we capture the delta here.
        assert teardown_spy.call_count == teardown_calls_before + 1
        latest_call = teardown_spy.call_args_list[-1]
        assert "library_id" in latest_call.kwargs

    async def test_validate_bundles_from_directory_tears_down_library_on_translated_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.mthds").write_text(_VALID_MTHDS, encoding="utf-8")
            teardown_calls_before = teardown_spy.call_count
            with pytest.raises(ValidateBundleError):
                await validate_bundles_from_directory(directory=Path(tmp_dir))
        assert teardown_spy.call_count == teardown_calls_before + 1
        latest_call = teardown_spy.call_args_list[-1]
        assert "library_id" in latest_call.kwargs

    async def test_load_concepts_only_tears_down_library_on_translated_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(validate_bundle_module, "LoadConceptsOnlyResult", _BrokenResult)

        teardown_calls_before = teardown_spy.call_count
        with pytest.raises(ValidateBundleError):
            load_concepts_only(mthds_contents=[_VALID_MTHDS])
        assert teardown_spy.call_count == teardown_calls_before + 1
        latest_call = teardown_spy.call_args_list[-1]
        assert "library_id" in latest_call.kwargs

    async def test_load_concepts_only_from_directory_tears_down_library_on_translated_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(validate_bundle_module, "LoadConceptsOnlyResult", _BrokenResult)

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.mthds").write_text(_VALID_MTHDS, encoding="utf-8")
            teardown_calls_before = teardown_spy.call_count
            with pytest.raises(ValidateBundleError):
                load_concepts_only_from_directory(directory=Path(tmp_dir))
        assert teardown_spy.call_count == teardown_calls_before + 1
        latest_call = teardown_spy.call_args_list[-1]
        assert "library_id" in latest_call.kwargs
