"""Integration: ``validate_bundle`` threads a real ``source`` onto its structured errors.

Two channels are pinned here:

- The API submits sourceless bundle text (``mthds_contents: list[str]``), so without
  a per-item source the in-memory load path sets ``blueprint.source = None`` and
  cross-file diagnostics misfire. ``validate_bundle(mthds_sources=...)`` pairs each
  content with its logical source, so the loaded blueprint — and any
  ``ValidateBundleError`` it raises — carries a real ``source`` the consumer can map
  to the owning file. The CLI's on-disk path keeps using real file paths and is
  unaffected.
- Pipe-channel errors (``PipeValidationError`` raised during library validation)
  don't know their file at the raise site; the translate funnel backfills
  ``file_path`` from the library manager's pipe-source map (keyed by the full
  ``domain.pipe_code`` ref) so the categorized item — and the suggested fix riding
  it — names the declaring ``.mthds`` file even in multi-file libraries.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexUnexpectedError, ValidationErrorCategory, ValidationErrorItem
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import (
    _backfill_pipe_error_source,  # pyright: ignore[reportPrivateUsage]
    validate_bundle,
)
from pipelex.validation_error_types import PipeValidationErrorType

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

# An unclosed table header is a TOML *syntax* error: it fails in the interpreter before any
# blueprint dict exists, so the interpreter must attach the threaded source directly to the
# structured error item.
_MALFORMED_TOML_MTHDS = """
domain = "testapp"
[concept.Customer
description = "the table header above is never closed"
"""

# Deliberate INADEQUATE_OUTPUT_MULTIPLICITY: the sequence declares a single Idea while its last
# step yields a list — a pipe-channel error raised during library validation, far from any file.
_ENTRY_SEQ_MISMATCH_MTHDS = """domain = "srcthread_entry"
main_pipe = "list_ideas"

[concept]
Idea = "An idea."

[pipe.gen_ideas]
type = "PipeLLM"
description = "Generate ideas."
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Generate ideas about $topic"

[pipe.list_ideas]
type = "PipeSequence"
description = "Sequence declaring a single output while the last step yields a list."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "gen_ideas", result = "ideas" },
]
"""

# Same deliberate mismatch, declared by a *sibling* library file (different domain), so the
# pipe-channel error must carry the sibling's path — not the entry file's.
_SIBLING_SEQ_MISMATCH_MTHDS = _ENTRY_SEQ_MISMATCH_MTHDS.replace("srcthread_entry", "srcthread_sibling")

_ENTRY_INPUT_DRIFT_MTHDS = """domain = "srcthread_input_entry"
main_pipe = "make_summary"

[concept]
Summary = "A summary of a text."

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize the text."
inputs = { text = "Text", style = "Text" }
output = "Summary"
prompt = "Summarize $text in style $style"

[pipe.make_summary]
type = "PipeSequence"
description = "Sequence with drifted inputs."
inputs = { text = "Number", note = "Text" }
output = "Summary"
steps = [
  { pipe = "write_summary", result = "summary" },
]
"""

_SIBLING_INPUT_DRIFT_MTHDS = _ENTRY_INPUT_DRIFT_MTHDS.replace("srcthread_input_entry", "srcthread_input_sibling")

_VALID_ENTRY_MTHDS = """domain = "srcthread_valid"
main_pipe = "say_hi"

