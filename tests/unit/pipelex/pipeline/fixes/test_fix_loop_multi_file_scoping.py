"""Unit test for the convergence loop's multi-file scoping guard.

A source-less fix is only provably targeted at the file being fixed when validation ran on
that single file. Under ``library_dirs``, a same-named pipe in another file's domain would
resolve to the wrong TOML table (pipe codes are only unique per domain), so the loop must
refuse to apply source-less fixes rather than risk patching an unrelated pipe. Real
multi-file targeting (threading ``file_path`` from the raise sites) is Phase 1 work.
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


def _sourceless_output_error() -> ValidateBundleError:
    """An enriched output-mismatch error with no source file — as all raise sites emit today."""
    return ValidateBundleError(
        message="Pipe validation failed",
        pipe_validation_errors=[
            PipesAndConceptValidationErrorData(
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code="other_domain",
                pipe_code="list_ideas",
                message="output mismatch",
                field_path="",
                expected_output_ref="Idea[]",
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
        """With library_dirs set, a source-less fix is dropped: the file must not be touched."""
        bundle_path = tmp_path / "scoping.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        library_dir = tmp_path / "library"
        library_dir.mkdir()
        validate_mock = mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=_sourceless_output_error(),
        )

        result = await fix_bundle_file(bundle_path, library_dirs=[library_dir])

        assert result.is_valid is False
        assert result.iterations == 0
        assert result.fixes_applied == []
        assert validate_mock.await_count == 1
        assert [item.error_type for item in result.remaining_errors] == [PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT]
        # The pipe table [pipe.list_ideas] DOES exist in this file — without the scoping
        # guard the applier would have patched it. The file must be byte-identical.
        assert bundle_path.read_text(encoding="utf-8") == _MINIMAL_MTHDS

    async def test_sourceful_blueprint_fix_applies_under_library_dirs(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """A fix whose ``source`` equals the file being fixed IS applied under library_dirs.

        The blueprint-channel native-redeclaration fix is the first to carry a populated
        ``source``; the loop's source/file check accepts it (unlike a source-less fix, dropped
        above) and targets only the declaring file.
        """
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

        result = await fix_bundle_file(bundle_path, library_dirs=[library_dir])

        assert result.is_valid is True
        assert result.iterations == 1
        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-native-concept-redecl"]
        # The redeclared concept is gone from the declaring file.
        assert "[concept.Text]" not in bundle_path.read_text(encoding="utf-8")

    async def test_sourceless_fix_still_applies_single_file(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Without library_dirs (single-file validation), the same source-less fix applies."""
        bundle_path = tmp_path / "scoping.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[_sourceless_output_error(), None],
        )

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 1
        assert len(result.fixes_applied) == 1
        # Assert on the parsed value, not raw spacing: the fix loop rewrites the whole file to
        # canonical MTHDS, and the formatter column-aligns this single-line table.
        fixed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        assert fixed["pipe"]["list_ideas"]["output"] == "Idea[]"
