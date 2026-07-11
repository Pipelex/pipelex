"""Golden format-preservation tests for the sync-controller-inputs op shapes.

The multi-op diff (set_key updates + adds, delete_key removals) mutates the ``inputs``
table in place, in both its inline and block authoring forms; the no-table case creates
the whole mapping as one inline table (kept attached to its pipe, not a detached block).
Goldens are the MTHDS-formatter canonical bytes: the applier mutates, ``serialize_and_format``
reflows inline-table spacing via ``pipelex_tools.format_mthds`` (the same engine ``plxt``
runs on save), so the fix output is stable under the formatter.
"""

from pathlib import Path

import tomlkit

from pipelex.pipeline.fixes.applier import FixOpOutcome, apply_fix_ops, serialize_and_format
from pipelex.suggested_fix import FixOp, FixOpKind

_FIXES_DIR = Path("tests/data/fixes")
_INPUTS_TABLE_PATH = ["pipe", "make_summary", "inputs"]


def _dumps(toml_doc: tomlkit.TOMLDocument) -> str:
    """One typed funnel over tomlkit's weakly-typed ``dumps`` (narrow ignore, not file-level)."""
    return tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]


def _load(name: str) -> tomlkit.TOMLDocument:
    return tomlkit.loads((_FIXES_DIR / f"{name}.mthds").read_text(encoding="utf-8"))


def _golden(name: str) -> str:
    return (_FIXES_DIR / f"{name}.golden.mthds").read_text(encoding="utf-8")


_INLINE_OPS = [
    FixOp(kind=FixOpKind.SET_KEY, table_path=_INPUTS_TABLE_PATH, key="text", value="Text"),
    FixOp(kind=FixOpKind.SET_KEY, table_path=_INPUTS_TABLE_PATH, key="style", value="Text"),
    FixOp(kind=FixOpKind.DELETE_KEY, table_path=_INPUTS_TABLE_PATH, key="note"),
]

_BLOCK_OPS = [
    FixOp(kind=FixOpKind.SET_KEY, table_path=_INPUTS_TABLE_PATH, key="text", value="Text"),
    FixOp(kind=FixOpKind.DELETE_KEY, table_path=_INPUTS_TABLE_PATH, key="note"),
]

_MISSING_TABLE_OPS = [
    FixOp(kind=FixOpKind.ENSURE_TABLE, table_path=_INPUTS_TABLE_PATH),
    FixOp(kind=FixOpKind.SET_KEY, table_path=_INPUTS_TABLE_PATH, key="text", value="Text"),
]


class TestFixApplierInputsSync:
    def test_inline_inputs_diff_matches_golden_bytes(self) -> None:
        """Add + update + delete on an inline inputs table, then format, yields the golden bytes."""
        toml_doc = _load("controller_inputs_inline")
        applications = apply_fix_ops(toml_doc=toml_doc, ops=_INLINE_OPS)
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED] * 3
        assert serialize_and_format(toml_doc) == _golden("controller_inputs_inline")

    def test_block_inputs_diff_matches_golden_bytes(self) -> None:
        """Update + delete on a block [pipe.x.inputs] table preserves surrounding comments."""
        toml_doc = _load("controller_inputs_block")
        applications = apply_fix_ops(toml_doc=toml_doc, ops=_BLOCK_OPS)
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED] * 2
        assert serialize_and_format(toml_doc) == _golden("controller_inputs_block")

    def test_missing_inputs_table_created_as_inline_table(self) -> None:
        """With no inputs declared, one set_key writes the whole mapping as an inline table."""
        toml_doc = _load("controller_inputs_missing_table")
        applications = apply_fix_ops(toml_doc=toml_doc, ops=_MISSING_TABLE_OPS)
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED] * 2
        assert serialize_and_format(toml_doc) == _golden("controller_inputs_missing_table")

    def test_explicit_empty_block_keeps_its_comment(self) -> None:
        """Ensuring an existing empty block mutates it in place instead of replacing it."""
        source = """[pipe.make_summary]
type = "PipeSequence"
output = "Text"

[pipe.make_summary.inputs]
# keep this author note
"""
        toml_doc = tomlkit.loads(source)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=_MISSING_TABLE_OPS)

        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED, FixOpOutcome.APPLIED]
        formatted = serialize_and_format(toml_doc)
        assert "# keep this author note" in formatted
        assert 'text = "Text"' in formatted

    def test_inline_diff_applied_twice_is_idempotent(self) -> None:
        """Re-applying the same diff yields the same bytes."""
        toml_doc = _load("controller_inputs_inline")
        apply_fix_ops(toml_doc=toml_doc, ops=_INLINE_OPS)
        once = _dumps(toml_doc)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=_INLINE_OPS)
        set_outcomes = [application.outcome for application in applications[:2]]
        delete_outcome = applications[2].outcome
        assert set_outcomes == [FixOpOutcome.APPLIED] * 2
        assert delete_outcome == FixOpOutcome.SKIPPED
        assert _dumps(toml_doc) == once

    def test_missing_table_creation_applied_twice_is_idempotent(self) -> None:
        """Re-applying the whole-table set_key yields the same bytes."""
        toml_doc = _load("controller_inputs_missing_table")
        apply_fix_ops(toml_doc=toml_doc, ops=_MISSING_TABLE_OPS)
        once = _dumps(toml_doc)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=_MISSING_TABLE_OPS)
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED, FixOpOutcome.APPLIED]
        assert _dumps(toml_doc) == once

    def test_dotted_input_key_survives_format(self) -> None:
        """A quoted dotted input key (`"cv.name"`, a supported sub-attribute name) stays a flat
        quoted entry through the format pass, not split into a nested table. Deleting an unrelated
        sibling (with a bare ``cv`` root also present) must neither crash nor corrupt the file.
        """
        source = '[pipe.make_summary]\ntype = "PipeSequence"\ninputs = { "cv.name" = "Text", cv = "Curriculum", note = "Text" }\n'
        toml_doc = tomlkit.loads(source)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[FixOp(kind=FixOpKind.DELETE_KEY, table_path=_INPUTS_TABLE_PATH, key="note")])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        formatted = serialize_and_format(toml_doc)
        assert '"cv.name" = "Text"' in formatted
        assert "note" not in formatted
        # The dotted key stays a flat string entry, not a nested `cv = { name = ... }` table.
        reloaded = tomlkit.loads(formatted).unwrap()
        assert reloaded["pipe"]["make_summary"]["inputs"] == {"cv.name": "Text", "cv": "Curriculum"}
