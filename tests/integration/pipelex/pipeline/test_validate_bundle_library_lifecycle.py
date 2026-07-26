"""Pin: an opened library is torn down when bundle-validation fails.

Both bundle-loading entry points (``validate_bundle`` and
``validate_bundles_from_directory``) call ``library_manager.open_library()``
before doing any work. When the body raises (including a translated
``ValidateBundleError`` from ``translate_to_validate_bundle_error``), the
opened library must be torn down so the process does not accumulate one
un-torn-down ``Library`` per failed validation.

The IDE/server use case is the amplifier: a process that calls ``validate_bundle``
once per user save accumulates leaked libraries proportional to how often the
caller validates failing bundles — which is "every save while syntax-erroring"
for the IDE/agent build flow.

Also pins the preflight-leak surface: every statement that runs between
``open_library()`` and the body must live inside the ``try`` block so any
exception (including ``asyncio.CancelledError`` at an ``await`` yield, or a
``TypeError`` from ``resolve_library_dirs``) still triggers teardown. The
``library_id`` passed to ``teardown`` is asserted equal to the one returned by
``open_library`` so a regression that tore down a stale closure-captured id
would still fail the test.
"""

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.method_hub import clear_current_library, get_current_library, get_library_manager, set_current_library
from pipelex.pipeline import validate_bundle as validate_bundle_module
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import (
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
        open_library_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        teardown_calls_before = teardown_spy.call_count
        with pytest.raises(ValidateBundleError):
            await validate_bundle(mthds_contents=[_VALID_MTHDS])
        # The fix calls teardown(library_id=<the leaked id>) exactly once on the failure path.
        # The fixture's own teardown runs after the test, so we capture the delta here.
        assert teardown_spy.call_count == teardown_calls_before + 1
        latest_call = teardown_spy.call_args_list[-1]
        opened_library_id, _ = open_library_spy.spy_return
        assert latest_call.kwargs["library_id"] == opened_library_id

    async def test_validate_bundles_from_directory_tears_down_library_on_translated_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        load_empty_library()
        library_manager = get_library_manager()
        open_library_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)

        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.mthds").write_text(_VALID_MTHDS, encoding="utf-8")
            teardown_calls_before = teardown_spy.call_count
            with pytest.raises(ValidateBundleError):
                await validate_bundles_from_directory(directory=Path(tmp_dir))
        assert teardown_spy.call_count == teardown_calls_before + 1
        latest_call = teardown_spy.call_args_list[-1]
        opened_library_id, _ = open_library_spy.spy_return
        assert latest_call.kwargs["library_id"] == opened_library_id

    async def test_validate_bundle_tears_down_on_base_exception_in_pre_try_window(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """Pin: a ``BaseException`` (e.g. ``CancelledError``) raised in the pre-try window still triggers teardown.

        The IDE/server use case is the trigger — a caller that cancels in-flight
        validation on every keystroke would otherwise leak one library per
        cancellation, because ``asyncio.CancelledError`` is a ``BaseException``
        and only ``finally`` (not ``except Exception``) catches it. Every
        statement between ``open_library()`` and the helper ``with`` block —
        including the ``await asyncio.sleep(0)`` yield — must live inside the
        ``try`` block so the ``finally`` runs.

        Simulated here by patching ``resolve_library_dirs`` (which runs in that
        window) to raise ``CancelledError``. The shape — a ``BaseException`` in
        the pre-try window — is the property under test, not the specific call
        site.
        """
        load_empty_library()
        library_manager = get_library_manager()
        open_library_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(
            validate_bundle_module,
            "resolve_library_dirs",
            side_effect=asyncio.CancelledError("simulated cancellation in pre-try window"),
        )

        teardown_calls_before = teardown_spy.call_count
        with pytest.raises(asyncio.CancelledError):
            await validate_bundle(mthds_contents=[_VALID_MTHDS])

        assert teardown_spy.call_count == teardown_calls_before + 1
        latest_call = teardown_spy.call_args_list[-1]
        opened_library_id, _ = open_library_spy.spy_return
        assert latest_call.kwargs["library_id"] == opened_library_id

    async def test_validate_bundle_tears_down_on_resolve_library_dirs_failure(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """Pin: a ``TypeError`` from ``resolve_library_dirs`` still triggers teardown.

        ``resolve_library_dirs`` runs between ``open_library`` and the helper
        ``with`` block. A malformed ``library_dirs`` element (e.g. ``None`` in
        the sequence) raises ``TypeError`` at ``Path(None)``. The pre-try-leak
        fix moves it inside the ``try`` block so the ``finally`` runs.
        """
        load_empty_library()
        library_manager = get_library_manager()
        open_library_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(
            validate_bundle_module,
            "resolve_library_dirs",
            side_effect=TypeError("simulated invalid library_dirs element"),
        )

        teardown_calls_before = teardown_spy.call_count
        with pytest.raises(TypeError):
            await validate_bundle(mthds_contents=[_VALID_MTHDS])

        assert teardown_spy.call_count == teardown_calls_before + 1
        latest_call = teardown_spy.call_args_list[-1]
        opened_library_id, _ = open_library_spy.spy_return
        assert latest_call.kwargs["library_id"] == opened_library_id


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleRestoresOuterLibraryOnFailure:
    """Pin: a failed validation must restore the caller's outer current-library, not clear it.

    The IDE/server use case: a process sets a current library (e.g. for an
    in-flight pipeline run or an open project), then calls a validation entry
    point for a user edit. If that validation fails, the ``finally`` block
    must restore the outer ``_library_id`` ContextVar to what the caller had
    set — clearing it strands every subsequent ``get_current_library()`` in
    the same async context with ``RuntimeError: No current library set``.

    Covers both entry points that touch ``_library_id``:
    ``validate_bundle`` and ``validate_bundles_from_directory``.
    """

    async def test_validate_bundle_restores_previous_current_library(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)
            with pytest.raises(ValidateBundleError):
                await validate_bundle(mthds_contents=[_VALID_MTHDS])
            assert get_current_library() == outer_library_id
        finally:
            clear_current_library()

    async def test_validate_bundles_from_directory_restores_previous_current_library(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            mocker.patch.object(validate_bundle_module, "ValidateBundleResult", _BrokenResult)
            with tempfile.TemporaryDirectory() as tmp_dir:
                (Path(tmp_dir) / "test.mthds").write_text(_VALID_MTHDS, encoding="utf-8")
                with pytest.raises(ValidateBundleError):
                    await validate_bundles_from_directory(directory=Path(tmp_dir))
            assert get_current_library() == outer_library_id
        finally:
            clear_current_library()
