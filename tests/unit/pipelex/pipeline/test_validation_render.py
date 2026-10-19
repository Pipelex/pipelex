"""Unit tests for the validate markdown renderers in `pipelex.pipeline.validation_render`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mthds.protocol.problem.models import FixOp, ProblemItem, SetKeyOp
from mthds.protocol.problem.models import SuggestedFix as WireSuggestedFix
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.errors.error_codes import error_code_spec
from pipelex.pipeline.validation_errors import problem_item_of, validation_item_code
from pipelex.pipeline.validation_render import (
    build_fix_command,
    format_validate_markdown,
    render_invalid_verdict_markdown,
    suggested_fix_label,
)
from pipelex.suggested_fix import FixSafety, SuggestedFix
from pipelex.suggested_fix import SetKeyOp as PipelexSetKeyOp
from pipelex.validation_error_types import PipeValidationErrorType


class TestValidationRender:
    def test_renders_pending_signatures_section_with_not_runnable_verdict(self):
        """A populated pending_signatures list renders the verbatim section heading, an explicit
        "NOT yet runnable" verdict, and each ref as a bullet.
        """
        result: dict[str, Any] = {
            "success": True,
            "bundle_path": "/fake/method.mthds",
            "validated_pipes": [{"pipe_ref": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": ["research.find_key_findings", "research.rank_findings"],
            "is_runnable": False,
        }

        markdown = format_validate_markdown(result)

        assert markdown.startswith("# Validation passed")
        # Heading kept verbatim — a downstream plugin reads this exact string.
        assert "## Pending signatures (2)" in markdown
        # Explicit negative verdict, with the count, immediately above the list.
        assert "⚠️ This method is NOT yet runnable" in markdown
        assert "2 pipes are still `PipeSignature` placeholders" in markdown
        assert "- `research.find_key_findings`" in markdown
        assert "- `research.rank_findings`" in markdown
        # The verdict must precede the verbatim heading — consumers expect the note directly above it.
        assert markdown.index("⚠️ This method is NOT yet runnable") < markdown.index("## Pending signatures")

    def test_renders_single_pending_signature_with_singular_grammar(self):
        """A single pending signature renders grammatically — "1 pipe is still a `PipeSignature`
        placeholder" — with no "(s)", singular verb, and the article present.
        """
        result: dict[str, Any] = {
            "success": True,
            "bundle_path": "/fake/method.mthds",
            "validated_pipes": [{"pipe_ref": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": ["research.find_key_findings"],
            "is_runnable": False,
        }

        markdown = format_validate_markdown(result)

        # The count line also pluralizes: a single validated pipe is "1 pipe", not "1 pipe(s)".
        assert "Validated 1 pipe:" in markdown
        assert "1 pipe is still a `PipeSignature` placeholder" in markdown
        assert "## Pending signatures (1)" in markdown
        # No "(s)" shorthand anywhere in the rendered markdown.
        assert "(s)" not in markdown

    def test_renders_runnable_verdict_for_complete_bundle(self):
        """A present-but-empty pending_signatures (complete bundle) renders an explicit runnable
        verdict and no "Pending signatures" section.
        """
        result: dict[str, Any] = {
            "success": True,
            "bundle_path": "/fake/method.mthds",
            "validated_pipes": [{"pipe_ref": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": [],
            "is_runnable": True,
        }

        markdown = format_validate_markdown(result)

        assert markdown.startswith("# Validation passed")
        assert "✅ All pipes are concretely implemented" in markdown
        assert "this method is runnable." in markdown
        assert "Pending signatures" not in markdown

    def test_says_plainly_why_a_method_folder_drew_no_graph(self):
        """A folder judged whole with no single pipe to start at still passes; the markdown says why no graph was drawn."""
        reason = "No graph was drawn, since a graph is drawn from one pipe: the folder declares several main pipes."
        result: dict[str, Any] = {
            "success": True,
            "bundle_path": "/fake/method",
            "validated_pipes": [{"pipe_ref": "first.one", "status": "SUCCESS"}, {"pipe_ref": "second.two", "status": "SUCCESS"}],
            "total_pipes": 2,
            "graph_unavailable": reason,
        }

        markdown = format_validate_markdown(result)

        assert markdown.startswith("# Validation passed")
        assert markdown.endswith(f"## Graph\n\n{reason}")

    def test_omits_runnability_verdict_when_key_absent(self):
        """The `validate all` / `validate pipe` shape omits the `pending_signatures` key entirely —
        so no runnability verdict (positive or negative) leaks onto those non-bundle surfaces.
        """
        without_key: dict[str, Any] = {
            "success": True,
            "validated_pipes": [{"pipe_ref": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
        }

        markdown = format_validate_markdown(without_key)

        assert markdown.startswith("# Validation passed")
        assert "Pending signatures" not in markdown
        assert "runnable" not in markdown
        assert "✅" not in markdown
        assert "⚠️" not in markdown

    def test_renders_an_invalid_verdict_from_its_problem_items(self):
        """The invalid-arm renderer presents the verdict's problem items, the `errors` a host answers: each numbered under
        its code's title with its code, where it is, its sentence and its suggested fix, and never a validation item's own
        message, which the reader's view of the items does not carry.
        """
        validation_item = ValidationErrorItem(
            category=ValidationErrorCategory.PIPE_VALIDATION,
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
            message="The operator's own wording of the fault.",
            pipe_code="summarize",
            field_name="output",
            source="/fake/method.mthds",
            line=7,
            suggested_fix=SuggestedFix(
                fix_code="match-sequence-output",
                description="Set output of pipe 'summarize' to 'Contract'",
                safety=FixSafety.SAFE,
                ops=[PipelexSetKeyOp(table_path=["pipe", "summarize"], key="output", value="Contract")],
            ),
        )
        code = validation_item_code(item=validation_item, residual_code=CoreCode.METHOD_SCHEMA_VIOLATION)
        item = problem_item_of(item=validation_item, code=code)

        markdown = render_invalid_verdict_markdown(items=[item], message="MTHDS validation found errors")

        assert markdown.startswith("# Validation failed")
        assert f"1. **{error_code_spec(code).title}** (`{code}`)" in markdown
        assert "   - Pipe: `summarize`" in markdown
        assert "   - Field: `output`" in markdown
        assert "   - File: `/fake/method.mthds:7`" in markdown
        assert f"   - {item.detail}" in markdown
        assert "   - 💡 Suggested fix: Set output of pipe 'summarize' to 'Contract'" in markdown
        assert "operator's own wording" not in markdown

    def test_an_invalid_verdict_with_no_item_shows_its_sentence(self):
        markdown = render_invalid_verdict_markdown(items=[], message="MTHDS validation found errors")

        assert markdown == "# Validation failed\n\nMTHDS validation found errors"

    def test_suggested_fix_label_says_when_a_fix_is_unsafe(self):
        """A safe fix is a plain `Suggested fix`; an unsafe one says it is unsafe and needs confirming."""
        safe_fix = SuggestedFix(fix_code="match-sequence-output", description="d", safety=FixSafety.SAFE, ops=[])
        unsafe_fix = SuggestedFix(fix_code="rename-model", description="d", safety=FixSafety.UNSAFE, ops=[])

        assert suggested_fix_label(fix=safe_fix) == "Suggested fix"
        assert suggested_fix_label(fix=unsafe_fix) == "Suggested fix (unsafe, confirm before applying)"

    def test_invalid_verdict_markdown_marks_an_unsafe_fix(self):
        """The hosted `rendered_markdown` path labels an unsafe wire fix, next to a safe one left plain."""
        ops: list[FixOp] = [SetKeyOp(kind="set_key", table_path=["pipe", "write"], key="model", value="gpt-5")]
        items = [
            ProblemItem(
                code="method.schema_violation",
                detail="Output mismatch.",
                suggested_fix=WireSuggestedFix(
                    fix_code="match-sequence-output", description="Set output of pipe 'summarize' to 'Contract'", safety="safe", ops=ops
                ),
            ),
            ProblemItem(
                code="model.unknown",
                detail="The model is not in the deck.",
                suggested_fix=WireSuggestedFix(
                    fix_code="rename-model",
                    description="Replace model 'gpt-5.1' of pipe 'write' with 'gpt-5', its one close match in the model deck",
                    safety="unsafe",
                    ops=ops,
                ),
            ),
        ]

        markdown = render_invalid_verdict_markdown(items=items, message="MTHDS validation found errors")

        assert "   - 💡 Suggested fix: Set output of pipe 'summarize' to 'Contract'" in markdown
        assert "   - 💡 Suggested fix (unsafe, confirm before applying): Replace model 'gpt-5.1' of pipe 'write' with 'gpt-5'" in markdown

    def test_build_fix_command_echoes_library_dirs_and_signatures(self):
        """`build_fix_command` shell-joins the executable, path, each `-L` dir, and `--allow-signatures`."""
        command = build_fix_command(
            executable="pipelex-agent",
            bundle_path=Path("my bundle.mthds"),
            library_dirs=[Path("libs/a"), Path("libs/b")],
            allow_signatures=True,
        )

        # shlex.join quotes the space-bearing path so it stays one argument when pasted.
        assert command == "pipelex-agent fix bundle 'my bundle.mthds' -L libs/a -L libs/b --allow-signatures"

    def test_build_fix_command_minimal_has_no_flags(self):
        """With no library dirs and signatures disabled, only the bare `fix bundle <path>` is emitted."""
        command = build_fix_command(executable="pipelex", bundle_path=Path("bundle.mthds"))

        assert command == "pipelex fix bundle bundle.mthds"
