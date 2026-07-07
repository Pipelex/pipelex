"""Unit tests for the tomlkit fix applier — golden format-preservation tests.

The applier mutates a tomlkit DOM in place (never rebuilds containers), so the comments,
ordering, and table style of untouched content survive by construction; ``serialize_and_format``
then hands the result to the MTHDS formatter for the one canonical style. The golden files are
that canonical output, and the byte-comparison is the regression net for the whole apply → format
pipeline; idempotence and the guarded skip (a missing target path is reported, not raised) are
pinned alongside on the raw DOM.
"""

from pathlib import Path

import tomlkit

from pipelex.pipeline.fixes.applier import FixOpOutcome, apply_fix_ops, serialize_and_format
from pipelex.suggested_fix import FixOp, FixOpKind

_FIXTURE_PATH = Path("tests/data/fixes/sequence_wrong_output.mthds")
_GOLDEN_PATH = Path("tests/data/fixes/sequence_wrong_output.golden.mthds")


def _dumps(toml_doc: tomlkit.TOMLDocument) -> str:
    """One typed funnel over tomlkit's weakly-typed ``dumps`` (narrow ignore, not file-level)."""
    return tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]


def _set_output_op(*, pipe_code: str = "list_ideas", value: str = "Idea[]") -> FixOp:
    return FixOp(kind=FixOpKind.SET_KEY, table_path=["pipe", pipe_code], key="output", value=value)


class TestFixApplier:
    def test_set_key_matches_golden_bytes(self) -> None:
        """Applying the set_key op then formatting yields output byte-equal to the golden file."""
        toml_doc = tomlkit.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        applications = apply_fix_ops(toml_doc, ops=[_set_output_op()])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        assert serialize_and_format(toml_doc) == _GOLDEN_PATH.read_text(encoding="utf-8")

    def test_apply_twice_is_idempotent(self) -> None:
        """Applying the same op twice yields the same bytes as applying it once."""
        toml_doc = tomlkit.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        apply_fix_ops(toml_doc, ops=[_set_output_op()])
        once = _dumps(toml_doc)
        applications = apply_fix_ops(toml_doc, ops=[_set_output_op()])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        assert _dumps(toml_doc) == once

    def test_missing_table_path_is_skipped_not_raised(self) -> None:
        """An op targeting a table absent from the DOM (e.g. a synthetic pipe) is skipped and reported."""
        toml_doc = tomlkit.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        source_bytes = _dumps(toml_doc)
        applications = apply_fix_ops(toml_doc, ops=[_set_output_op(pipe_code="synthetic_pipe_not_in_file")])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]
        assert applications[0].detail is not None
        assert "pipe" in applications[0].detail
        assert _dumps(toml_doc) == source_bytes

    def test_delete_key_removes_key_preserving_rest(self) -> None:
        """delete_key removes exactly the addressed key; everything else survives byte-for-byte."""
        toml_doc = tomlkit.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        delete_op = FixOp(kind=FixOpKind.DELETE_KEY, table_path=["pipe", "gen_ideas"], key="prompt")
        applications = apply_fix_ops(toml_doc, ops=[delete_op])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        dumped = _dumps(toml_doc)
        assert "Generate ideas about $topic" not in dumped
        assert 'inputs = { topic = "Text" } # inline table style' in dumped
        assert "# The sequence below declares the wrong output on purpose." in dumped

    def test_delete_key_missing_is_skipped(self) -> None:
        """delete_key on an absent key is skipped and reported, not raised."""
        toml_doc = tomlkit.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        delete_op = FixOp(kind=FixOpKind.DELETE_KEY, table_path=["pipe", "gen_ideas"], key="not_a_key")
        applications = apply_fix_ops(toml_doc, ops=[delete_op])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]

    def test_delete_table_on_scalar_leaf_is_skipped(self) -> None:
        """delete_table whose final segment names a scalar (a drifted target) is skipped, not deleted."""
        toml_doc = tomlkit.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        source_bytes = _dumps(toml_doc)
        delete_op = FixOp(kind=FixOpKind.DELETE_TABLE, table_path=["pipe", "gen_ideas", "prompt"])
        applications = apply_fix_ops(toml_doc, ops=[delete_op])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]
        assert applications[0].detail is not None
        assert _dumps(toml_doc) == source_bytes

    def test_delete_table_removes_whole_table(self) -> None:
        """delete_table removes the addressed table and its keys; sibling tables survive."""
        toml_doc = tomlkit.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        delete_op = FixOp(kind=FixOpKind.DELETE_TABLE, table_path=["pipe", "gen_ideas"])
        applications = apply_fix_ops(toml_doc, ops=[delete_op])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        dumped = _dumps(toml_doc)
        assert "[pipe.gen_ideas]" not in dumped
        assert "[pipe.list_ideas]" in dumped

    def test_set_output_on_whole_pipe_inline_table_survives_format(self) -> None:
        """A pipe authored as a single-line inline table is a valid, rarer form. Setting its
        output mutates that nested inline table in place; the format pass must reflow it without
        crashing on the nested inputs table nor corrupting it into multi-line block form.
        """
        source = '[pipe]\nlist_ideas = { type = "PipeSequence", inputs = { topic = "Text" }, output = "Idea" }\n'
        toml_doc = tomlkit.loads(source)
        applications = apply_fix_ops(toml_doc, ops=[_set_output_op()])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        reloaded = tomlkit.loads(serialize_and_format(toml_doc)).unwrap()["pipe"]["list_ideas"]
        assert reloaded["output"] == "Idea[]"
        assert reloaded["inputs"] == {"topic": "Text"}
