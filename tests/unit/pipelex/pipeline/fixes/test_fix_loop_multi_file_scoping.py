"""Unit pins for the fix loop's multi-file scoping: the resolved-dirs single-file gate (D3.2),
the write-scope policy (D3.3), and per-file fix grouping (D3.4).

``validate_bundle`` — and, for the ambient-resolution cases, ``resolve_library_dirs`` — are
patched at the loop's namespace so each case pins exactly one scoping decision: which files the
loop is willing to patch, and where a fix actually lands. The rules under test:

- Single-file is derived from the RESOLVED dirs: an explicit ``[]`` is genuinely single-file
  (source-less fixes apply); a ``None`` that falls through to ambient dirs is multi-file
  (source-less fixes conservatively dropped).
- Write scope is the entry file plus per-call ``library_dirs`` only; files loaded via ambient
  resolution are read-only, and a run whose every fix targets a read-only file bails loudly.
"""

from pathlib import Path

import pytest
import tomlkit
from pytest_mock import MockerFixture

from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.fix_loop import fix_bundle_file

_MINIMAL_MTHDS = """domain = "seqfix_scoping"
main_pipe = "list_ideas"

[pipe.list_ideas]
type = "PipeLLM"
description = "A pipe whose code could collide with a same-named pipe in another domain."
inputs = { topic = "Text" }
output = "Text"
prompt = "Write about $topic"
"""

_NATIVE_REDECL_MTHDS = """domain = "nativefix_scoping"
main_pipe = "greet"

[concept.Text]
description = "Redeclared native Text."

[pipe.greet]
type = "PipeLLM"
description = "Greet."
inputs = { name = "Text" }
output = "Text"
prompt = "Greet $name"
"""

_SIBLING_MTHDS = """domain = "seqfix_scoping_sibling"

[pipe.sibling_pipe]
type = "PipeLLM"
description = "A sibling pipe with its own output mismatch."
inputs = { topic = "Text" }
output = "Text"
prompt = "Write about $topic"
"""

_DOTTED_SHARED_A_MTHDS = """domain = "rebuild_a"

[pipe."rebuild_a.shared"]
type = "PipeLLM"
description = "A dotted declaration that strips to a bare shared code."
inputs = { topic = "Text" }
output = "Text"
prompt = "Write about $topic"
"""

_DOTTED_SHARED_B_MTHDS = """domain = "rebuild_b"

[pipe."rebuild_b.shared"]
type = "PipeLLM"
description = "Another dotted declaration that strips to the same bare shared code."
inputs = { topic = "Text" }
output = "Text"
prompt = "Write about $topic"
"""


def _seq_output_error_data(*, pipe_code: str, source: str | None) -> PipesAndConceptValidationErrorData:
    """One enriched output-mismatch error datum — plans a ``match-sequence-output`` fix."""
    return PipesAndConceptValidationErrorData(
        error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
        domain_code="seqfix_scoping",
        source=source,
        pipe_code=pipe_code,
        message=f"pipe '{pipe_code}' output mismatch",
        field_path=source or "",
        expected_output_ref="Idea[]",
    )


def _seq_output_error(*, pipe_code: str, source: str | None) -> ValidateBundleError:
    return ValidateBundleError(
        message="Pipe validation failed",
        pipe_validation_errors=[_seq_output_error_data(pipe_code=pipe_code, source=source)],
    )


def _strip_namespace_error(*, pipe_code: str, stripped_pipe_code: str, source: str) -> ValidateBundleError:
    return ValidateBundleError(
        message="Blueprint validation failed",
        pipelex_bundle_blueprint_validation_errors=[
            PipelexBundleBlueprintValidationErrorData(
                error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX,
                source=source,
                pipe_code=pipe_code,
                stripped_pipe_code=stripped_pipe_code,
                message=f"Pipe code '{pipe_code}' should be '{stripped_pipe_code}'",
            ),
        ],
    )


