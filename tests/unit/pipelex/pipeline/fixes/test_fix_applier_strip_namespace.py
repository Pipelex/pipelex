"""Golden format-preservation tests for the ``strip-namespace`` rename op.

``RENAME_TABLE_KEY`` on ``["pipe"]`` renames a same-domain over-qualified declaration key to its
bare form *in place* — via tomlkit's position-preserving ``Container._replace`` — so the pipe keeps
its position among siblings and its comments (a ``del`` + re-add would send it to the bottom). Paired
with a root ``SET_KEY`` that strips ``main_pipe``, the golden byte-comparison pins that surrounding
pipes, comments, and the qualified step reference (which still resolves) are untouched. Collision and
idempotence are guarded skips, never raises.
"""

from pathlib import Path

import tomlkit

from pipelex.pipeline.fixes.applier import FixOpOutcome, apply_fix_ops, serialize_and_format
from pipelex.suggested_fix import FixOp, FixOpKind

_DATA = Path("tests/data/fixes")


def _dumps(toml_doc: tomlkit.TOMLDocument) -> str:
    """One typed funnel over tomlkit's weakly-typed ``dumps`` (narrow ignore, not file-level)."""
    return tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]


def _rename_op(*, key: str, new_key: str) -> FixOp:
    return FixOp(kind=FixOpKind.RENAME_TABLE_KEY, table_path=["pipe"], key=key, new_key=new_key)


def _strip_main_pipe_op(*, value: str) -> FixOp:
    return FixOp(kind=FixOpKind.SET_KEY, table_path=[], key="main_pipe", value=value)


_STRIP_OPS = [
    _rename_op(key="namespacefix.hello", new_key="hello"),
    _strip_main_pipe_op(value="run_seq"),
]

_COLLISION_MTHDS = """domain = "coll"
main_pipe = "hello"

[pipe.hello]
type = "PipeLLM"
description = "Bare hello."
output = "Text"
prompt = "Bare"

[pipe."coll.hello"]
type = "PipeLLM"
description = "Dotted hello."
output = "Text"
prompt = "Dotted"
"""

# ``[pipe.*]`` sections interleaved with a ``[concept.*]`` section (a legal, common layout:
# concepts declared next to the pipes that use them) — tomlkit resolves ``doc["pipe"]`` to an
# ``OutOfOrderTableProxy`` instead of a ``Table``.
_INTERLEAVED_MTHDS = """domain = "inter"

[pipe."inter.hello"]
type = "PipeLLM"
description = "Dotted hello."
output = "Text"
prompt = "Dotted"

[concept.Greeting]
description = "A greeting."

[pipe.other]
type = "PipeLLM"
description = "Other."
output = "Text"
prompt = "Other"
"""

# The whole ``pipe`` section as one inline table — tomlkit resolves ``doc["pipe"]`` to an
# ``InlineTable`` instead of a ``Table``.
_INLINE_MTHDS = """domain = "inl"
pipe = { "inl.hello" = { type = "PipeLLM", description = "Dotted.", output = "Text", prompt = "Dotted" } }
"""


