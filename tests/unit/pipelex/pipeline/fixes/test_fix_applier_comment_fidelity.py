"""Comment fidelity across the applier's structural operations — the banner that introduces a
moved or deleted item goes where the item goes, and the banner of whatever came *next* stays put.

tomlkit stores a comment block written above a table as trailing trivia of the *previous* table in
document order (its deepest last container), and a comment above a key as trivia items sitting
before that key in the same container. A plain ``del`` + re-add therefore leaves a moved table's
banner behind — now labelling whatever followed — and carries the *next* table's banner away
inside the moved body. Both halves are what a migrated configuration file used to show. The
applier now reads every run of own-line comments and blank lines as introducing whatever comes
next, and moves or drops that run with the item it introduces.

Everything here is compared as serialized bytes without the MTHDS formatter, exactly as a
configuration migration runs, so spacing is part of what is pinned.
"""

from pathlib import Path

import pytest
import tomlkit
from tomlkit import TOMLDocument

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.ledger import load_ledger, packaged_migration_dir
from pipelex.pipeline.fixes.applier import FixOpOutcome, apply_fix_ops
from pipelex.suggested_fix import DeleteKeyOp, DeleteTableOp, EnsureTableOp, FixOp, MoveKeyOp, SetKeyOp

_KIT_TEMPLATE = Path("pipelex/kit/configs/pipelex.toml")
_PRE_RESHAPE_DEFAULTS = Path("pipelex/migration/goldens/pipelex-config/defaults@2.toml")

_THREE_SECTIONS = """\
[a]
x = 1

# ---- Section B ----
[b]
y = 2

# ---- Section C ----
[c]
z = 3
"""

_NESTED_DESTINATION = """\
[c]
z = 3

[c.s]
q = 1

# ---- Section D ----
[d]
w = 4

# ---- Section B ----
[b]
y = 2
"""

_PER_KEY_COMMENTS = """\
[a]
# about x
x = 1
# about y
y = 2

[b]
w = 0

# ---- Section C ----
[c]
z = 3
"""

_TABLE_WITH_SUBTABLE = """\
[a]
x = 1

# ---- Section B ----
[b]
y = 2

[b.sub]
q = 1

# ---- Section C ----
[c]
z = 3
"""


def _dumps(toml_doc: TOMLDocument) -> str:
    """One typed funnel over tomlkit's weakly-typed ``dumps``."""
    return tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]


def _apply(*, text: str, ops: list[FixOp]) -> tuple[str, list[FixOpOutcome]]:
    toml_doc = tomlkit.parse(text)
    applications = apply_fix_ops(toml_doc=toml_doc, ops=ops)
    return _dumps(toml_doc), [application.outcome for application in applications]


def _lines_above(*, text: str, header: str, count: int) -> list[str]:
    """The ``count`` lines immediately above the one line equal to ``header``."""
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line == header]
    assert len(matches) == 1, f"expected exactly one '{header}' line, found {len(matches)}"
    return lines[matches[0] - count : matches[0]]


