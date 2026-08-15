"""Unit tests for the coverage gate — the forcing function that makes a schema change say what it did.

Every test here points the gate at a **synthetic** surface with a fixture ledger and a fixture
golden chain in a temporary directory. That is not incidental: the surface registry is an injected
parameter precisely so gate *behaviour* can be tested against something that never moves. Wire the
real configuration models in here and every legitimate configuration change turns this suite red
alongside the gate, and the fix everyone learns is "regenerate the goldens" — which is how a gate
goes permanently green while catching nothing. The real surfaces get one smoke test, and it lives
in `test_real_surfaces.py`.

The shape of each test is the same: describe schema 1 and schema 2 as two synthetic models, write
the golden the gate will compare against, hand it a ledger entry, and assert which guarantee broke.
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from pipelex.migration.coverage import CoverageIssue, CoverageIssueKind, check_surface, diff_fingerprints
from pipelex.migration.fingerprint import compute_fingerprint
from pipelex.migration.goldens import write_defaults_golden, write_fingerprint_golden
from pipelex.migration.ledger import ledgers_dir
from pipelex.migration.surfaces import DefaultsLayerKind, Surface

SURFACE_ID = "synthetic-config"


class _Tier(StrEnum):
    BASIC = "basic"
    PREMIUM = "premium"


class _TierWithoutBasic(StrEnum):
    PREMIUM = "premium"
    STANDARD = "standard"


class _SchemaOne(BaseModel):
    """The starting shape: a section with two keys, one of them enumerated."""

    label: str = "hello"
    tier: _Tier = _Tier.BASIC


class _SchemaTwoRenamed(BaseModel):
    """`label` renamed to `title`."""

    title: str = "hello"
    tier: _Tier = _Tier.BASIC


class _SchemaTwoRemoved(BaseModel):
    """`label` dropped outright."""

    tier: _Tier = _Tier.BASIC


class _SchemaTwoEnumMemberGone(BaseModel):
    """`basic` is no longer a legal spelling of `tier`."""

    label: str = "hello"
    tier: _TierWithoutBasic = _TierWithoutBasic.PREMIUM


class _SchemaTwoTierRenamedAndMemberGone(BaseModel):
    """`tier` renamed to `level` *and* `basic` dropped, in the same schema version."""

    label: str = "hello"
    level: _TierWithoutBasic = _TierWithoutBasic.PREMIUM


class _SchemaOneWithBothNames(BaseModel):
    """A starting shape that already has `title`, so a rename of `label` onto it collides."""

    label: str = "hello"
    title: str = "world"
    tier: _Tier = _Tier.BASIC


def _surface(*, config_model: type[BaseModel]) -> Surface:
    return Surface(
        surface_id=SURFACE_ID,
        title="A synthetic surface",
        base_file="synthetic.toml",
        tier_glob="synthetic_*.toml",
        config_model=config_model,
        defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
    )


def _write_ledger(*, migration_dir: Path, current_schema_version: int, entries: str = "") -> None:
    directory = ledgers_dir(migration_dir=migration_dir)
    directory.mkdir(parents=True, exist_ok=True)
    body = f"""
[surface]
id                           = "{SURFACE_ID}"
title                        = "A synthetic surface"
base_file                    = "synthetic.toml"
tier_glob                    = "synthetic_*.toml"
current_schema_version       = {current_schema_version}
min_supported_schema_version = 0
{entries}
"""
    (directory / f"{SURFACE_ID}.toml").write_text(body, encoding="utf-8")


def _snapshot(*, migration_dir: Path, config_model: type[BaseModel], schema_version: int) -> None:
    surface = _surface(config_model=config_model)
    write_fingerprint_golden(
        migration_dir=migration_dir,
        fingerprint=compute_fingerprint(
            surface_id=SURFACE_ID,
            schema_version=schema_version,
            config_model=config_model,
            defaults_document=surface.read_defaults_document(),
        ),
    )


def _kinds(issues: list[CoverageIssue]) -> list[CoverageIssueKind]:
    return [issue.kind for issue in issues]


def _rename_entry(*, new_key: str = "title", safety: str = "safe") -> str:
    return f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "{safety}"
title             = "Rename label to title"
description       = "The key was renamed."

[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "label"
new_key    = "{new_key}"
"""


