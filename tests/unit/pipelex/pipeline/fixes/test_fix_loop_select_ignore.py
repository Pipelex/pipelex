"""Unit pins for the fix loop's rule filters: keyword-only ``select_codes`` / ``ignore_codes``.

The filters select *behavior* (which rules may write to disk), applied inside the loop's
safe-fix collection so every consumer — the agent CLI's ``--select``/``--ignore`` today, the
human CLI later — inherits identical semantics. Validation of the codes themselves (unknown
code → loud rejection) is the CLI layer's job, not the loop's.
"""

from pathlib import Path

import pytest
import tomlkit
from pytest_mock import MockerFixture

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.fix_loop import fix_bundle_file

_BUNDLE_MTHDS = """domain = "selectfix"
main_pipe = "list_ideas"

[concept.Idea]
description = "An idea."

[pipe.list_ideas]
type = "PipeLLM"
description = "List ideas."
inputs = { topic = "Text" }
output = "Idea"
prompt = "Write about $topic"
"""


def _two_rule_error() -> ValidateBundleError:
    """One error per channel: a pipe-channel output mismatch AND a blueprint-channel native
    concept redeclaration — planning two fixes with two distinct fix codes.
    """
    output_error = PipesAndConceptValidationErrorData(
        error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
        domain_code="selectfix",
        pipe_code="list_ideas",
        message="output mismatch",
        field_path="",
        expected_output_ref="Idea[]",
    )
    redeclaration_error = PipelexBundleBlueprintValidationErrorData(
        error_type=PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION,
        domain_code="selectfix",
        concept_code="Idea",
        message="Cannot redeclare native concept 'Idea'.",
    )
    return ValidateBundleError(
        message="bundle invalid",
        pipelex_bundle_blueprint_validation_errors=[redeclaration_error],
        pipe_validation_errors=[output_error],
    )


@pytest.mark.asyncio(loop_scope="class")
class TestFixLoopSelectIgnore:
    async def test_select_applies_only_the_selected_rule(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """``select_codes`` keeps only the named rules: the other planned fix is never applied."""
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_BUNDLE_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[_two_rule_error(), _two_rule_error()],
        )

        result = await fix_bundle_file(
            bundle_path,
            library_dirs=[],
            max_iterations=1,
            select_codes=["match-sequence-output"],
        )

        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output"]
        parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        assert parsed["pipe"]["list_ideas"]["output"] == "Idea[]"
        # The ignored rule's target is untouched: the concept declaration survives.
        assert "Idea" in parsed["concept"]

    async def test_ignore_drops_the_named_rule(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """``ignore_codes`` drops the named rules and keeps the rest."""
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_BUNDLE_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[_two_rule_error(), _two_rule_error()],
        )

        result = await fix_bundle_file(
            bundle_path,
            library_dirs=[],
            max_iterations=1,
            ignore_codes=["match-sequence-output"],
        )

        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-native-concept-redecl"]
        parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        assert parsed["pipe"]["list_ideas"]["output"] == "Idea"
        assert "Idea" not in parsed.get("concept", {})

    async def test_everything_filtered_out_is_a_plain_no_fix_result(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """When the filters drop every fix, the result is the ordinary no-applicable-fixes shape."""
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_BUNDLE_MTHDS, encoding="utf-8")
        validate_mock = mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=_two_rule_error(),
        )

        result = await fix_bundle_file(
            bundle_path,
            library_dirs=[],
            max_iterations=3,
            select_codes=["strip-namespace"],
        )

        assert result.is_valid is False
        assert result.iterations == 0
        assert result.fixes_applied == []
        assert result.files_written == []
        assert validate_mock.await_count == 1
        assert bundle_path.read_text(encoding="utf-8") == _BUNDLE_MTHDS
        # The dropped fixes still ride the remaining errors for the consumer to see.
        assert [item.suggested_fix.fix_code for item in result.remaining_errors if item.suggested_fix is not None] == [
            "strip-native-concept-redecl",
            "match-sequence-output",
        ]
