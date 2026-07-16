"""Pin: a successful ``validate_bundle`` leaves the library loaded + current (D6 inner-sweep contract).

The build/inputs/output CLIs and builder operations (``inputs_ops``, ``output_ops``,
``runner_code_ops``, ``validate_pipe_in_bundle``) call ``validate_bundle`` (or ``validate_pipes``
directly) and then immediately ``get_required_pipe(...)`` against the library it left open. The
migration to ``BundleValidator.validate_pipes`` — the public inner sweep, which deliberately never
tears the library down — must preserve this: a sweep that tore the library down on success would
strand every one of those callers with ``No current library set`` / ``PipeNotFoundError``.
"""

from __future__ import annotations

import pytest

from pipelex.builder.operations.runner_code_ops import build_runner_code_for_pipe
from pipelex.hub import clear_current_library, get_current_library_id_or_none, get_library_manager, get_required_pipe
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
    async def test_get_required_pipe_works_after_successful_validation(self) -> None:
        # The inner sweep never tears down on success: the library stays open + current, so a caller can
        # resolve the just-validated pipe without re-opening anything.
        result = await validate_bundle(mthds_contents=[_LOADED_MTHDS])
        library_id = get_current_library_id_or_none()
        try:
            assert library_id is not None, "validate_bundle must leave the library current on success"
            pipe = get_required_pipe(pipe_code=f"{_LOADED_DOMAIN}.summarize_doc")
            assert pipe.pipe_ref == f"{_LOADED_DOMAIN}.summarize_doc"
            assert result.dry_run_result[f"{_LOADED_DOMAIN}.summarize_doc"].status.is_success
        finally:
            if library_id is not None:
                get_library_manager().teardown(library_id=library_id)
            clear_current_library()

    async def test_runner_code_ops_resolves_pipe_after_inner_sweep(self) -> None:
        # runner_code_ops is the caller that drives the inner sweep (validate_pipes) directly and then
        # resolves + generates code against the still-open library — the loaded-on-success contract in action.
        runner_code = await build_runner_code_for_pipe(mthds_contents=[_LOADED_MTHDS], pipe_code="summarize_doc")
        library_id = get_current_library_id_or_none()
        try:
            assert "summarize_doc" in runner_code
        finally:
            if library_id is not None:
                get_library_manager().teardown(library_id=library_id)
            clear_current_library()
