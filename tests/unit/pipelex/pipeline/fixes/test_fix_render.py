"""Unit tests for agent-facing fix result markdown."""

from typing import Any

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.pipeline.fixes.fix_loop import FixBundleResult
from pipelex.pipeline.fixes.fix_render import format_fix_markdown, format_fix_still_invalid_markdown
from pipelex.suggested_fix import FixSafety, SuggestedFix
from pipelex.validation_error_types import PipeValidationErrorType


class TestFixRender:
    def test_already_valid_result_mentions_no_applied_fixes(self) -> None:
        result: dict[str, Any] = {
            "success": True,
            "is_valid": True,
            "bundle_path": "/workspace/bundle.mthds",
            "iterations": 0,
            "fixes_applied": [],
            "files_written": [],
            "remaining_errors": [],
        }

        rendered = format_fix_markdown(result)

        assert rendered.startswith("# Bundle already valid")
        assert "- **Bundle:** `/workspace/bundle.mthds`" in rendered
        assert "- **Iterations:** 0" in rendered
        assert "## Applied Fixes" not in rendered

    def test_fixed_result_lists_applied_fixes_and_written_files(self) -> None:
        result: dict[str, Any] = {
            "success": True,
            "is_valid": True,
            "bundle_path": "/workspace/entry.mthds",
            "iterations": 1,
            "fixes_applied": [
                {
                    "fix_code": "match-sequence-output",
                    "description": "Set output of pipe 'list_ideas' to 'Idea[]'",
                    "source": "/workspace/entry.mthds",
                    "ops": [],
                }
            ],
            "files_written": ["/workspace/entry.mthds"],
            "remaining_errors": [],
        }

        rendered = format_fix_markdown(result)

        assert rendered.startswith("# Fix applied - bundle is valid")
        assert "`match-sequence-output` - Set output of pipe 'list_ideas' to 'Idea[]'" in rendered
        assert "## Files Written" in rendered
        assert "- `/workspace/entry.mthds`" in rendered

    def test_multi_file_fix_names_non_entry_source(self) -> None:
        result: dict[str, Any] = {
            "success": True,
            "is_valid": True,
            "bundle_path": "/workspace/entry.mthds",
            "iterations": 1,
            "fixes_applied": [
                {
                    "fix_code": "strip-namespace",
                    "description": "Strip the same-domain prefix from pipe 'pkg.hello'",
                    "source": "/workspace/libs/sibling.mthds",
                    "ops": [],
                }
            ],
            "files_written": ["/workspace/libs/sibling.mthds"],
            "remaining_errors": [],
        }

        rendered = format_fix_markdown(result)

        assert "`strip-namespace` - Strip the same-domain prefix from pipe 'pkg.hello' (`/workspace/libs/sibling.mthds`)" in rendered

    def test_non_runnable_result_lists_pending_signatures(self) -> None:
        result: dict[str, Any] = {
            "success": True,
            "is_valid": True,
            "is_runnable": False,
            "bundle_path": "/workspace/entry.mthds",
            "iterations": 0,
            "fixes_applied": [],
            "files_written": [],
            "remaining_errors": [],
            "pending_signatures": ["signature_demo.summarize_doc"],
        }

        rendered = format_fix_markdown(result)

        assert rendered.startswith("# Bundle valid but not runnable")
        assert "## Pending Signatures" in rendered
        assert "- `signature_demo.summarize_doc`" in rendered

    def test_still_invalid_renders_applied_fixes_bail_and_remaining_as_prose(self) -> None:
        """The still-invalid markdown names the partial progress, the bail reason, and the remaining
        errors as prose items (with their 💡 lines) — not a JSON dump.
        """
        result = FixBundleResult(
            is_valid=False,
            iterations=2,
            fixes_applied=[
                SuggestedFix(
                    fix_code="match-sequence-output",
                    description="Set output of pipe 'a' to 'X[]'",
                    safety=FixSafety.SAFE,
                    source="/w/entry.mthds",
                    ops=[],
                )
            ],
            files_written=["/w/entry.mthds"],
            remaining_errors=[
                ValidationErrorItem(
                    category=ValidationErrorCategory.PIPE_VALIDATION,
                    error_type=PipeValidationErrorType.UNRESOLVED_CONCEPT,
                    pipe_code="b",
                    concept_code="Missing",
                    message="Concept 'Missing' is not defined.",
                    source="/w/entry.mthds",
                    suggested_fix=SuggestedFix(
                        fix_code="strip-namespace",
                        description="Strip the same-domain prefix from pipe 'b'",
                        safety=FixSafety.SAFE,
                        ops=[],
                    ),
                )
            ],
            bail_reason="Cross-file collision: two files declare pipe 'b'",
        )

        rendered = format_fix_still_invalid_markdown(result, bundle_path="/w/entry.mthds")

        assert rendered.startswith("# Fix incomplete - bundle still invalid")
        assert "## Applied Fixes" in rendered
        assert "- `match-sequence-output` - Set output of pipe 'a' to 'X[]'" in rendered
        assert "**Stopped:** Cross-file collision: two files declare pipe 'b'" in rendered
        # Remaining errors render as prose items, with the humanized title and the 💡 suggested-fix line.
        assert "1. **Unresolved Concept**" in rendered
        assert "   - Concept: `Missing`" in rendered
        assert "   - 💡 Suggested fix: Strip the same-domain prefix from pipe 'b'" in rendered
        # A remaining fixable item flips the tip toward "not applied", not "no safe fix".
        assert "still show a suggested fix that was not applied" in rendered

    def test_still_invalid_tip_says_manual_when_no_remaining_fix(self) -> None:
        """When no remaining error carries a suggested fix, the tip points at a manual edit."""
        result = FixBundleResult(
            is_valid=False,
            iterations=1,
            fixes_applied=[],
            files_written=[],
            remaining_errors=[
                ValidationErrorItem(
                    category=ValidationErrorCategory.PIPE_VALIDATION,
                    error_type=PipeValidationErrorType.UNRESOLVED_CONCEPT,
                    message="Concept 'Missing' is not defined.",
                )
            ],
        )

        rendered = format_fix_still_invalid_markdown(result, bundle_path="/w/entry.mthds")

        assert "have no deterministic safe fix" in rendered
        assert "## Applied Fixes" not in rendered