@pytest.mark.asyncio(loop_scope="class")
class TestFixLoopMultiFileScoping:
    async def test_sourceless_fix_not_applied_under_library_dirs(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """With explicit library_dirs, a source-less fix is dropped: the file must not be touched."""
        bundle_path = tmp_path / "scoping.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        library_dir = tmp_path / "library"
        library_dir.mkdir()
        validate_mock = mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=_seq_output_error(pipe_code="list_ideas", source=None),
        )

        result = await fix_bundle_file(bundle_path, library_dirs=[library_dir], max_iterations=3)

        assert result.is_valid is False
        assert result.iterations == 0
        assert result.fixes_applied == []
        assert result.files_written == []
        assert validate_mock.await_count == 1
        assert [item.error_type for item in result.remaining_errors] == [PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT]
        # The pipe table [pipe.list_ideas] DOES exist in this file — without the scoping
        # guard the applier would have patched it. The file must be byte-identical.
        assert bundle_path.read_text(encoding="utf-8") == _MINIMAL_MTHDS

    async def test_explicit_empty_library_dirs_is_single_file(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """``library_dirs=[]`` resolves to no dirs — genuinely single-file, so a source-less fix applies."""
        bundle_path = tmp_path / "scoping.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[_seq_output_error(pipe_code="list_ideas", source=None), None],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=[], max_iterations=3)

        assert result.is_valid is True
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output"]
        assert [Path(written) for written in result.files_written] == [bundle_path.resolve()]
        fixed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        assert fixed["pipe"]["list_ideas"]["output"] == "Idea[]"

    async def test_none_falling_through_to_ambient_dirs_is_multi_file(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """``library_dirs=None`` resolving to ambient dirs is multi-file: a source-less fix is dropped."""
        bundle_path = tmp_path / "scoping.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        ambient_dir = tmp_path / "ambient"
        ambient_dir.mkdir()
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.resolve_library_dirs",
            return_value=([ambient_dir], "instance default"),
        )
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=_seq_output_error(pipe_code="list_ideas", source=None),
        )

        result = await fix_bundle_file(bundle_path, library_dirs=None, max_iterations=3)

        assert result.is_valid is False
        assert result.fixes_applied == []
        assert result.files_written == []
        assert bundle_path.read_text(encoding="utf-8") == _MINIMAL_MTHDS

    async def test_none_resolving_to_nothing_is_single_file(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """``library_dirs=None`` with nothing configured anywhere resolves single-file: fixes apply."""
        bundle_path = tmp_path / "scoping.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.resolve_library_dirs",
            return_value=([], "none configured"),
        )
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[_seq_output_error(pipe_code="list_ideas", source=None), None],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=None, max_iterations=3)

        assert result.is_valid is True
        assert result.iterations == 1
        fixed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        assert fixed["pipe"]["list_ideas"]["output"] == "Idea[]"

    async def test_sourceful_blueprint_fix_applies_under_library_dirs(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """A fix whose ``source`` equals the file being fixed IS applied under library_dirs."""
        bundle_path = tmp_path / "native_redecl.mthds"
        bundle_path.write_text(_NATIVE_REDECL_MTHDS, encoding="utf-8")
        library_dir = tmp_path / "library"
        library_dir.mkdir()
        redeclaration_error = ValidateBundleError(
            message="Blueprint validation failed",
            pipelex_bundle_blueprint_validation_errors=[
                PipelexBundleBlueprintValidationErrorData(
                    error_type=PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION,
                    domain_code="nativefix_scoping",
                    source=str(bundle_path),
                    concept_code="Text",
                    message="Cannot declare a concept named 'Text' because it is natively available in Pipelex.",
                ),
            ],
        )
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[redeclaration_error, None],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=[library_dir], max_iterations=3)

        assert result.is_valid is True
        assert result.iterations == 1
        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-native-concept-redecl"]
        # The redeclared concept is gone from the declaring file.
        assert "[concept.Text]" not in bundle_path.read_text(encoding="utf-8")

    async def test_sourced_fix_under_explicit_library_dir_writes_the_sibling(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """A fix sourced at a sibling under a per-call ``-L`` dir patches the sibling, not the entry."""
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        sibling_path = libs_dir / "sibling.mthds"
        sibling_path.write_text(_SIBLING_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[_seq_output_error(pipe_code="sibling_pipe", source=str(sibling_path)), None],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=[libs_dir], max_iterations=3)

        assert result.is_valid is True
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output"]
        assert [Path(written) for written in result.files_written] == [sibling_path.resolve()]
        fixed_sibling = tomlkit.loads(sibling_path.read_text(encoding="utf-8")).unwrap()
        assert fixed_sibling["pipe"]["sibling_pipe"]["output"] == "Idea[]"
        assert bundle_path.read_text(encoding="utf-8") == _MINIMAL_MTHDS

    async def test_fix_sourced_at_ambient_file_bails_out_of_scope(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """A fix sourced at a file loaded via ambient resolution is read-only: loud bail, no write.

        The user did not pass that directory to THIS command, so the loop must not write there —
        and the outcome must be actionable, naming the out-of-scope file and the -L remedy.
        """
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        ambient_dir = tmp_path / "ambient"
        ambient_dir.mkdir()
        ambient_sibling = ambient_dir / "ambient_sibling.mthds"
        ambient_sibling.write_text(_SIBLING_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.resolve_library_dirs",
            return_value=([ambient_dir], "instance default"),
        )
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=_seq_output_error(pipe_code="sibling_pipe", source=str(ambient_sibling)),
        )

        result = await fix_bundle_file(bundle_path, library_dirs=None, max_iterations=3)

        assert result.is_valid is False
        assert result.fixes_applied == []
        assert result.files_written == []
        assert result.bail_reason is not None
        assert "outside write scope" in result.bail_reason
        assert str(ambient_sibling.resolve()) in result.bail_reason
        assert "-L" in result.bail_reason
        assert ambient_sibling.read_text(encoding="utf-8") == _SIBLING_MTHDS
        # The remaining errors still carry the suggested fix (with its source) for the consumer.
        assert result.remaining_errors
        assert result.remaining_errors[0].suggested_fix is not None
        assert result.remaining_errors[0].suggested_fix.source == str(ambient_sibling)

    async def test_entry_file_sourced_fix_is_always_writable(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """A fix sourced at the entry file itself applies even when it was loaded via ambient dirs."""
        ambient_dir = tmp_path / "ambient"
        ambient_dir.mkdir()
        bundle_path = ambient_dir / "entry.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.resolve_library_dirs",
            return_value=([ambient_dir], "instance default"),
        )
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[_seq_output_error(pipe_code="list_ideas", source=str(bundle_path)), None],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=None, max_iterations=3)

        assert result.is_valid is True
        assert [Path(written) for written in result.files_written] == [bundle_path.resolve()]
        fixed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        assert fixed["pipe"]["list_ideas"]["output"] == "Idea[]"

    async def test_mixed_scope_applies_in_scope_and_reports_out_of_scope(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """In-scope fixes proceed even when other fixes target read-only files (no all-or-nothing)."""
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        ambient_dir = tmp_path / "ambient"
        ambient_dir.mkdir()
        ambient_sibling = ambient_dir / "ambient_sibling.mthds"
        ambient_sibling.write_text(_SIBLING_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.resolve_library_dirs",
            return_value=([ambient_dir], "instance default"),
        )
        entry_error = _seq_output_error_data(pipe_code="list_ideas", source=str(bundle_path))
        ambient_error = _seq_output_error_data(pipe_code="sibling_pipe", source=str(ambient_sibling))
        both_errors = ValidateBundleError(message="bundle invalid", pipe_validation_errors=[entry_error, ambient_error])
        only_ambient_left = ValidateBundleError(message="bundle invalid", pipe_validation_errors=[ambient_error])
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[both_errors, only_ambient_left],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=None, max_iterations=3)

        assert result.is_valid is False
        assert result.iterations == 1
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output"]
        assert [Path(written) for written in result.files_written] == [bundle_path.resolve()]
        fixed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        assert fixed["pipe"]["list_ideas"]["output"] == "Idea[]"
        assert ambient_sibling.read_text(encoding="utf-8") == _SIBLING_MTHDS
        assert result.bail_reason is not None
        assert "outside write scope" in result.bail_reason

    async def test_one_iteration_groups_fixes_per_target_file(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Two fixes targeting two files in ONE iteration each land in their own file (D3.4 grouping)."""
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        sibling_path = libs_dir / "sibling.mthds"
        sibling_path.write_text(_SIBLING_MTHDS, encoding="utf-8")
        entry_error = _seq_output_error_data(pipe_code="list_ideas", source=str(bundle_path))
        sibling_error = _seq_output_error_data(pipe_code="sibling_pipe", source=str(sibling_path))
        both_errors = ValidateBundleError(message="bundle invalid", pipe_validation_errors=[entry_error, sibling_error])
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[both_errors, None],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=[libs_dir], max_iterations=3)

        assert result.is_valid is True
        assert result.iterations == 1
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output", "match-sequence-output"]
        assert [Path(written) for written in result.files_written] == [bundle_path.resolve(), sibling_path.resolve()]
        fixed_entry = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        fixed_sibling = tomlkit.loads(sibling_path.read_text(encoding="utf-8")).unwrap()
        assert fixed_entry["pipe"]["list_ideas"]["output"] == "Idea[]"
        assert fixed_sibling["pipe"]["sibling_pipe"]["output"] == "Idea[]"

    async def test_collision_scan_rebuilds_after_each_written_round(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """A rename from round one blocks a sibling rename proposed in round two.

        If the cross-file map were cached before the loop, the second ``strip-namespace`` fix
        would not see that round one already created ``[pipe.shared]`` in a sibling bundle.
        """
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        first_path = libs_dir / "a_first.mthds"
        first_path.write_text(_DOTTED_SHARED_A_MTHDS, encoding="utf-8")
        second_path = libs_dir / "b_second.mthds"
        second_path.write_text(_DOTTED_SHARED_B_MTHDS, encoding="utf-8")
        validate_mock = mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[
                _strip_namespace_error(pipe_code="rebuild_a.shared", stripped_pipe_code="shared", source=str(first_path)),
                _strip_namespace_error(pipe_code="rebuild_b.shared", stripped_pipe_code="shared", source=str(second_path)),
            ],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=[libs_dir], max_iterations=3)

        assert result.is_valid is False
        assert result.iterations == 1
        assert validate_mock.await_count == 2
        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-namespace"]
        assert [Path(written) for written in result.files_written] == [first_path.resolve()]
        assert result.bail_reason is not None
        assert "cross-file collision" in result.bail_reason
        assert "'shared'" in result.bail_reason
        fixed_first = tomlkit.loads(first_path.read_text(encoding="utf-8")).unwrap()
        unchanged_second = tomlkit.loads(second_path.read_text(encoding="utf-8")).unwrap()
        assert "shared" in fixed_first["pipe"]
        assert "rebuild_a.shared" not in fixed_first["pipe"]
        assert "rebuild_b.shared" in unchanged_second["pipe"]

    async def test_max_iterations_none_reads_the_config_default(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """``max_iterations=None`` resolves to ``builder_config.fix_loop_max_attempts`` (D3.5)."""
        bundle_path = tmp_path / "scoping.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        fake_config = mocker.MagicMock()
        fake_config.pipelex.builder_config.fix_loop_max_attempts = 1
        mocker.patch("pipelex.pipeline.fixes.fix_loop.get_config", return_value=fake_config)
        # The error persists past the single allowed apply round: the loop must run exactly one
        # round then take its final-validation verdict and bail on max_iterations.
        validate_mock = mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[
                _seq_output_error(pipe_code="list_ideas", source=None),
                _seq_output_error(pipe_code="list_ideas", source=None),
            ],
        )

        result = await fix_bundle_file(bundle_path, library_dirs=[])

        assert result.is_valid is False
        assert result.iterations == 1
        assert result.bail_reason is not None
        assert "max_iterations (1)" in result.bail_reason
        assert validate_mock.await_count == 2