def _pre_history_entry() -> str:
    """An entry about `legacy_mode`, a key no fingerprint in this chain has ever recorded."""
    return f"""
[[migration]]
id                     = "{SURFACE_ID}@2"
to_schema_version      = 2
introduced_in          = "0.46.0"
breaking               = true
safety                 = "safe"
title                  = "Drop a key that predates the chain"
description            = "It was gone before anything was snapshotted."
pre_history            = true
declared_removed_paths = ["legacy_mode"]

[[migration.ops]]
kind       = "delete_key"
table_path = []
key        = "legacy_mode"
"""


class TestTheSteadyState:
    def test_a_surface_whose_golden_matches_its_models_passes(self, tmp_path: Path) -> None:
        """The overwhelmingly common state: nothing changed, so nothing is owed."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        assert check_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path) == []

    def test_a_surface_with_no_snapshot_at_all_asks_for_one(self, tmp_path: Path) -> None:
        """The bootstrap state, and the only one with no diff to show."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        issues = check_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.SNAPSHOT_PENDING]


class TestTheHeadLink:
    def test_an_additive_change_asks_for_a_regeneration_and_demands_no_entry(self, tmp_path: Path) -> None:
        """A key we add is supplied by the defaults layer, so an old file still validates."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRemoved, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.FINGERPRINT_DRIFTED]
        assert "label" in issues[0].message

    def test_a_removal_without_a_bump_is_refused(self, tmp_path: Path) -> None:
        """The whole point of the gate: this is the change that breaks a user's boot."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRemoved), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.REMOVAL_NEEDS_A_BUMP]
        assert f"{SURFACE_ID}@2" in issues[0].message

    def test_a_lost_enum_member_without_a_bump_is_refused_too(self, tmp_path: Path) -> None:
        """A renamed enumerated value breaks a file exactly as a renamed key does."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoEnumMemberGone), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.REMOVAL_NEEDS_A_BUMP]
        assert "basic" in issues[0].message

    def test_a_stale_reference_document_is_caught_even_when_the_fingerprint_matches(self, tmp_path: Path) -> None:
        """`defaults@N.toml` is a checked-in copy of a live document, and the fingerprint diff
        cannot see it drift — an edited value inside an unchanged path moves the file, not the
        path set. Left unchecked, two copies of the same document quietly disagree.
        """
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        write_defaults_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1, document='label = "stale"\n')
        issues = check_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.FINGERPRINT_DRIFTED]
        assert "defaults@1.toml" in issues[0].message

    def test_a_bump_whose_snapshot_has_not_been_taken_says_so(self, tmp_path: Path) -> None:
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_rename_entry())
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.SNAPSHOT_PENDING]

    def test_a_gap_in_the_golden_chain_is_reported_not_papered_over(self, tmp_path: Path) -> None:
        """Only the head link may fall back to the live fingerprint.

        Substituting it for a missing golden lower down would compare an old entry against today's
        models and blame the entry for the mismatch.
        """
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_rename_entry())
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.GOLDEN_MISSING]
        assert "schema version 1" in issues[0].message


class TestThePreHistoryClaim:
    def test_a_pre_history_entry_over_an_unmoved_pair_is_green(self, tmp_path: Path) -> None:
        """The whole point of the flag: the change it describes happened before any of this was snapshotted."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_pre_history_entry())
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path) == []

    def test_a_pre_history_entry_hiding_a_real_removal_is_refused(self, tmp_path: Path) -> None:
        """The flag exempts an entry from accounting, so a change with an observable diff must not carry it."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_pre_history_entry())
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRemoved, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRemoved), migration_dir=tmp_path)
        assert CoverageIssueKind.PRE_HISTORY_HAS_A_DIFF in _kinds(issues)
        assert "label" in "".join(issue.message for issue in issues)

    def test_a_pre_history_entry_beside_an_addition_stays_green(self, tmp_path: Path) -> None:
        """Additions are absorbed by the defaults layer, so they are nobody's accounting — the flag's included."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_pre_history_entry())
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOneWithBothNames, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaOneWithBothNames), migration_dir=tmp_path) == []


class TestEntryAccounting:
    def test_a_correct_rename_entry_is_green(self, tmp_path: Path) -> None:
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_rename_entry())
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path) == []

    def test_a_misspelled_destination_is_caught(self, tmp_path: Path) -> None:
        """Without the cross-check this passes coverage *and* convergence, then migrates every
        user file to a key `extra="forbid"` rejects, with the tool reporting success.
        """
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_rename_entry(new_key="titel"))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.UNACCOUNTED_PATH]
        assert "titel" in issues[0].message

    def test_a_removal_with_no_operation_accounting_for_it_is_caught(self, tmp_path: Path) -> None:
        entry = f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "unsafe"