class TestFixApplierStripNamespace:
    def test_strip_matches_golden_bytes(self) -> None:
        """Renaming the dotted declaration + stripping main_pipe, then formatting, yields the golden."""
        toml_doc = tomlkit.loads((_DATA / "strip_namespace_rename.mthds").read_text(encoding="utf-8"))
        applications = apply_fix_ops(toml_doc, ops=_STRIP_OPS)
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED, FixOpOutcome.APPLIED]
        golden = (_DATA / "strip_namespace_rename.golden.mthds").read_text(encoding="utf-8")
        assert serialize_and_format(toml_doc) == golden

    def test_rename_preserves_position_and_comments(self) -> None:
        """The renamed pipe stays between its siblings, keeping its leading and trailing comments."""
        toml_doc = tomlkit.loads((_DATA / "strip_namespace_rename.mthds").read_text(encoding="utf-8"))
        apply_fix_ops(toml_doc, ops=_STRIP_OPS)
        dumped = _dumps(toml_doc)
        assert '[pipe."namespacefix.hello"]' not in dumped
        assert "[pipe.hello]" in dumped
        # Position: renamed pipe is still between first_pipe and run_seq.
        assert dumped.index("[pipe.first_pipe]") < dumped.index("[pipe.hello]") < dumped.index("[pipe.run_seq]")
        # Comments survive (leading standalone + trailing inline).
        assert "over-qualified with its own domain prefix" in dumped
        assert "trailing comment stays on this line" in dumped
        # The qualified step reference is left untouched (it still resolves to the bare pipe).
        assert 'pipe = "namespacefix.hello"' in dumped

    def test_apply_twice_is_idempotent(self) -> None:
        """Re-applying finds the dotted key already renamed / main_pipe already stripped — bytes hold."""
        toml_doc = tomlkit.loads((_DATA / "strip_namespace_rename.mthds").read_text(encoding="utf-8"))
        apply_fix_ops(toml_doc, ops=_STRIP_OPS)
        once = serialize_and_format(toml_doc)
        second = apply_fix_ops(toml_doc, ops=_STRIP_OPS)
        assert [application.outcome for application in second] == [FixOpOutcome.SKIPPED, FixOpOutcome.APPLIED]
        assert serialize_and_format(toml_doc) == once

    def test_rename_skips_on_collision(self) -> None:
        """Renaming to a key already declared separately is skipped, not applied (no clobber)."""
        toml_doc = tomlkit.loads(_COLLISION_MTHDS)
        applications = apply_fix_ops(toml_doc, ops=[_rename_op(key="coll.hello", new_key="hello")])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]
        dumped = _dumps(toml_doc)
        # Both declarations survive untouched — nothing was clobbered.
        assert '[pipe."coll.hello"]' in dumped
        assert "[pipe.hello]" in dumped

    def test_rename_skips_when_key_absent(self) -> None:
        """A rename whose source key is not present is a guarded skip (e.g. a stale op)."""
        toml_doc = tomlkit.loads(_COLLISION_MTHDS)
        applications = apply_fix_ops(toml_doc, ops=[_rename_op(key="coll.ghost", new_key="ghost")])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]

    def test_rename_applies_on_interleaved_pipe_sections(self) -> None:
        """Interleaved ``[pipe.*]``/``[concept.*]`` sections (an ``OutOfOrderTableProxy``) rename in place."""
        toml_doc = tomlkit.loads(_INTERLEAVED_MTHDS)
        applications = apply_fix_ops(toml_doc, ops=[_rename_op(key="inter.hello", new_key="hello")])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        dumped = _dumps(toml_doc)
        assert '[pipe."inter.hello"]' not in dumped
        assert "[pipe.hello]" in dumped
        # Position: the renamed pipe stays before the concept section, which stays before [pipe.other].
        assert dumped.index("[pipe.hello]") < dumped.index("[concept.Greeting]") < dumped.index("[pipe.other]")
        # The whole document still formats cleanly (no malformed TOML out of the proxy rename).
        assert "[pipe.hello]" in serialize_and_format(toml_doc)

    def test_rename_skips_on_collision_across_interleaved_sections(self) -> None:
        """A collision with a bare key living in a *different* ``[pipe.*]`` section is still a skip."""
        interleaved_collision = _INTERLEAVED_MTHDS.replace("[pipe.other]", "[pipe.hello]")
        toml_doc = tomlkit.loads(interleaved_collision)
        applications = apply_fix_ops(toml_doc, ops=[_rename_op(key="inter.hello", new_key="hello")])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]
        dumped = _dumps(toml_doc)
        assert '[pipe."inter.hello"]' in dumped

    def test_rename_applies_on_inline_pipe_table(self) -> None:
        """An inline ``pipe = {...}`` section (an ``InlineTable``) renames in place."""
        toml_doc = tomlkit.loads(_INLINE_MTHDS)
        applications = apply_fix_ops(toml_doc, ops=[_rename_op(key="inl.hello", new_key="hello")])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        dumped = _dumps(toml_doc)
        assert '"inl.hello"' not in dumped
        assert "hello" in dumped
        assert "hello" in serialize_and_format(toml_doc)
