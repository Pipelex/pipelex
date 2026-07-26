"""Integration tests for the public load + sweep composers consumers build on.

These pin the two surfaces downstream consumers (e.g. cocode) use instead of re-deriving the
open/set/load ceremony + ``get_pipes`` + ``is_signature`` filter + ``validate_pipes`` by hand:

- :func:`load_libraries_and_activate` opens a fresh library, loads the given dirs, and **leaves it
  loaded and current** (returns its id) — the loaded-library counterpart to ``acquire_and_validate``'s
  acquire-and-teardown lifecycle.
- :meth:`BundleValidator.validate_current_library` sweeps every (non-signature, in strict mode) pipe in
  the **current** library and **never** tears it down, so the same loaded library stays usable after.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, get_pipes
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunStatus
from pipelex.pipeline.execution_seams import load_libraries_and_activate

if TYPE_CHECKING:
    from pathlib import Path

_PVA_DOMAIN = "pub_validate_api"
_PVA_MTHDS = f"""domain = "{_PVA_DOMAIN}"
description = "Bundle for public validation API tests"

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


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    """Write the test bundle into a temp directory and return that directory."""
    (tmp_path / f"{_PVA_DOMAIN}.mthds").write_text(_PVA_MTHDS, encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio(loop_scope="class")
class TestPublicValidationApi:
    async def test_load_activates_and_sweep_leaves_library_loaded(self, library_dir: Path) -> None:
        library_id = load_libraries_and_activate([library_dir])
        try:
            # load_libraries_and_activate leaves the library open and current for the caller (no teardown).
            assert get_current_library_id_or_none() == library_id
            loaded_refs = {pipe.pipe_ref for pipe in get_pipes()}
            assert f"{_PVA_DOMAIN}.leaf" in loaded_refs
            assert f"{_PVA_DOMAIN}.standalone_sig" in loaded_refs

            # Strict sweep over the current library: the leaf passes; the standalone signature is filtered
            # out of the swept set entirely (validating one directly would always trip the pre-pass).
            results = await BundleValidator().validate_current_library()
            assert results[f"{_PVA_DOMAIN}.leaf"].status == DryRunStatus.SUCCESS
            assert f"{_PVA_DOMAIN}.standalone_sig" not in results

            # No teardown: the library is still loaded and current, so a second sweep runs identically.
            assert get_current_library_id_or_none() == library_id
            assert {pipe.pipe_ref for pipe in get_pipes()} == loaded_refs
            second = await BundleValidator().validate_current_library()
            assert second[f"{_PVA_DOMAIN}.leaf"].status == DryRunStatus.SUCCESS
        finally:
            clear_current_library()
            get_library_manager().teardown(library_id=library_id)

    async def test_lenient_mode_includes_signature_in_sweep(self, library_dir: Path) -> None:
        library_id = load_libraries_and_activate([library_dir])
        try:
            # Lenient mode keeps the standalone signature in the swept set — it dry-runs trivially by
            # minting a mock — so both pipes appear in the result map.
            results = await BundleValidator().validate_current_library(allow_signatures=True)
            assert results[f"{_PVA_DOMAIN}.leaf"].status == DryRunStatus.SUCCESS
            assert f"{_PVA_DOMAIN}.standalone_sig" in results
        finally:
            clear_current_library()
            get_library_manager().teardown(library_id=library_id)