title             = "Drop label"
description       = "The key is gone, and this entry forgot to say so."
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRemoved, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRemoved), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.UNACCOUNTED_PATH]
        assert "label" in issues[0].message

    def test_over_deletion_is_caught(self, tmp_path: Path) -> None:
        """An entry that deletes a path the new schema still has would destroy live configuration."""
        entry = f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "safe"
title             = "Drop too much"
description       = "Deletes tier as well, which schema 2 still has."

[[migration.ops]]
kind       = "delete_key"
table_path = []
key        = "label"

[[migration.ops]]
kind       = "delete_key"
table_path = []
key        = "tier"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRemoved, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRemoved), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.OVER_DELETION]
        assert "tier" in issues[0].message

    def test_an_operation_whose_source_never_existed_is_caught(self, tmp_path: Path) -> None:
        """A dead operation is silent forever: it skips on every file and reports success."""
        entry = f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "safe"
title             = "Rename a key that was never there"
description       = "A typo in the source name."

[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "lable"
new_key    = "title"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path)
        assert CoverageIssueKind.DEAD_OP in _kinds(issues)
        assert "lable" in issues[0].message

    def test_a_delete_table_aimed_at_a_key_is_dead(self, tmp_path: Path) -> None:
        """The applier deletes a table only where the path *is* a table; on a key it skips forever.

        The walk has to say the same, or an entry that never fires passes the gate — and the
        key it meant to remove is then reported unaccounted for, which is exactly right.
        """
        entry = f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "safe"
title             = "Drop label with the wrong operation"
description       = "label is a key, not a table."

[[migration.ops]]
kind       = "delete_table"
table_path = ["label"]
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRemoved, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRemoved), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.DEAD_OP, CoverageIssueKind.UNACCOUNTED_PATH]
        assert "delete_key" in issues[0].message

    def test_a_safe_rename_onto_a_path_the_old_schema_already_had_is_refused(self, tmp_path: Path) -> None:
        """The applier refuses to clobber an occupied destination, so a file carrying both keys —
        a perfectly valid schema-1 file — would come back CONFLICT on every run. The walk must not
        quietly overwrite what the applier will not.
        """
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_rename_entry())
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOneWithBothNames, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.DESTINATION_OCCUPIED]
        assert "title" in issues[0].message

    def test_an_unsafe_rename_onto_an_occupied_path_is_allowed(self, tmp_path: Path) -> None:
        """An unsafe entry is reported and never applied, so its operations never conflict."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_rename_entry(safety="unsafe"))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOneWithBothNames, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path) == []


class TestEnumAccounting:
    def _entry_with_ops(self, *, safety: str, ops: str) -> str:
        return f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "{safety}"
title             = "Retire the basic tier"
description       = "The spelling changed."
{ops}
"""

    def test_a_removed_member_with_no_remap_is_caught(self, tmp_path: Path) -> None:
        """A `safe` entry needs at least one operation, and no live one exists for this schema
        pair, so the fixture carries a filler `delete_key` on a path that never existed. That is
        a dead operation by construction and is reported as one; the member loss is the finding.
        """
        ops = """
[[migration.ops]]
kind       = "delete_key"
table_path = []
key        = "nothing_relevant"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoEnumMemberGone), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.DEAD_OP, CoverageIssueKind.ENUM_MEMBER_NOT_REMAPPED]
        assert "basic" in issues[1].message

    def test_a_member_lost_by_a_renamed_path_is_still_caught(self, tmp_path: Path) -> None:
        """Enum accounting follows the path through the entry's own renames.

        The old and new fingerprints share no name for this path — `tier` became `level` — so a
        comparison over shared names would never look at it, and a file carrying `basic` would
        be migrated to a key that rejects it.
        """
        ops = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "tier"
new_key    = "level"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoTierRenamedAndMemberGone, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoTierRenamedAndMemberGone), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.ENUM_MEMBER_NOT_REMAPPED]
        assert "basic" in issues[0].message

    def test_a_remap_after_the_rename_accounts_for_the_lost_member(self, tmp_path: Path) -> None:
        """Operations chain: the remap addresses the key by its *new* name, and is attributed to the origin."""
        ops = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "tier"
new_key    = "level"

[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "level"
mapping    = { basic = "standard" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoTierRenamedAndMemberGone, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaTwoTierRenamedAndMemberGone), migration_dir=tmp_path) == []

    def test_a_removed_member_with_a_matching_remap_is_green(self, tmp_path: Path) -> None:
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tier"
mapping    = { basic = "standard" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaTwoEnumMemberGone), migration_dir=tmp_path) == []

    def test_an_unsafe_entry_may_leave_a_removed_member_unremapped(self, tmp_path: Path) -> None:
        """`unsafe` means reported and never applied, so it is allowed to describe what no operation can do."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="unsafe", ops=""))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaTwoEnumMemberGone), migration_dir=tmp_path) == []


