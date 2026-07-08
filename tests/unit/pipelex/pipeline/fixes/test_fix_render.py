"""Unit tests for agent-facing fix result markdown."""

from typing import Any

from pipelex.pipeline.fixes.fix_render import format_fix_markdown


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
