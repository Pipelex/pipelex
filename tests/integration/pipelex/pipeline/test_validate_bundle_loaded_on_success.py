"""Pin: a successful ``validate_bundle`` leaves the library loaded + current (D6 inner-sweep contract).

The build inputs/output CLIs and the inputs template engine (``build_inputs_for_pipe``) call
``validate_bundle`` and then immediately ``get_required_entry_pipe(...)`` against the library it left
open. The migration to ``BundleValidator.validate_pipes`` — the public inner sweep, which
deliberately never tears the library down — must preserve this: a sweep that tore the library down on
success would strand every one of those callers with ``No current library set`` /
``PipeNotFoundError``.
"""

from __future__ import annotations

import pytest

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, get_required_entry_pipe
from pipelex.pipeline.inputs_template import build_inputs_for_pipe
from pipelex.pipeline.validate_bundle import validate_bundle

_LOADED_DOMAIN = "loaded_on_success"
_LOADED_MTHDS = f"""
domain = "{_LOADED_DOMAIN}"
description = "Bundle pinning the loaded-on-success caller contract"

[concept.Doc]
description = "A document"

[pipe.summarize_doc]
type = "PipeLLM"
description = "Summarize a document"
inputs = {{ doc = "Doc" }}
output = "Text"
prompt = "Summarize $doc"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleLoadedOnSuccess:
    async def test_entry_pipe_resolves_after_successful_validation(self) -> None:
        # The inner sweep never tears down on success: the library stays open + current, so a caller can
        # resolve the just-validated pipe without re-opening anything.
        result = await validate_bundle(mthds_contents=[_LOADED_MTHDS])
        library_id = get_current_library_id_or_none()
        try:
            assert library_id is not None, "validate_bundle must leave the library current on success"
            pipe = get_required_entry_pipe(pipe_code=f"{_LOADED_DOMAIN}.summarize_doc")
            assert pipe.pipe_ref == f"{_LOADED_DOMAIN}.summarize_doc"
            assert result.dry_run_result[f"{_LOADED_DOMAIN}.summarize_doc"].status.is_success
        finally:
            if library_id is not None:
                get_library_manager().teardown(library_id=library_id)
            clear_current_library()

    async def test_inputs_template_resolves_pipe_after_validation(self) -> None:
        # The inputs template engine validates the bundle, then resolves the pipe and renders its inputs
        # against the still-open library — the loaded-on-success contract in action.
        inputs_result = await build_inputs_for_pipe(mthds_contents=[_LOADED_MTHDS], pipe_code="summarize_doc")
        library_id = get_current_library_id_or_none()
        try:
            assert inputs_result["pipe_ref"] == f"{_LOADED_DOMAIN}.summarize_doc"
            assert "doc" in inputs_result["inputs"]
        finally:
            if library_id is not None:
                get_library_manager().teardown(library_id=library_id)
            clear_current_library()
