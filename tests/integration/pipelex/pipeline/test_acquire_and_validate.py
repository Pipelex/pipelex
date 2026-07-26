"""Integration tests for ``BundleValidator.acquire_and_validate`` (standalone validate-all lifecycle, D6).

``acquire_and_validate`` opens a fresh library, loads the resolved dirs + contents, sweeps **all**
loaded pipes, and **always** tears the acquired library down — restoring the caller's outer
current-library first (so the guarantee survives a teardown raise). These pin (finding #7): the acquired
library is torn down and the outer current-library is restored on **both** the success path and a raise
mid-sweep, plus the strict-mode ``is_signature`` filter that excludes standalone signatures from the
sweep. ``library_dirs=[]`` disables base/PIPELEXPATH loading so the sweep is scoped to the bundle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pytest

from pipelex.method_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunStatus

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_AAV_DOMAIN = "acquire_validate"
_AAV_MTHDS = f"""
domain = "{_AAV_DOMAIN}"
description = "Bundle for acquire_and_validate lifecycle tests"

[concept.Doc]
description = "A document"

[pipe.leaf]
type = "PipeLLM"
description = "An implemented leaf"
inputs = {{ doc = "Doc" }}
output = "Text"
prompt = "Summarize $doc"

[pipe.standalone_sig]
description = "A standalone signature reached by nothing"
inputs = {{ doc = "Doc" }}
output = "Text"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestAcquireAndValidate:
    async def test_success_restores_outer_current_and_tears_down_acquired(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        teardown_spy = mocker.spy(get_library_manager(), "teardown")
        try:
            # Lenient mode so the standalone signature dry-runs (as a mock) rather than tripping the
            # strict pre-pass — keeps this test focused on the lifecycle, not signature policy.
            results = await BundleValidator().acquire_and_validate(mthds_contents=[_AAV_MTHDS], library_dirs=[], allow_signatures=True)

            # The outer current-library is restored (not cleared, not left on the acquired id).
            assert get_current_library_id_or_none() == outer_library_id
            # The acquired library (a fresh id, distinct from the outer) was torn down.
            torn_down_ids = {call.kwargs.get("library_id") for call in teardown_spy.call_args_list}
            assert any(library_id not in {None, outer_library_id} for library_id in torn_down_ids)
            # All loaded pipes were swept.
            assert f"{_AAV_DOMAIN}.leaf" in results
        finally:
            clear_current_library()

    async def test_raise_mid_sweep_restores_outer_current_and_tears_down_acquired(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        teardown_spy = mocker.spy(get_library_manager(), "teardown")
        # Force the sweep to raise AFTER the library is acquired, so only the `finally` can restore + tear down.
        mocker.patch.object(BundleValidator, "validate_pipes", new=mocker.AsyncMock(side_effect=DryRunError("boom mid-sweep")))
        try:
            with pytest.raises(DryRunError):
                await BundleValidator().acquire_and_validate(mthds_contents=[_AAV_MTHDS], library_dirs=[], allow_signatures=True)

            assert get_current_library_id_or_none() == outer_library_id
            torn_down_ids = {call.kwargs.get("library_id") for call in teardown_spy.call_args_list}
            assert any(library_id not in {None, outer_library_id} for library_id in torn_down_ids)
        finally:
            clear_current_library()

    async def test_strict_mode_filters_standalone_signature_from_sweep(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            # Strict (default): the standalone signature is filtered out of the swept set entirely, so it
            # neither trips the pre-pass (nothing reaches it) nor appears in the result map; the leaf passes.
            results = await BundleValidator().acquire_and_validate(mthds_contents=[_AAV_MTHDS], library_dirs=[])

            assert results[f"{_AAV_DOMAIN}.leaf"].status == DryRunStatus.SUCCESS
            assert f"{_AAV_DOMAIN}.standalone_sig" not in results
        finally:
            clear_current_library()
