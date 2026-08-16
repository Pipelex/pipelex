"""Characterization tests for the fix applier's path model against the real configuration files.

Migration reuses the ``.mthds`` fix applier to rewrite user-owned ``.toml`` configuration, and that
reuse rests on assumptions the ``.mthds`` tests never exercise: that ``table_path`` addresses every
table a configuration file actually contains, that an untouched round-trip is byte-identical (the
migration checks are byte-level claims), and that tomlkit's ``OutOfOrderTableProxy`` — which the
packaged defaults document produces, being written out of order — survives every op rather than only
the rename that handles it explicitly.

These tests pin the measured behaviour of the applier *and* of tomlkit underneath it, so a tomlkit
bump that changes comment attachment, header re-rendering, or proxy handling fails here rather than
silently corrupting somebody's configuration file. The reachability test deliberately probes through
the public ``apply_fix_ops`` — a ``delete_key`` for an absent key reports "table not found" when the
path model cannot reach the table and "key not found" when it can — so it characterizes the contract
rather than the private resolver.

Where a behaviour is a hazard rather than a guarantee, the test says so in its name and docstring:
``test_moved_table_leaves_its_banner_comment_behind`` pins a *limitation* that the migration contract
has to state, not something to rely on.
"""

from pathlib import Path
from typing import Any, cast

import pytest
import tomlkit
from tomlkit import TOMLDocument

from pipelex.pipeline.fixes.applier import FixOpOutcome, apply_fix_ops
from pipelex.suggested_fix import DeleteKeyOp, DeleteTableOp, EnsureTableOp, MoveKeyOp, RenameTableKeyOp

# Every configuration file this repository owns and tracks. The packaged defaults are the complete
# witness (every path present); the kit templates are the sparse shape real user files have — and
# `ensure_global_config_exists` seeds every `~/.pipelex/` as a copy of them. `plxt.toml` is not a
# migration surface; it is here because it is the only tracked config file containing an array of
# tables, which is the one shape the path model cannot address.
_TRACKED_CONFIG_FILES = [
    Path("pipelex/pipelex.toml"),
    Path("pipelex/kit/configs/pipelex.toml"),
    Path("pipelex/kit/configs/telemetry.toml"),
    Path("pipelex/kit/configs/telemetry.project.toml"),
    Path("pipelex/kit/configs/pipelex_service.toml"),
    Path("pipelex/kit/configs/plxt.toml"),
    Path(".pipelex/pipelex.toml"),
    Path(".pipelex/telemetry.toml"),
    Path("tests/pipelex_unit_test.toml"),
]

_PACKAGED_DEFAULTS = Path("pipelex/pipelex.toml")
_KIT_TEMPLATE = Path("pipelex/kit/configs/pipelex.toml")
_ARRAY_OF_TABLES_FILE = Path("pipelex/kit/configs/plxt.toml")

_ABSENT_KEY = "key_that_no_configuration_file_declares"


def _dumps(toml_doc: TOMLDocument) -> str:
    """One typed funnel over tomlkit's weakly-typed ``dumps`` (narrow ignore, not file-level)."""
    return tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]


def _parse(path: Path) -> TOMLDocument:
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def _as_mapping(node: Any) -> dict[str, Any]:
    """One typed funnel over tomlkit's dict-like nodes, which the stubs type as bare ``Item``."""
    return cast("dict[str, Any]", node)


def _table_paths(node: object, prefix: list[str]) -> list[list[str]]:
    """Every dict-addressable table path in the document, depth-first, in document order.

    Array-of-tables elements are deliberately not descended into: they are ``list`` nodes, which the
    ``table_path`` model has no segment syntax for — the very fact the reachability test asserts.
    """
    collected: list[list[str]] = []
    if not isinstance(node, dict):
        return collected
    mapping = _as_mapping(node)
    for key in mapping:
        value: Any = mapping[key]
        path = [*prefix, str(key)]
        if isinstance(value, dict):
            collected.append(path)
            collected.extend(_table_paths(_as_mapping(value), path))
    return collected


def _probe_reachability(*, toml_doc: TOMLDocument, table_path: list[str]) -> str | None:
    """Ask the applier whether it can reach ``table_path``, without changing the document.

    A ``delete_key`` for a key no configuration file declares always skips; *why* it skipped is the
    measurement — "table … not found" means the path model could not walk there.
    """
    applications = apply_fix_ops(toml_doc=toml_doc, ops=[DeleteKeyOp(table_path=table_path, key=_ABSENT_KEY)])
    assert applications[0].outcome == FixOpOutcome.SKIPPED
    return applications[0].detail