[pipe.say_hi]
type = "PipeLLM"
description = "Say hi."
output = "Text"
prompt = "Say hi"
"""


def _pipe_channel_items(exc: ValidateBundleError, *, error_type: PipeValidationErrorType) -> list[ValidationErrorItem]:
    report = exc.to_error_report()
    assert report.validation_errors is not None
    return [item for item in report.validation_errors if item.category == ValidationErrorCategory.PIPE_VALIDATION and item.error_type == error_type]


def _input_drift_items(exc: ValidateBundleError) -> list[ValidationErrorItem]:
    report = exc.to_error_report()
    assert report.validation_errors is not None
    input_drift_types = {
        PipeValidationErrorType.MISSING_INPUT_VARIABLE,
        PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
        PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
    }
    return [
        item for item in report.validation_errors if item.category == ValidationErrorCategory.PIPE_VALIDATION and item.error_type in input_drift_types
    ]


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleSourceThreading:
    async def test_old_injected_manager_path_source_is_normalized(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Managers implementing the former ``Path`` return contract remain compatible."""
        source_path = tmp_path / "legacy.mthds"
        manager = mocker.Mock()
        manager.get_pipe_source.return_value = source_path
        mocker.patch("pipelex.pipeline.validate_bundle.get_library_manager", return_value=manager)
        pipe_error = PipeValidationError(message="invalid", domain_code="demo", pipe_code="broken")

        _backfill_pipe_error_source(pipe_error)

        assert pipe_error.file_path == str(source_path)

    async def test_valid_bundle_blueprint_carries_threaded_source(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A valid bundle's loaded blueprint records the threaded per-content source as ``source``."""
        load_empty_library()
        result = await validate_bundle(mthds_contents=[_VALID_MTHDS], mthds_sources=["api://bundle-0.mthds"])
        assert result.blueprints[0].source == "api://bundle-0.mthds"

    async def test_source_none_without_names(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Without ``mthds_sources`` the in-memory path leaves ``source`` unset (unchanged behavior)."""
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
            await validate_bundle(mthds_contents=[_INVALID_MAIN_PIPE_MTHDS], mthds_sources=["broken.mthds"])
        report = exc_info.value.to_error_report()
        assert report.validation_errors is not None
        seeded_items = [item for item in report.validation_errors if item.source == "broken.mthds"]
        assert seeded_items, "no validation_errors item carried the threaded source"
        assert any(item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION for item in seeded_items)

    async def test_parse_level_failure_carries_threaded_source(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A TOML-syntax error surfaces a blueprint-validation item with the threaded source.

        Parse-level failures happen before a ``PipelexBundleBlueprint`` exists, so they cannot read
        ``blueprint.source``. The interpreter must attach the caller-supplied logical source directly
        to the structured blueprint-validation item; otherwise API/MCP clients receive an error
        message they cannot map back to the submitted file.
        """
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_MALFORMED_TOML_MTHDS], mthds_sources=["broken.mthds"])
        report = exc_info.value.to_error_report()
        assert report.validation_errors, "a parse-level failure must still carry a non-empty validation_errors[]"
        assert all(item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION for item in report.validation_errors)
        assert [item.source for item in report.validation_errors] == ["broken.mthds"]

    async def test_length_mismatch_is_a_host_contract_error(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A ``mthds_sources``/``mthds_contents`` length mismatch is a host wiring bug, not user input.

        It must raise an internal error (→ 500, redacted under STRICT), not a caller-facing
        ``ValidateBundleError`` (→ 422) — ``mthds_sources`` is never supplied by the end caller.
        """
        load_empty_library()
        with pytest.raises(PipelexUnexpectedError, match="must be a per-item source list matching mthds_contents"):
            await validate_bundle(mthds_contents=[_VALID_MTHDS], mthds_sources=["a.mthds", "b.mthds"])

    async def test_pipe_channel_error_carries_entry_file_source(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A pipe-channel error on an entry-file pipe carries the entry file as ``source``.

        The raise site (``PipeSequence.validate_output_with_library``) doesn't know the file;
        the translate funnel must backfill it from the library manager's pipe-source map so the
        suggested fix riding the item is addressable to a file.
        """
        load_empty_library()
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_ENTRY_SEQ_MISMATCH_MTHDS, encoding="utf-8")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        items = _pipe_channel_items(exc_info.value, error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY)
        assert items, "expected a pipe-channel INADEQUATE_OUTPUT_MULTIPLICITY item"
        for item in items:
            assert item.source is not None, "pipe-channel item must carry the declaring file as source"
            assert Path(item.source).resolve() == bundle_path.resolve()
            assert item.suggested_fix is not None
            assert item.suggested_fix.source == item.source

    async def test_pipe_channel_error_carries_sibling_file_source(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A pipe-channel error on a pipe declared by a sibling library file names the sibling.

        This is what makes multi-file fix targeting possible: the fix must patch the declaring
        file, never the entry file's same-named table.
        """
        load_empty_library()
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_VALID_ENTRY_MTHDS, encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        sibling_path = libs_dir / "sibling.mthds"
        sibling_path.write_text(_SIBLING_SEQ_MISMATCH_MTHDS, encoding="utf-8")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[libs_dir])

        items = _pipe_channel_items(exc_info.value, error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY)
        assert items, "expected a pipe-channel INADEQUATE_OUTPUT_MULTIPLICITY item"
        for item in items:
            assert item.source is not None, "sibling-declared pipe error must carry the sibling file as source"
            assert Path(item.source).resolve() == sibling_path.resolve()
            assert item.suggested_fix is not None
            assert item.suggested_fix.source == item.source

    async def test_input_drift_error_carries_entry_file_source(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A fixable input-drift pipe-channel error carries the entry file as ``source``."""
        load_empty_library()
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_ENTRY_INPUT_DRIFT_MTHDS, encoding="utf-8")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        items = _input_drift_items(exc_info.value)
        assert items, "expected a pipe-channel controller-input-drift item"
        for item in items:
            assert item.source is not None
            assert Path(item.source).resolve() == bundle_path.resolve()
            assert item.suggested_fix is not None
            assert item.suggested_fix.fix_code == "sync-controller-inputs"
            assert item.suggested_fix.source == item.source

    async def test_input_drift_error_carries_sibling_file_source(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A fixable input-drift error in a sibling library file names that sibling file."""
        load_empty_library()
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_VALID_ENTRY_MTHDS, encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        sibling_path = libs_dir / "sibling.mthds"
        sibling_path.write_text(_SIBLING_INPUT_DRIFT_MTHDS, encoding="utf-8")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[libs_dir])

        items = _input_drift_items(exc_info.value)
        assert items, "expected a pipe-channel controller-input-drift item"
        for item in items:
            assert item.source is not None
            assert Path(item.source).resolve() == sibling_path.resolve()
            assert item.suggested_fix is not None
            assert item.suggested_fix.fix_code == "sync-controller-inputs"
            assert item.suggested_fix.source == item.source

    async def test_pipe_channel_lookup_miss_leaves_source_absent(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """When the pipe-source map has no entry (sourceless in-memory content), ``source`` stays unset.

        The backfill must only set what it can prove — a lookup miss falls back to the source-less
        conservative path, never a guess.
        """
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_ENTRY_SEQ_MISMATCH_MTHDS])

        items = _pipe_channel_items(exc_info.value, error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY)
        assert items, "expected a pipe-channel INADEQUATE_OUTPUT_MULTIPLICITY item"
        for item in items:
            assert item.source is None

    async def test_pipe_channel_error_preserves_logical_source(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A pipe-channel error on an in-memory bundle keeps its logical URI source verbatim.

        The backfill reads the source from the library manager's pipe-source map. A logical
        source like ``api://bundle-0.mthds`` (passed via ``mthds_sources``) must survive the
        round-trip unchanged — never mangled to ``api:/bundle-0.mthds`` by a ``Path`` coercion —
        so API/MCP clients can map the diagnostic and its suggested fix back to the submitted
        bundle.
        """
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_ENTRY_SEQ_MISMATCH_MTHDS], mthds_sources=["api://bundle-0.mthds"])

        items = _pipe_channel_items(exc_info.value, error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY)
        assert items, "expected a pipe-channel INADEQUATE_OUTPUT_MULTIPLICITY item"
        for item in items:
            assert item.source == "api://bundle-0.mthds"
            assert item.suggested_fix is not None
            assert item.suggested_fix.source == "api://bundle-0.mthds"
