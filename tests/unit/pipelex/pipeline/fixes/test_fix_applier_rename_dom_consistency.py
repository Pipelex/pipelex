"""Characterization of what a rename leaves behind in the tomlkit DOM.

`_rename_key_in_place` renames through `Container._replace`, tomlkit's own position-preserving
primitive — the only one there is, and the reason a renamed key keeps its place among its siblings
instead of being appended at the bottom of its parent. What it does **not** do, for a value that
is not a `Table`, is update the node's raw `dict` storage: the key is deleted from the dict and the
new one is only ever written back inside the table branch of `_replace_at`.

Everything tomlkit renders or looks up still works — `dumps`, `in`, `[]`, `.get()` all read the
authoritative body — so a single rename followed by serialization is correct, which is why the
`.mthds` fix path never met this: the keys it renames are `[pipe.*]` tables, and tables take the
branch that keeps the dict in step.

A migration is the case that meets it, because always-replay runs many operations over one
document. The consequence is pinned below: addressing a renamed non-table key again in the same
DOM raises `KeyError` from inside the library. `pipelex.migration.engine` works around it by
re-reading the document between operations that applied, and this module is the tripwire — **if
these tests go red after a tomlkit bump, the workaround can be reconsidered**, and the engine's
docstring says so.
"""

from typing import Any, cast

import pytest
import tomlkit
from tomlkit import TOMLDocument

from pipelex.pipeline.fixes.applier import FixOpOutcome, apply_fix_ops
from pipelex.suggested_fix import DeleteKeyOp, RenameTableKeyOp

FLAT = """\
[reporting]
output_config = { directory = "out" }
retention = 30
"""

OUT_OF_ORDER = """\
[pipelex]
alpha = 1

[other]
z = 0

[pipelex.sub]
b = 2
"""


def _raw_dict_keys(*, node: object) -> set[str]:
    """The keys of a tomlkit node's *raw* dict storage, bypassing its overriding accessors.

    Every public accessor reads the authoritative body instead, which is precisely why the
    staleness this pins is invisible until something calls `dict.__delitem__`.
    """
    raw_mapping = cast("dict[str, Any]", node)
    return {str(key) for key in cast("list[Any]", list(dict.keys(raw_mapping)))}  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]


def _dumped(*, toml_doc: TOMLDocument) -> str:
    dumped: str = tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]
    return dumped


TABLE_VALUED = """\
[pipe]
[pipe.old_name]
type = "PipeLLM"
"""


class TestRenameDomConsistency:
    def test_a_renamed_scalar_serializes_correctly_and_reads_back_through_every_accessor(self) -> None:
        toml_doc = tomlkit.loads(FLAT)

        applications = apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=["reporting"], key="retention", new_key="keep_days")])

        assert applications[0].outcome is FixOpOutcome.APPLIED
        assert "keep_days = 30" in _dumped(toml_doc=toml_doc)
        reporting = cast("dict[str, Any]", toml_doc["reporting"])
        assert "keep_days" in reporting
        assert reporting["keep_days"] == 30

    def test_the_raw_dict_storage_is_left_stale_by_the_rename(self) -> None:
        """The measured defect itself, stated in one assertion so a tomlkit fix is visible."""
        toml_doc = tomlkit.loads(FLAT)
        apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=["reporting"], key="retention", new_key="keep_days")])

        raw_keys = _raw_dict_keys(node=toml_doc["reporting"])
        assert "retention" in raw_keys
        assert "keep_days" not in raw_keys

    @pytest.mark.parametrize(
        ("text", "table_path", "key", "new_key"),
        [
            (FLAT, ["reporting"], "retention", "keep_days"),
            (OUT_OF_ORDER, ["pipelex"], "alpha", "beta"),
        ],
    )
    def test_addressing_a_renamed_key_again_in_the_same_dom_raises_from_inside_tomlkit(
        self,
        text: str,
        table_path: list[str],
        key: str,
        new_key: str,
    ) -> None:
        """Both parent shapes are affected: a plain table and an out-of-order table proxy.

        This is what the migration engine's re-read exists to avoid. It is deliberately asserted
        as a raise rather than worked around here: the applier's guarded-skip contract is about
        targets that do not resolve, and this target does resolve — the library's own bookkeeping
        is what disagrees with itself.
        """
        toml_doc = tomlkit.loads(text)
        apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=table_path, key=key, new_key=new_key)])

        with pytest.raises(KeyError):
            apply_fix_ops(toml_doc=toml_doc, ops=[DeleteKeyOp(table_path=table_path, key=new_key)])

    def test_renaming_a_table_valued_key_keeps_the_dom_consistent(self) -> None:
        """The branch tomlkit does maintain — and the reason the `.mthds` fix path never met this."""
        toml_doc = tomlkit.loads(TABLE_VALUED)

        apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=["pipe"], key="old_name", new_key="new_name")])
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[DeleteKeyOp(table_path=["pipe", "new_name"], key="type")])

        assert applications[0].outcome is FixOpOutcome.APPLIED
        assert "old_name" not in _dumped(toml_doc=toml_doc)

    def test_re_reading_between_operations_is_what_makes_the_sequence_work(self) -> None:
        """The workaround, shown at its smallest: serialize, parse, continue."""
        toml_doc = tomlkit.loads(FLAT)
        apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=["reporting"], key="retention", new_key="keep_days")])

        re_read = tomlkit.loads(_dumped(toml_doc=toml_doc))
        applications = apply_fix_ops(toml_doc=re_read, ops=[DeleteKeyOp(table_path=["reporting"], key="keep_days")])

        assert applications[0].outcome is FixOpOutcome.APPLIED
        assert "keep_days" not in _dumped(toml_doc=re_read)