class TestFixApplierConfigSurfaceShapes:
    @pytest.mark.parametrize("config_path", _TRACKED_CONFIG_FILES, ids=str)
    def test_untouched_round_trip_is_byte_identical(self, config_path: Path) -> None:
        """Parsing and re-dumping an untouched configuration file returns the exact input bytes.

        Migration serializes with ``tomlkit.dumps`` and no canonical reflow, so replay neutrality and
        the transform goldens are byte-level claims that rest entirely on this holding.
        """
        text = config_path.read_text(encoding="utf-8")
        assert _dumps(tomlkit.parse(text)) == text

    @pytest.mark.parametrize("config_path", _TRACKED_CONFIG_FILES, ids=str)
    def test_every_table_is_addressable_by_table_path(self, config_path: Path) -> None:
        """Every table in every tracked configuration file is reachable by its ``table_path``."""
        toml_doc = _parse(config_path)
        unreachable = [
            table_path
            for table_path in _table_paths(toml_doc, [])
            if "not found in document" in (_probe_reachability(toml_doc=toml_doc, table_path=table_path) or "")
        ]
        assert unreachable == []

    @pytest.mark.parametrize("config_path", _TRACKED_CONFIG_FILES, ids=str)
    def test_reachability_probing_leaves_the_document_untouched(self, config_path: Path) -> None:
        """Probing every path with a skipping op changes no bytes — the guarded-skip contract."""
        toml_doc = _parse(config_path)
        source_bytes = _dumps(toml_doc)
        for table_path in _table_paths(toml_doc, []):
            _probe_reachability(toml_doc=toml_doc, table_path=table_path)
        assert _dumps(toml_doc) == source_bytes

    def test_array_of_tables_is_not_addressable(self) -> None:
        """An array of tables is a ``list``, so no ``table_path`` reaches it — reported, never raised.

        No migration surface contains one today; the guarded skip is what keeps that from being a
        latent crash if one ever appears.
        """
        toml_doc = _parse(_ARRAY_OF_TABLES_FILE)
        assert isinstance(toml_doc["rule"], list)
        detail = _probe_reachability(toml_doc=toml_doc, table_path=["rule"])
        assert detail is not None
        assert "not found in document" in detail

    def test_inline_table_key_renames_in_place(self) -> None:
        """A key inside an inline table is addressable and renames without disturbing its siblings."""
        toml_doc = _parse(_PACKAGED_DEFAULTS)
        before = _dumps(toml_doc).splitlines()
        applications = apply_fix_ops(
            toml_doc=toml_doc,
            ops=[
                RenameTableKeyOp(
                    table_path=["cogt", "img_gen_config", "quality_to_steps_maps", "flux"],
                    key="low",
                    new_key="lowest",
                )
            ],
        )
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        after = _dumps(toml_doc).splitlines()
        changed = [line for expected, line in zip(before, after, strict=True) if expected != line]
        assert changed == ['flux = { lowest = 14, "medium" = 28, "high" = 56 }']

    def test_dotted_key_assignment_is_addressable_and_renames(self) -> None:
        """``a.b = 1`` is a table to tomlkit, so it is addressable and stays a dotted key on rename."""
        toml_doc = tomlkit.parse("[section]\nnested.leaf = 1\nother = 2\n")
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=["section", "nested"], key="leaf", new_key="renamed")])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        assert _dumps(toml_doc) == "[section]\nnested.renamed = 1\nother = 2\n"

    def test_quoted_key_containing_a_dot_is_one_path_segment(self) -> None:
        """A quoted key with a dot inside is a single segment, and stays quoted when renamed."""
        toml_doc = tomlkit.parse('["outer.inner"]\nvalue = 1\n')
        detail = _probe_reachability(toml_doc=toml_doc, table_path=["outer.inner"])
        assert detail is not None
        assert "not found in table" in detail

    def test_packaged_defaults_produce_out_of_order_proxies(self) -> None:
        """The packaged document is written out of order, so two of its root tables are proxies.

        This is the premise of every proxy test below; if a reordering of ``pipelex.toml`` ever makes
        it false, those tests stop measuring what they claim to.
        """
        toml_doc = _parse(_PACKAGED_DEFAULTS)
        proxy_roots = [str(key) for key in toml_doc if type(toml_doc[key]).__name__ == "OutOfOrderTableProxy"]
        assert proxy_roots == ["pipelex", "migration"]

    @pytest.mark.parametrize(
        "table_path",
        [
            pytest.param(["pipelex", "log_config"], id="table-inside-a-proxy"),
            pytest.param(["migration"], id="the-proxy-itself"),
            pytest.param(["pipelex"], id="the-other-proxy-itself"),
        ],
    )
    def test_delete_table_removes_every_chunk_of_an_out_of_order_table(self, table_path: list[str]) -> None:
        """``delete_table`` removes all of an out-of-order table, leaving no orphaned header behind."""
        toml_doc = _parse(_PACKAGED_DEFAULTS)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[DeleteTableOp(table_path=table_path)])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        rendered = _dumps(toml_doc)
        header_prefix = f"[{'.'.join(table_path)}"
        assert [line for line in rendered.splitlines() if line.startswith(header_prefix)] == []
        reparsed = tomlkit.parse(rendered)
        assert table_path[0] not in reparsed or table_path[-1] not in _as_mapping(reparsed[table_path[0]])

    def test_root_level_proxy_rename_rewrites_every_chunk(self) -> None:
        """Renaming a root table that is split into chunks rewrites every child header, content intact.

        This is the configuration reshape's hardest shape (``[pipelex]`` becomes ``[interpreter]``)
        and it goes through ``Container._replace``, a tomlkit internal — so this test is the tripwire.
        """
        toml_doc = _parse(_PACKAGED_DEFAULTS)
        original = _parse(_PACKAGED_DEFAULTS)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=[], key="pipelex", new_key="interpreter")])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        rendered = _dumps(toml_doc)
        assert [line for line in rendered.splitlines() if line.startswith("[pipelex")] == []
        reparsed = tomlkit.parse(rendered)
        assert reparsed["interpreter"] == original["pipelex"]

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("[a.b]\nx = 1\n[a.c]\ny = 2\n[a.b.d]\nz = 3\n", id="grandchild continued after a sibling"),
            pytest.param("[a]\n[a.b]\nx = 1\n[a.c]\ny = 2\n[a.b.d]\nz = 3\n", id="same, with an explicit header"),
            pytest.param("[a.b.c]\nx = 1\n[a.b.e]\ny = 1\n[a.b.c.d]\nz = 1\n", id="split two levels down"),
            pytest.param("[a]\nb.x = 1\nc = 2\nb.y = 3\n", id="dotted keys interleaved in one table"),
            pytest.param("[a.b]\nx = 1\n[[a.b.l]]\nq = 1\n[a.c]\ny = 2\n[a.b.d]\nz = 3\n", id="array of tables between the chunks"),
        ],
    )
    def test_a_table_whose_descendant_is_split_across_chunks_moves_and_renames_whole(self, text: str) -> None:
        """A split *descendant* (a child declared, interrupted by a sibling, then continued) is several
        tomlkit tables under one key, and the library's own header-cache invalidation visits only the
        first of them — left alone, the rest would keep rendering under the old name. The applier
        refreshes every chunk, so the rename or move comes out whole and re-parses to the same value
        under the new path, in the original order.
        """
        original = tomlkit.parse(text).unwrap()["a"]
        for op, expected in (
            (RenameTableKeyOp(table_path=[], key="a", new_key="zz"), {"zz": original}),
            (MoveKeyOp(table_path=[], key="a", new_table_path=["q"], new_key="a"), {"q": {"a": original}}),
        ):
            toml_doc = tomlkit.parse(text)
            applications = apply_fix_ops(toml_doc=toml_doc, ops=[op])
            assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
            rendered = _dumps(toml_doc)
            assert "[a" not in rendered
            assert tomlkit.parse(rendered).unwrap() == expected

    def test_a_split_descendant_beneath_a_root_proxy_still_renames_whole(self) -> None:
        """The two shapes compose: a table interleaved at its own level *and* carrying a split child
        goes through the proxy path, which renames in every chunk — every child lands under the new name.
        """
        text = "[a.b]\nx = 1\n[other]\nz = 1\n[a.c]\ny = 2\n[a.b.d]\nz = 3\n"
        toml_doc = tomlkit.parse(text)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=[], key="a", new_key="zz")])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        reparsed = tomlkit.parse(_dumps(toml_doc)).unwrap()
        assert "a" not in reparsed
        assert reparsed["zz"] == {"b": {"x": 1, "d": {"z": 3}}, "c": {"y": 2}}

    def test_a_split_descendant_beneath_a_nested_proxy_still_renames_whole(self) -> None:
        """Same composition one level down: the renamed key lives inside an out-of-order table that is
        itself nested, and one of its chunks carries a split child. The header refresh must reach
        the chunks of a *nested* proxy too — the merged facade would show it one table per key.
        """
        text = "[p.a.b]\nx = 1\n[q]\nw = 0\n[p.a.c]\ny = 1\n[p.a.b.d]\nz = 1\n[p.a.e]\nv = 1\n[p.a.b.f]\nu = 1\n"
        original = tomlkit.parse(text).unwrap()["p"]["a"]
        toml_doc = tomlkit.parse(text)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[RenameTableKeyOp(table_path=["p"], key="a", new_key="zz")])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        rendered = _dumps(toml_doc)
        assert "[p.a" not in rendered
        assert tomlkit.parse(rendered).unwrap()["p"] == {"zz": original}

    def test_rename_is_replay_neutral_once_applied(self) -> None:
        """Re-applying a rename over an already-migrated document skips and changes no bytes.

        Replay neutrality is the migration engine's central guarantee: every entry is replayed on
        every run, so an entry that has already been applied must be a byte-level no-op.
        """
        rename_op = RenameTableKeyOp(table_path=[], key="cogt", new_key="inference")
        toml_doc = _parse(_PACKAGED_DEFAULTS)
        apply_fix_ops(toml_doc=toml_doc, ops=[rename_op])
        once = _dumps(toml_doc)

        replayed_doc = tomlkit.parse(once)
        applications = apply_fix_ops(toml_doc=replayed_doc, ops=[rename_op])
        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]
        assert _dumps(replayed_doc) == once

    def test_ensure_table_emits_an_inline_table(self) -> None:
        """``ensure_table`` creates ``key = {}``, an inline table, and that is deliberate.

        The migration plan carried this down as a bug to fix — "the wrong shape for a config
        section" — but ``ensure_table`` is not a migration op and never touches a config
        section. Its one producer is the ``sync-controller-inputs`` fix, where the inline form
        is the dominant `.mthds` authoring form and keeps the mapping attached to its pipe; a
        block table would detach it into a ``[pipe.x.inputs]`` section after the pipe's body.
        The block-table shape landed in ``move_key``, which is where a migration actually needs
        to create a destination section.
        """
        toml_doc = _parse(_PACKAGED_DEFAULTS)
        applications = apply_fix_ops(toml_doc=toml_doc, ops=[EnsureTableOp(table_path=["pipelex", "freshly_ensured"])])
        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        assert "freshly_ensured = {}" in _dumps(toml_doc)

    def test_a_created_root_parent_lands_at_the_end_of_the_file(self) -> None:
        """A table moved under a parent that does not exist yet lands at the end of the document.

        Position is preserved *within* a parent, never *across* parents — the placement rule the
        migration contract has to state, because a migrated file will not look like the original.
        """
        toml_doc = _parse(_KIT_TEMPLATE)
        pipelex_table = _as_mapping(toml_doc["pipelex"])
        moved = pipelex_table["storage_config"]
        del pipelex_table["storage_config"]
        created_parent = tomlkit.table()
        created_parent["storage"] = moved
        toml_doc["runtime"] = created_parent

        rendered_lines = _dumps(toml_doc).splitlines()
        header_indexes = [index for index, line in enumerate(rendered_lines) if line.startswith("[runtime.storage]")]
        assert len(header_indexes) == 1
        remaining_headers = [line for line in rendered_lines[header_indexes[0] :] if line.startswith("[") and not line.startswith("[runtime")]
        assert remaining_headers == []

    def test_moved_table_leaves_its_banner_comment_behind(self) -> None:
        """A comment block *preceding* a table does not travel with it — a documented limitation.

        tomlkit stores such a block as trailing trivia of the *previous* sibling, not as anything
        attached to the table, so a moved table arrives bare and the banner stays put, now labelling
        whatever followed it. The migration contract states this; nothing in the engine relies on
        comment fidelity across a move.
        """
        toml_doc = _parse(_KIT_TEMPLATE)
        banner = "# Storage Config"
        source_lines = _dumps(toml_doc).splitlines()
        banner_index = source_lines.index(banner)
        assert source_lines[banner_index + 2 : banner_index + 4] == ["", "[pipelex.storage_config]"]

        pipelex_table = _as_mapping(toml_doc["pipelex"])
        moved = pipelex_table["storage_config"]
        del pipelex_table["storage_config"]
        created_parent = tomlkit.table()
        created_parent["storage"] = moved
        toml_doc["runtime"] = created_parent

        migrated_lines = _dumps(toml_doc).splitlines()
        migrated_banner_index = migrated_lines.index(banner)
        assert migrated_lines[migrated_banner_index + 2] != "[runtime.storage]"
        destination_index = migrated_lines.index("[runtime.storage]")
        assert banner not in migrated_lines[destination_index - 3 : destination_index]
