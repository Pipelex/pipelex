"""Golden coverage for the light (signature-driven) inputs template — the real end-to-end path.

Unlike the pure-transform unit test, this loads the actual Smart-Inputs fixture bundles so the real
``resolve_input_kind`` runs against a loaded concept library. It pins:

- the light JSON default for a mixed-signature pipe (bare string / bare number / structured dict /
  list of bare strings, and file-ish URL strings / structured-list),
- the light TOML default carrying a ``# concept: ...`` comment per key and loading back to the same
  light dict, and
- ``--explicit`` reproducing the ceremonial ``{concept, content}`` envelope template.

Both formats compose with the same ``explicit`` switch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import tomli

from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_required_entry_pipe,
    set_current_library,
)
from pipelex.pipe_machinery.rendering.input_renderer import render_inputs, render_inputs_toml
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.test_extras.mthds_corpus.loader import get_entry

if TYPE_CHECKING:
    from collections.abc import Callable

#: Anchored on the `tests/` root by name rather than by a parent count: a depth index silently
#: resolves to the wrong directory when the module moves, which is exactly what happened when this
#: test followed `input_renderer` out of `core/pipes/` into the `pipe_machinery/` mirror.
_TESTS_ROOT = next(parent for parent in Path(__file__).parents if parent.name == "tests")
_SMART_INPUTS = _TESTS_ROOT / "e2e" / "pipelex" / "pipes" / "smart_inputs"
#: The triage bundle is a corpus entry now — the corpus is the single source for language-level
#: `.mthds` methods, and `feature.smart_inputs` is exactly what this golden renders against.
_TRIAGE = get_entry(name="feature_smart_inputs_claims_triage").bundle_path
_FILES = _SMART_INPUTS / "smart_inputs_files" / "smart_inputs_files.mthds"


def _teardown_validation_library(outer_library_id: str) -> None:
    """Tear down the library `validate_bundle` left open on success, restoring the outer one."""
    validation_library_id = get_current_library_id_or_none()
    if validation_library_id is not None and validation_library_id != outer_library_id:
        set_current_library(library_id=outer_library_id)
        get_library_manager().teardown(library_id=validation_library_id)
    clear_current_library()


@pytest.mark.asyncio(loop_scope="class")
class TestInputRendererLightGolden:
    async def _load_pipe(self, bundle_path: Path, *, pipe_ref: str, load_empty_library: Callable[[], str]) -> tuple[Any, str]:
        outer_library_id = load_empty_library()
        await validate_bundle(mthds_file_path=bundle_path)
        the_pipe = get_required_entry_pipe(pipe_code=pipe_ref)
        return the_pipe, outer_library_id

    async def test_triage_light_json_default(self, load_empty_library: Callable[[], str]) -> None:
        """The default JSON template is the light shape: bare string/number, structured dict, list of bare strings."""
        the_pipe, outer_library_id = await self._load_pipe(_TRIAGE, pipe_ref="claims_desk.triage_case", load_empty_library=load_empty_library)
        try:
            light = json.loads(render_inputs(the_pipe))
        finally:
            _teardown_validation_library(outer_library_id)

        assert light == {
            "question": "text_value",
            "priority": 1,
            "invoice": {"invoice_number": "invoice_number_value", "amount": 0.0},
            "tags": ["text_value"],
        }

    async def test_triage_light_toml_carries_concept_comments(self, load_empty_library: Callable[[], str]) -> None:
        """The default TOML template carries the declared concept as a comment and loads back to the light dict."""
        the_pipe, outer_library_id = await self._load_pipe(_TRIAGE, pipe_ref="claims_desk.triage_case", load_empty_library=load_empty_library)
        try:
            toml_str = render_inputs_toml(the_pipe)
        finally:
            _teardown_validation_library(outer_library_id)

        assert "# concept: claims_desk.Question" in toml_str
        assert "# concept: claims_desk.Priority" in toml_str
        assert "# concept: claims_desk.Tag[]" in toml_str
        assert tomli.loads(toml_str) == {
            "question": "text_value",
            "priority": 1,
            "invoice": {"invoice_number": "invoice_number_value", "amount": 0.0},
            "tags": ["text_value"],
        }

    async def test_triage_explicit_reproduces_envelope(self, load_empty_library: Callable[[], str]) -> None:
        """--explicit reproduces the ceremonial {concept, content} envelope, in both JSON and TOML."""
        the_pipe, outer_library_id = await self._load_pipe(_TRIAGE, pipe_ref="claims_desk.triage_case", load_empty_library=load_empty_library)
        try:
            envelope = json.loads(render_inputs(the_pipe, explicit=True))
            envelope_toml = tomli.loads(render_inputs_toml(the_pipe, explicit=True))
        finally:
            _teardown_validation_library(outer_library_id)

        assert envelope["question"] == {"concept": "claims_desk.Question", "content": {"text": "text_value"}}
        assert envelope["priority"] == {"concept": "claims_desk.Priority", "content": {"number": 1}}
        assert envelope["tags"] == {"concept": "claims_desk.Tag", "content": [{"text": "text_value"}]}
        assert envelope_toml == envelope

    async def test_files_light_json_file_ish_and_structured_list(self, load_empty_library: Callable[[], str]) -> None:
        """File-ish inputs become bare URL strings; a structured list becomes a bare list of dicts."""
        the_pipe, outer_library_id = await self._load_pipe(
            _FILES, pipe_ref="smart_inputs_files_demo.review_case", load_empty_library=load_empty_library
        )
        try:
            light = json.loads(render_inputs(the_pipe))
        finally:
            _teardown_validation_library(outer_library_id)

        photo = light["photo"]
        assert isinstance(photo, str)
        assert photo.startswith("https://")
        exhibits = cast("list[Any]", light["exhibits"])
        assert len(exhibits) == 1
        first_exhibit = exhibits[0]
        assert isinstance(first_exhibit, str)
        assert first_exhibit.startswith("https://")
        assert light["people"] == [{"name": "name_value", "job": "job_value"}]