class TestFixApplierCommentFidelity:
    def test_a_moved_table_takes_its_banner_and_leaves_the_next_banner_behind(self) -> None:
        """The banner above ``[b]`` travels to ``[new.b]``; the banner above ``[c]`` stays above ``[c]``."""
        text, outcomes = _apply(
            text=_THREE_SECTIONS,
            ops=[MoveKeyOp(table_path=[], key="b", new_table_path=["new"], new_key="b")],
        )
        assert outcomes == [FixOpOutcome.APPLIED]
        assert text == ("[a]\nx = 1\n\n# ---- Section C ----\n[c]\nz = 3\n\n# ---- Section B ----\n[new.b]\ny = 2\n")

    def test_a_table_moved_into_an_existing_parent_does_not_steal_the_parents_trailing_banner(self) -> None:
        """Appending under ``[c]`` lands *before* the banner that introduces ``[d]``, not after it."""
        text, outcomes = _apply(
            text=_NESTED_DESTINATION,
            ops=[MoveKeyOp(table_path=[], key="b", new_table_path=["c"], new_key="b")],
        )
        assert outcomes == [FixOpOutcome.APPLIED]
        assert text == ("[c]\nz = 3\n\n[c.s]\nq = 1\n\n# ---- Section B ----\n[c.b]\ny = 2\n\n# ---- Section D ----\n[d]\nw = 4\n")

    def test_a_moved_key_takes_the_comment_above_it_and_lands_before_the_destinations_trailing_banner(self) -> None:
        """Per-key comments in the kit's style: the one above ``y`` follows ``y``; ``[c]`` keeps its banner."""
        text, outcomes = _apply(
            text=_PER_KEY_COMMENTS,
            ops=[MoveKeyOp(table_path=["a"], key="y", new_table_path=["b"], new_key="y")],
        )
        assert outcomes == [FixOpOutcome.APPLIED]
        assert text == ("[a]\n# about x\nx = 1\n\n[b]\nw = 0\n# about y\ny = 2\n\n# ---- Section C ----\n[c]\nz = 3\n")

    def test_a_moved_table_with_a_sub_table_leaves_the_next_banner_where_it_was(self) -> None:
        """The next banner lives in the deepest last container of the moved table; it still stays behind."""
        text, outcomes = _apply(
            text=_TABLE_WITH_SUBTABLE,
            ops=[MoveKeyOp(table_path=[], key="b", new_table_path=["new"], new_key="b")],
        )
        assert outcomes == [FixOpOutcome.APPLIED]
        assert text == ("[a]\nx = 1\n\n# ---- Section C ----\n[c]\nz = 3\n\n# ---- Section B ----\n[new.b]\ny = 2\n\n[new.b.sub]\nq = 1\n")

    def test_a_deleted_table_drops_its_own_banner_and_keeps_the_next_one(self) -> None:
        text, outcomes = _apply(text=_THREE_SECTIONS, ops=[DeleteTableOp(table_path=["b"])])
        assert outcomes == [FixOpOutcome.APPLIED]
        assert text == ("[a]\nx = 1\n\n# ---- Section C ----\n[c]\nz = 3\n")

    def test_a_deleted_key_drops_the_comment_above_it_and_keeps_its_neighbours(self) -> None:
        text, outcomes = _apply(text=_PER_KEY_COMMENTS, ops=[DeleteKeyOp(table_path=["a"], key="y")])
        assert outcomes == [FixOpOutcome.APPLIED]
        assert text == ("[a]\n# about x\nx = 1\n\n[b]\nw = 0\n\n# ---- Section C ----\n[c]\nz = 3\n")

    def test_a_move_without_any_comment_around_it_is_unchanged_from_before(self) -> None:
        """No trivia to carry: the placement and spacing tomlkit gives an appended table are kept."""
        text, outcomes = _apply(
            text="[a]\nx = 1\n\n[b]\ny = 2\n\n[c]\nz = 3\n",
            ops=[MoveKeyOp(table_path=[], key="b", new_table_path=["new"], new_key="b")],
        )
        assert outcomes == [FixOpOutcome.APPLIED]
        assert text == "[a]\nx = 1\n\n[c]\nz = 3\n\n[new.b]\ny = 2\n"

    @pytest.mark.parametrize(
        ("source", "ops", "expected"),
        [
            pytest.param(
                "[a]\nx = 1\n\n[b]\ny = 2\n",
                [MoveKeyOp(table_path=[], key="a", new_table_path=["new"], new_key="a")],
                "[b]\ny = 2\n\n[new.a]\nx = 1\n",
                id="removing the file's first table leaves no blank line at the top",
            ),
            pytest.param(
                "# my config\n\n[a]\nx = 1\n\n[b]\ny = 2\n",
                [MoveKeyOp(table_path=[], key="a", new_table_path=["new"], new_key="a")],
                "# my config\n\n[b]\ny = 2\n\n[new.a]\nx = 1\n",
                id="a lone comment block at the top, set apart by a blank line, is the file's preamble and stays",
            ),
            pytest.param(
                "# my config\n# more\n\n# A banner\n[a]\nx = 1\n\n[b]\ny = 2\n",
                [MoveKeyOp(table_path=[], key="a", new_table_path=["new"], new_key="a")],
                "# my config\n# more\n\n[b]\ny = 2\n\n# A banner\n[new.a]\nx = 1\n",
                id="a preamble stays while the banner below it travels",
            ),
            pytest.param(
                "# A banner\n[a]\nx = 1\n\n[b]\ny = 2\n",
                [MoveKeyOp(table_path=[], key="a", new_table_path=["new"], new_key="a")],
                "[b]\ny = 2\n\n# A banner\n[new.a]\nx = 1\n",
                id="a banner glued to the first header travels, and gets the blank line tomlkit gives an appended table",
            ),
            pytest.param(
                "# root note\nname = 'x'\n\n[a]\nx = 1\n",
                [MoveKeyOp(table_path=[], key="name", new_table_path=["a"], new_key="name")],
                "[a]\nx = 1\n# root note\nname = 'x'\n",
                id="a comment glued to the file's first key travels with the key",
            ),
            pytest.param(
                "# preamble\n\n[a]\n# about x\nx = 1\n",
                [MoveKeyOp(table_path=["a"], key="x", new_table_path=[], new_key="x")],
                "# preamble\n# about x\nx = 1\n\n[a]\n",
                id="a key moved to the root of a file lands under the preamble, not above it",
            ),
            pytest.param(
                "[t]\nz = 0\n# note on sub\n\n[t.sub]\nq = 1\n\n[a]\n# about x\nx = 1\n",
                [MoveKeyOp(table_path=["a"], key="x", new_table_path=["t"], new_key="x")],
                "[t]\nz = 0\n# about x\nx = 1\n# note on sub\n\n[t.sub]\nq = 1\n\n[a]\n",
                id="a key inserted before a table's first sub-table takes its comment and leaves the sub-table's note on the sub-table",
            ),
            pytest.param(
                "[t]\n# note on sub\n[t.sub]\nq = 1\n\n[a]\nx = 1\n",
                [MoveKeyOp(table_path=["a"], key="x", new_table_path=["t"], new_key="x")],
                "[t]\nx = 1\n\n# note on sub\n[t.sub]\nq = 1\n\n[a]\n",
                id="the blank line tomlkit adds under an inserted key sits above the note that follows it, not between the note and its header",
            ),
            pytest.param(
                "# preamble\n\n# ---- Storage ----\n\n[runtime.storage]\nm = 1\n\n# ---- Secrets ----\n\n[runtime.secrets]\ns = 1\n",
                [MoveKeyOp(table_path=["runtime"], key="storage", new_table_path=["relocated"], new_key="storage")],
                "# preamble\n\n# ---- Secrets ----\n\n[runtime.secrets]\ns = 1\n\n# ---- Storage ----\n\n[relocated.storage]\nm = 1\n",
                id="the first entry of an implicit parent is introduced by what sits above the parent, and no bare [runtime] header appears",
            ),
            pytest.param(
                "[t]\n\n[a]\nx = 1\n\n# B banner\n[b]\ny = 2\n\n[c]\nz = 3\n",
                [MoveKeyOp(table_path=[], key="b", new_table_path=["t"], new_key="b")],
                "[t]\n\n# B banner\n[t.b]\ny = 2\n\n[a]\nx = 1\n\n[c]\nz = 3\n",
                id="moved into an empty explicit table, the banner sits under that table's header",
            ),
            pytest.param(
                "[a]\nx = 1\n\n# B banner\n[b]\ny = 2\n\n# C banner\n[c]\nz = 3\n",
                [MoveKeyOp(table_path=[], key="b", new_table_path=["a", "new"], new_key="b")],
                "[a]\nx = 1\n\n# B banner\n[a.new.b]\ny = 2\n\n# C banner\n[c]\nz = 3\n",
                id="a created intermediate parent under an existing one carries the banner above the outermost created header",
            ),
            pytest.param(
                "[a]\nx = 1\n\n# exporters\n[[otlp]]\nendpoint = 1\n\n[[otlp]]\nendpoint = 2\n\n# next\n[next]\nz = 3\n",
                [MoveKeyOp(table_path=[], key="otlp", new_table_path=["tel"], new_key="otlp")],
                "[a]\nx = 1\n\n# next\n[next]\nz = 3\n\n# exporters\n[[tel.otlp]]\nendpoint = 1\n\n[[tel.otlp]]\nendpoint = 2\n",
                id="an array of tables travels with its banner and leaves the next banner behind",
            ),
            pytest.param(
                "[deck.gpt]\n# tier of gpt\ntier = 1\nprovider = 'o'\n\n"
                "[deck.claude]\n# tier of claude\ntier = 2\nprovider = 'a'\n\n# after\n[levels]\nx = 1\n",
                [DeleteKeyOp(table_path=["deck", "*"], key="tier")],
                "[deck.gpt]\nprovider = 'o'\n\n[deck.claude]\nprovider = 'a'\n\n# after\n[levels]\nx = 1\n",
                id="a wildcard op applies to every match on one document without losing track of positions",
            ),
            pytest.param(
                "[a]\nx = 1\n\n# B banner\n[b]\ny = 2\n\n# end of file note\n",
                [MoveKeyOp(table_path=[], key="b", new_table_path=["new"], new_key="b")],
                "[a]\nx = 1\n\n# B banner\n[new.b]\ny = 2\n\n# end of file note\n",
                id="a note at the end of the file stays at the end of the file",
            ),
            pytest.param(
                "[a]\nx = 1\n\n# B banner\n[b]\ny = 2\n",
                [DeleteTableOp(table_path=["b"])],
                "[a]\nx = 1\n",
                id="deleting the last table of the file takes its banner and the blank line above it",
            ),
            pytest.param(
                "# ---- Storage ----\n[runtime.storage]\nm = 1\n\n# ---- Secrets ----\n[runtime.secrets]\ns = 1\n",
                [MoveKeyOp(table_path=["runtime"], key="storage", new_table_path=["relocated"], new_key="storage")],
                "# ---- Secrets ----\n[runtime.secrets]\ns = 1\n\n# ---- Storage ----\n[relocated.storage]\nm = 1\n",
                id="removing the file's first table from under an implicit parent leaves no blank line at the top",
            ),
            pytest.param(
                "# preamble\n\n# ---- Storage ----\npipelex.storage_config = { x = 1 }\n\n# ---- Other ----\n[other]\nk = 1\n",
                [MoveKeyOp(table_path=["pipelex"], key="storage_config", new_table_path=["runtime"], new_key="storage_config")],
                "# preamble\n\n# ---- Other ----\n[other]\nk = 1\n\n# ---- Storage ----\n[runtime]\nstorage_config = { x = 1 }\n",
                id="a dotted assignment at the root is introduced by what sits above it, since its implicit parent renders no header",
            ),
            pytest.param(
                "# ---- Log ----\npipelex.log_config.level = 'INFO'\n\n# ---- Other ----\n[other]\nk = 1\n",
                [MoveKeyOp(table_path=["pipelex"], key="log_config", new_table_path=["runtime"], new_key="log_config")],
                "# ---- Other ----\n[other]\nk = 1\n\n# ---- Log ----\n[runtime.log_config]\nlevel = 'INFO'\n",
                id="a deeper dotted assignment climbs through every header-less parent to its banner",
            ),
            pytest.param(
                "# ---- Storage ----\npipelex.storage_config = { x = 1 }\n\n# ---- Other ----\n[other]\nk = 1\n",
                [DeleteKeyOp(table_path=["pipelex"], key="storage_config")],
                "# ---- Other ----\n[other]\nk = 1\n",
                id="deleting a dotted-assignment key drops the banner above it",
            ),
            pytest.param(
                "[a]\nx = 1\n\n# B banner\n[b]\ny = 2\n",
                [SetKeyOp(table_path=["a"], key="z", value=3)],
                "[a]\nx = 1\nz = 3\n\n# B banner\n[b]\ny = 2\n",
                id="a key set into a table lands before the table's trailing banner, not after it",
            ),
            pytest.param(
                "[a]\nx = 1\n\n# B banner\n[b]\ny = 2\n",
                [EnsureTableOp(table_path=["a", "sub"])],
                "[a]\nx = 1\nsub = {}\n\n# B banner\n[b]\ny = 2\n",
                id="a table ensured under a table lands before the table's trailing banner, not after it",
            ),
            pytest.param(
                "[a]\n# about x\nx = 1\n\n# B banner\n[b]\ny = 2\n",
                [SetKeyOp(table_path=["a"], key="x", value=2)],
                "[a]\n# about x\nx = 2\n\n# B banner\n[b]\ny = 2\n",
                id="setting an existing key rewrites it in place and moves no comment",
            ),
            pytest.param(
                "# A banner\n[a]\nx = 1\n",
                [SetKeyOp(table_path=[], key="main_pipe", value="p")],
                'main_pipe = "p"\n\n# A banner\n[a]\nx = 1\n',
                id="a root key set into a file whose first header carries a banner lands above the banner",
            ),
            pytest.param(
                "[pipe.first]\na = 1\n\n# concepts\n[concept]\nIdea = 'x'\n\n[pipe.first.inputs]\nt = 'Text'\n",
                [SetKeyOp(table_path=["pipe", "first"], key="output", value="Text")],
                "[pipe.first]\na = 1\noutput = \"Text\"\n\n# concepts\n[concept]\nIdea = 'x'\n\n[pipe.first.inputs]\nt = 'Text'\n",
                id="a key set into an out-of-order chunk lands in that chunk, before the next section's banner",
            ),
            pytest.param(
                "[t]\nz = 0\n\n# note on sub\n[t.sub]\nq = 1\n\n[a]\n# about x\nx = 1\n",
                [MoveKeyOp(table_path=["a"], key="x", new_table_path=["t"], new_key="x")],
                "[t]\nz = 0\n# about x\nx = 1\n\n# note on sub\n[t.sub]\nq = 1\n\n[a]\n",
                id="a trailing run that already opens on a blank line does not gain a second one from tomlkit's indent",
            ),
        ],
    )
    def test_edge_shapes(self, source: str, ops: list[FixOp], expected: str) -> None:
        text, outcomes = _apply(text=source, ops=ops)
        assert outcomes == [FixOpOutcome.APPLIED]
        assert text == expected
        tomlkit.parse(text)

    def test_the_kit_template_keeps_every_banner_on_its_section_through_a_move(self) -> None:
        """The real, heavily-commented template: the storage banner follows storage, the next stays."""
        text, outcomes = _apply(
            text=_KIT_TEMPLATE.read_text(encoding="utf-8"),
            ops=[MoveKeyOp(table_path=["runtime"], key="storage", new_table_path=["relocated"], new_key="storage")],
        )
        assert outcomes == [FixOpOutcome.APPLIED]
        rule = "#" * 100
        assert _lines_above(text=text, header="[relocated.storage]", count=4) == [rule, "# Storage Config", rule, ""]
        assert _lines_above(text=text, header="[runtime.secrets]", count=4) == [rule, "# Secrets Config", rule, ""]

    def test_the_reshape_entry_carries_every_section_banner_with_its_section(self) -> None:
        """The shipped `pipelex-config` ledger over the frozen pre-reshape defaults, banner by banner.

        This is the file shape the bug was reported on: a document seeded from a heavily-commented
        template, migrated by the configuration reshape. Every ``# <Name> config`` banner that
        introduced a section before must introduce the same section after — wherever it moved to.
        """
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id="pipelex-config")
        replay = replay_ledger_over_text(ledger=ledger, text=_PRE_RESHAPE_DEFAULTS.read_text(encoding="utf-8"))
        assert replay.blocked == []
        rule = "#" * 100
        expected_headers_by_banner = {
            # moved out of [pipelex] into a created root section
            "# Log config": "[runtime.log]",
            "# Tracing config (event log for distributed tracing across workers)": "[runtime.tracing]",
            "# Templating config": "[inference.templating]",
            "# Dry run config": "[inference.dry_run]",
            # moved out of an out-of-order [pipelex] chunk to the document root
            "# Kit Config": "[kit]",
            # renamed in place
            "# Cogt inference config": "[inference]",
            "# Pipe run config": "[interpreter.pipe_run]",
            "# Pipeline execution config": "[interpreter.pipeline_execution]",
        }
        for banner, header in expected_headers_by_banner.items():
            assert _lines_above(text=replay.text, header=header, count=4) == [rule, banner, rule, ""], header
        # The banner of a deleted section goes with it.
        assert "# Migration config" not in replay.text
        # And every banner in the migrated file introduces a header, not a stray key.
        lines = replay.text.splitlines()
        for index, line in enumerate(lines):
            if line == rule and index + 2 < len(lines) and lines[index + 2] == rule and lines[index + 1] != "#":
                # A banner in the last lines of the file introduces nothing: that is a failure, not a skip.
                following = lines[index + 4] if index + 4 < len(lines) else "<end of file>"
                assert following.startswith("["), f"banner {lines[index + 1]!r} is followed by {following!r}"