class TestTheDefaultsLayerRule:
    def test_a_required_path_with_no_defaults_layer_value_is_refused(self, tmp_path: Path) -> None:
        """The rule that keeps the whole vocabulary structural.

        Writing the value into the user's file instead would convert an inherited value into an
        explicitly set one, pinning it against every future change to that default — a semantic
        edit dressed up as a fix.
        """

        class _NeedsAValue(BaseModel):
            label: str

        packaged = tmp_path / "packaged.toml"
        packaged.write_text("", encoding="utf-8")
        surface = Surface(
            surface_id=SURFACE_ID,
            title="A synthetic surface",
            base_file="synthetic.toml",
            tier_glob="synthetic_*.toml",
            config_model=_NeedsAValue,
            defaults_layer_kind=DefaultsLayerKind.PACKAGED_DOCUMENT,
            packaged_document_path=packaged,
        )
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        issues = check_surface(surface=surface, migration_dir=tmp_path)
        assert CoverageIssueKind.REQUIRED_PATH_WITHOUT_DEFAULT in _kinds(issues)
        assert "give it a default" in issues[0].message

    def test_a_wildcard_path_is_exempt(self, tmp_path: Path) -> None:
        """The keys beneath an open node are the user's, so there is no value to supply."""

        class _OpenNode(BaseModel):
            deck: dict[str, str] = {}

        packaged = tmp_path / "packaged.toml"
        packaged.write_text("", encoding="utf-8")
        surface = Surface(
            surface_id=SURFACE_ID,
            title="A synthetic surface",
            base_file="synthetic.toml",
            tier_glob="synthetic_*.toml",
            config_model=_OpenNode,
            defaults_layer_kind=DefaultsLayerKind.PACKAGED_DOCUMENT,
            packaged_document_path=packaged,
        )
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        issues = check_surface(surface=surface, migration_dir=tmp_path)
        assert CoverageIssueKind.REQUIRED_PATH_WITHOUT_DEFAULT not in _kinds(issues)


class TestTheLedgerAgreesWithTheRegistry:
    def test_a_ledger_describing_another_file_is_refused(self, tmp_path: Path) -> None:
        """Both halves are hand-written and both are read as truth; a disagreement mis-migrates silently."""
        directory = ledgers_dir(migration_dir=tmp_path)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{SURFACE_ID}.toml").write_text(
            f"""
[surface]
id                           = "{SURFACE_ID}"
title                        = "A synthetic surface"
base_file                    = "elsewhere.toml"
tier_glob                    = "synthetic_*.toml"
current_schema_version       = 1
min_supported_schema_version = 0
""",
            encoding="utf-8",
        )
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.LEDGER_DISAGREES_WITH_REGISTRY]
        assert "elsewhere.toml" in issues[0].message


class TestTheDiff:
    def test_a_renamed_key_reads_as_one_removal_and_one_addition(self) -> None:
        """The diff is deliberately naive about renames — the ledger entry is what interprets it."""
        surface = _surface(config_model=_SchemaOne)
        before = compute_fingerprint(
            surface_id=SURFACE_ID, schema_version=1, config_model=_SchemaOne, defaults_document=surface.read_defaults_document()
        )
        renamed = _surface(config_model=_SchemaTwoRenamed)
        after = compute_fingerprint(
            surface_id=SURFACE_ID, schema_version=2, config_model=_SchemaTwoRenamed, defaults_document=renamed.read_defaults_document()
        )
        diff = diff_fingerprints(before=before, after=after)
        assert diff.removed_paths == ["label"]
        assert diff.added_paths == ["title"]
        assert diff.has_removals is True
