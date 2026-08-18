"""Golden format-preservation tests for the ``strip-native-concept-redecl`` delete op.

One ``DELETE_KEY`` on ``["concept"]`` strips a redeclared native concept across every authoring
form — a ``[concept.X]`` table (with a ``[concept.X.structure]`` sub-table), an ``X = "…"`` string
shorthand under ``[concept]``, and a dotted ``concept.X`` — because tomlkit represents all three as
a ``concept`` table keyed by the code. The goldens are the canonical apply → format output; the
byte-comparison pins that surviving concepts, comments, and pipes are untouched and that deleting a
table also removes its nested structure sub-table.
"""

from pathlib import Path

import pytest
import tomlkit

from pipelex.pipeline.fixes.applier import FixOpOutcome, apply_fix_ops, serialize_and_format
from pipelex.suggested_fix import DeleteKeyOp, FixOp

_DATA = Path("tests/data/fixes")


def _dumps(toml_doc: tomlkit.TOMLDocument) -> str:
    """One typed funnel over tomlkit's weakly-typed ``dumps`` (narrow ignore, not file-level)."""
    return tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]


def _delete_concept_op(*, key: str) -> FixOp:
    return DeleteKeyOp(table_path=["concept"], key=key)


class TestFixApplierNativeConcept:
    @pytest.mark.parametrize(
        ("fixture_stem", "concept_code"),
        [
            ("native_redecl_table", "Text"),
            ("native_redecl_inline", "Text"),
            ("native_redecl_dotted", "Number"),
        ],
    )
    def test_strip_matches_golden_bytes(self, fixture_stem: str, concept_code: str) -> None:
        """Deleting the redeclared concept then formatting yields the golden bytes, every form."""
        toml_doc = tomlkit.loads((_DATA / f"{fixture_stem}.mthds").read_text(encoding="utf-8"))
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[_delete_concept_op(key=concept_code)])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        golden = (_DATA / f"{fixture_stem}.golden.mthds").read_text(encoding="utf-8")
        assert serialize_and_format(toml_doc) == golden

    def test_delete_removes_table_and_its_structure_subtable(self) -> None:
        """Deleting a ``[concept.Text]`` table also drops its ``[concept.Text.structure]`` sub-table."""
        toml_doc = tomlkit.loads((_DATA / "native_redecl_table.mthds").read_text(encoding="utf-8"))
        apply_fix_ops(toml_doc=toml_doc, ops=[_delete_concept_op(key="Text")])
        dumped = _dumps(toml_doc)
        assert "[concept.Text]" not in dumped
        assert "structure" not in dumped
        # Sibling concept and its comment survive.
        assert "[concept.Report]" in dumped
        assert "must survive the fix untouched" in dumped

    def test_apply_twice_is_idempotent(self) -> None:
        """Re-applying the delete finds the key already gone — the bytes do not change."""
        toml_doc = tomlkit.loads((_DATA / "native_redecl_inline.mthds").read_text(encoding="utf-8"))
        apply_fix_ops(toml_doc=toml_doc, ops=[_delete_concept_op(key="Text")])
        once = _dumps(toml_doc)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[_delete_concept_op(key="Text")])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]
        assert _dumps(toml_doc) == once

    def test_leading_comment_on_deleted_table_goes_with_it(self) -> None:
        """A standalone comment sitting directly above a deleted ``[concept.X]`` table is dropped
        with the table, rather than dangling onto the next element. tomlkit stores such a comment
        as trailing trivia of the *previous* table, so a plain delete used to leave it there, now
        annotating whatever followed; the applier reads it as introducing the deleted table and
        removes it, and the successor keeps its own blank line.
        """
        source = (
            "[concept.Report]\n"
            'description = "A report."\n'
            "\n"
            "# describes the redeclared concept below\n"
            "[concept.Text]\n"
            'description = "Redeclared native Text."\n'
            "\n"
            "[pipe.make_report]\n"
            'type = "PipeLLM"\n'
        )
        toml_doc = tomlkit.loads(source)
        apply_fix_ops(toml_doc=toml_doc, ops=[_delete_concept_op(key="Text")])
        assert _dumps(toml_doc) == '[concept.Report]\ndescription = "A report."\n\n[pipe.make_report]\ntype = "PipeLLM"\n'

    def test_delete_missing_concept_is_skipped(self) -> None:
        """Stripping a concept absent from the document is reported as skipped, not raised."""
        toml_doc = tomlkit.loads((_DATA / "native_redecl_inline.mthds").read_text(encoding="utf-8"))
        source_bytes = _dumps(toml_doc)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[_delete_concept_op(key="Number")])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]
        assert _dumps(toml_doc) == source_bytes
