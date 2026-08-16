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
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pipelex.migration.coverage import CoverageIssue, CoverageIssueKind, check_surface, diff_fingerprints
from pipelex.migration.fingerprint import compute_fingerprint
from pipelex.migration.goldens import write_defaults_golden, write_fingerprint_golden
from pipelex.migration.ledger import ledgers_dir
from pipelex.migration.surfaces import DefaultsLayerKind, Surface
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

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


class _SchemaTwoRenamedWithMemberGone(BaseModel):
    """`label` renamed *and* a spelling of `tier` retired — an entry that is about the rename only."""

    title: str = "hello"
    tier: _TierWithoutBasic = _TierWithoutBasic.PREMIUM


class _SchemaTwoTierRenamedAndMemberGone(BaseModel):
    """`tier` renamed to `level` *and* `basic` dropped, in the same schema version."""

    label: str = "hello"
    level: _TierWithoutBasic = _TierWithoutBasic.PREMIUM


class _Section(BaseModel):
    """A table with two keys, one of them optional with no value in any reference document."""

    limit: int | None = None
    name: str = "x"


class _SchemaOneWithSection(BaseModel):
    label: str = "hello"
    section: _Section = Field(default_factory=_Section)


class _SchemaTwoSectionRenamed(BaseModel):
    """`section` renamed to `area`, both children kept."""

    label: str = "hello"
    area: _Section = Field(default_factory=_Section)


class _BoundedOne(BaseModel):
    """A shape with a bounded number beside an ordinary key — the starting point for narrowings."""

    label: str = "hello"
    retries: int = Field(default=3, ge=1)


class _BoundedTightened(BaseModel):
    """The bound moved up. Every path survives; a file saying `retries = 2` stops validating."""

    label: str = "hello"
    retries: int = Field(default=3, ge=2)


class _BoundedRelaxed(BaseModel):
    """The bound is gone. Every file that validated before still does."""

    label: str = "hello"
    retries: int = 3


class _BoundedTightenedAndRenamed(BaseModel):
    """A tightened bound riding along with a rename, the way a real schema version mixes changes."""

    title: str = "hello"
    retries: int = Field(default=3, ge=2)


class _MixedItemList(BaseModel):
    """A list whose items may be numbers or strings, beside a key the entry has an operation for."""

    gone: str = "x"
    items: list[int | str] = Field(default_factory=list[int | str])


class _IntegerItemList(BaseModel):
    """The items narrowed to numbers. No operation can reach inside the list to repair one."""

    items: list[int] = Field(default_factory=empty_list_factory_of(int))


class _BoundedOrAuto(BaseModel):
    """A bounded number that may also be spelled `auto` — the `int | literal` shape real surfaces carry."""

    label: str = "hello"
    retries: Annotated[int, Field(ge=1)] | Literal["auto", "unbounded"] = 3


class _BoundedTightenedOrUnbounded(BaseModel):
    """`auto` is gone *and* the bound moved up: a remap answers for the first, nothing but `unsafe` for the second."""

    label: str = "hello"
    retries: Annotated[int, Field(ge=8)] | Literal["unbounded"] = 8


class _SpelledOnly(BaseModel):
    """The number is gone altogether: only one spelling survives, and `retries = 4` is out of domain."""

    label: str = "hello"
    retries: Literal["unbounded"] = "unbounded"


class _FreeStringTier(BaseModel):
    """`tier` accepts any string."""

    tier: str = "basic"


class _EnumeratedTier(BaseModel):
    """`tier` accepts two spellings and nothing else."""

    tier: _Tier = _Tier.BASIC


class _EnumeratedTierList(BaseModel):
    """`tiers` accepts a list of the two spellings — the shape a real surface already has."""

    tiers: list[_Tier] = Field(default_factory=empty_list_factory_of(_Tier))


class _FreeStringTierList(BaseModel):
    """The same list, relaxed to accept any string."""

    tiers: list[str] = Field(default_factory=list)


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
        """An entry that is genuinely about something else still owes the version's removals."""
        entry = f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "unsafe"
title             = "Drop label"
description       = "The key is gone, and this entry forgot to say so."
declared_narrowed_paths = ["tier"]
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

    def test_an_over_deletion_beneath_a_renamed_table_is_caught(self, tmp_path: Path) -> None:
        """The deleted child is `section.limit` in the old spelling and `area.limit` in the new, so a
        comparison by current spelling never lines the two up. Compared by origin, the entry removes a
        path the new schema still has — and the convergence witness cannot see it either, because
        the child is optional and no reference document carries it.
        """
        entry = f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "safe"
title             = "Rename the section, and drop too much beneath it"
description       = "Deletes area.limit as well, which schema 2 still has."

[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "section"
new_key    = "area"

[[migration.ops]]
kind       = "delete_key"
table_path = ["area"]
key        = "limit"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOneWithSection, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoSectionRenamed, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoSectionRenamed), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.OVER_DELETION]
        assert "'section.limit'" in issues[0].message
        assert "'area.limit'" in issues[0].message

    def test_a_rename_that_keeps_every_child_is_green(self, tmp_path: Path) -> None:
        entry = f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "safe"
title             = "Rename the section"
description       = "Nothing beneath it changes."

[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "section"
new_key    = "area"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOneWithSection, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoSectionRenamed, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaTwoSectionRenamed), migration_dir=tmp_path) == []

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
    def _entry_with_ops(self, *, safety: str, ops: str, declared_narrowed_paths: str = "") -> str:
        return f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "{safety}"
title             = "Retire the basic tier"
description       = "The spelling changed."
{declared_narrowed_paths}
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

    def test_an_unsafe_entry_that_declares_the_path_may_leave_a_removed_member_unremapped(self, tmp_path: Path) -> None:
        """`unsafe` means reported and never applied, so it is allowed to describe what no operation can do."""
        entry = self._entry_with_ops(safety="unsafe", ops="", declared_narrowed_paths='declared_narrowed_paths = ["tier"]')
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        assert check_surface(surface=_surface(config_model=_SchemaTwoEnumMemberGone), migration_dir=tmp_path) == []

    def test_an_unsafe_entry_that_names_no_path_does_not_account_for_the_lost_member(self, tmp_path: Path) -> None:
        """R9, on the enum half: the word `unsafe` satisfies a reader and reaches no user.

        The entry has an operation, so it is not the op-free shape the parser refuses — and the
        operation is about something else entirely, so rehearsing it says nothing to the user
        whose `tier = "basic"` the new schema rejects.
        """
        ops = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "label"
new_key    = "title"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="unsafe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamedWithMemberGone, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SchemaTwoRenamedWithMemberGone), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.ENUM_MEMBER_NOT_REMAPPED]
        assert "declared_narrowed_paths" in issues[0].message

    def test_a_member_lost_inside_a_list_cannot_be_remapped_and_the_gate_says_so(self, tmp_path: Path) -> None:
        """A remap rewrites a string value, and the value here is a list.

        Crediting the remap would leave a green gate over a file that stops validating: the
        operation is a guarded skip on every run. `unsafe` is the only remedy, and the message
        has to say that rather than offer a remap the author would write and never see fire.
        """
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tiers"
mapping    = { basic = "standard" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_ListOfTiers, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_ListOfTiersMemberGone, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_ListOfTiersMemberGone), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.ENUM_MEMBER_NOT_REMAPPED]
        assert "must be marked unsafe" in issues[0].message
        assert "remap_value" not in issues[0].message

    def test_a_member_lost_beneath_an_open_mapping_is_remapped_through_the_wildcard_key(self, tmp_path: Path) -> None:
        """The keys are the user's, so `key = "*"` is the only operation that reaches the values."""
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = ["levels"]
key        = "*"
mapping    = { basic = "standard" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_MappingOfTiers, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_MappingOfTiersMemberGone, schema_version=2)
        assert check_surface(surface=_surface(config_model=_MappingOfTiersMemberGone), migration_dir=tmp_path) == []


class _ListOfTiers(BaseModel):
    """An enumerated type inside a list: the members live on the list's own path, with no child record."""

    tiers: list[_Tier] = Field(default_factory=lambda: [_Tier.BASIC])


class _ListOfTiersMemberGone(BaseModel):
    tiers: list[_TierWithoutBasic] = Field(default_factory=lambda: [_TierWithoutBasic.STANDARD])


class _MappingOfTiers(BaseModel):
    """An enumerated type beneath an open mapping: the members live on the `*` record."""

    levels: dict[str, _Tier] = Field(default_factory=lambda: {"one": _Tier.BASIC})


class _MappingOfTiersMemberGone(BaseModel):
    levels: dict[str, _TierWithoutBasic] = Field(default_factory=lambda: {"one": _TierWithoutBasic.STANDARD})


class TestValueDomainNarrowing:
    """The change that keeps every path and every spelling, and still breaks a user's file.

    Without the direction split these all read as additive — nothing was removed — so the gate
    would answer "regenerate the golden", demand no bump and no entry, and the next boot would
    reject a file that was valid the day before with a green gate behind it.
    """

    def _entry_with_ops(self, *, safety: str, ops: str, declared_narrowed_paths: str = "") -> str:
        return f"""
[[migration]]
id                = "{SURFACE_ID}@2"
to_schema_version = 2
introduced_in     = "0.46.0"
breaking          = true
safety            = "{safety}"
title             = "Narrow what a value may be"
description       = "The domain shrank."
{declared_narrowed_paths}
{ops}
"""

    def test_a_tightened_bound_without_a_bump_is_refused(self, tmp_path: Path) -> None:
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOne, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_BoundedTightened), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.REMOVAL_NEEDS_A_BUMP]
        assert "lower bound tightened from ge=1 to ge=2" in issues[0].message

    def test_a_free_string_becoming_enumerated_without_a_bump_is_refused(self, tmp_path: Path) -> None:
        """Every spelling the file could carry is now checked against a closed set it may fail."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_FreeStringTier, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_EnumeratedTier), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.REMOVAL_NEEDS_A_BUMP]
        assert "its type went from 'str' to 'enum'" in issues[0].message

    def test_a_relaxed_bound_asks_only_for_a_regeneration(self, tmp_path: Path) -> None:
        """The other direction has to stay cheap, or the gate is one an author learns to fight."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOne, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_BoundedRelaxed), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.FINGERPRINT_DRIFTED]

    def test_an_enumerated_path_relaxed_into_a_free_string_asks_only_for_a_regeneration(self, tmp_path: Path) -> None:
        """The member set empties, and a raw set difference would call that the loss of every spelling.

        This is the widening most likely to be attempted in practice, and demanding a bump and a
        remap for each spelling would be the gate at its most obviously wrong.
        """
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_EnumeratedTier, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_FreeStringTier), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.FINGERPRINT_DRIFTED]

    def test_an_enumerated_list_relaxed_into_free_strings_asks_only_for_a_regeneration(self, tmp_path: Path) -> None:
        """The same widening one container down, which a real surface already carries as `list[AgentTarget]`.

        The type half reads a container structurally; the member half read its exemption only at the
        top level, so this change reported no narrowing and every spelling lost at once. The remedy
        the gate then named — bump the version and mark the entry `unsafe`, because no operation can
        rewrite a value inside a list — would be reported to every user, at every boot, forever, for
        a change that invalidates nothing.
        """
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_EnumeratedTierList, schema_version=1)
        issues = check_surface(surface=_surface(config_model=_FreeStringTierList), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.FINGERPRINT_DRIFTED]

    def test_a_bumped_entry_that_does_not_account_for_the_narrowing_is_refused(self, tmp_path: Path) -> None:
        """The entry explains the rename it made and says nothing about the bound it moved."""
        ops = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "label"
new_key    = "title"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedTightenedAndRenamed, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_BoundedTightenedAndRenamed), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.VALUE_DOMAIN_NARROWED]
        assert "'retries'" in issues[0].message

    def test_a_narrowed_container_is_sent_to_unsafe_rather_than_to_a_remap_it_cannot_write(self, tmp_path: Path) -> None:
        """The remedy a gate names has to be one the other gates accept.

        A `remap_value` rewrites a string value, so it never reaches an item inside a list — and
        `make check-ledger` refuses one on a path that is not enumerated, as illegal. Offering it
        here sent the author to write an operation one gate demanded and the other rejected.
        """
        ops = """
[[migration.ops]]
kind       = "delete_key"
table_path = []
key        = "gone"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_MixedItemList, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_IntegerItemList, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_IntegerItemList), migration_dir=tmp_path)
        narrowings = [issue for issue in issues if issue.kind is CoverageIssueKind.VALUE_DOMAIN_NARROWED]
        assert len(narrowings) == 1
        assert "must be marked unsafe" in narrowings[0].message
        assert "remap_value" not in narrowings[0].message

    def test_a_remap_on_the_narrowed_path_accounts_for_it(self, tmp_path: Path) -> None:
        """The remedy that repairs the file rather than only warning about it, where it applies."""
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tier"
mapping    = { entry = "basic" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_FreeStringTier, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_EnumeratedTier, schema_version=2)
        assert check_surface(surface=_surface(config_model=_EnumeratedTier), migration_dir=tmp_path) == []

    def test_a_remap_on_a_path_does_not_answer_for_a_bound_tightened_on_that_same_path(self, tmp_path: Path) -> None:
        """A remap rewrites spellings; the number `retries = 4` is not a spelling and no mapping reaches it.

        Without this the remap that retires `auto` would carry the tightened bound into a `safe`
        entry, and a file saying `retries = 4` would fail at boot behind a green gate.
        """
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "retries"
mapping    = { auto = "unbounded" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOrAuto, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedTightenedOrUnbounded, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_BoundedTightenedOrUnbounded), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.VALUE_DOMAIN_NARROWED]
        assert "lower bound tightened from ge=1 to ge=8" in issues[0].message
        assert "its type went from" not in issues[0].message

    def test_a_remap_on_a_path_does_not_answer_for_a_non_string_member_that_path_lost(self, tmp_path: Path) -> None:
        """The other way a remap falls short: `int | literal` becomes `literal`. The remap rewrites the
        spelling it names and never touches the number, so `retries = 4` fails at boot — the type
        half of narrowing must still run for a remapped origin, exempting only what a remap can
        rewrite.
        """
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "retries"
mapping    = { auto = "unbounded" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="safe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOrAuto, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SpelledOnly, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_SpelledOnly), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.VALUE_DOMAIN_NARROWED]
        assert "its type went from 'int | literal' to 'literal'" in issues[0].message

    def test_an_unsafe_entry_that_declares_the_narrowing_leaves_it_unremapped(self, tmp_path: Path) -> None:
        """For a tightened numeric bound this is the only remedy there is: no mapping can enumerate
        the values a bound retires, so the migration is reported to the user and never applied.
        """
        entry = self._entry_with_ops(safety="unsafe", ops="", declared_narrowed_paths='declared_narrowed_paths = ["retries"]')
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedTightened, schema_version=2)
        assert check_surface(surface=_surface(config_model=_BoundedTightened), migration_dir=tmp_path) == []

    def test_an_unsafe_entry_that_declares_nothing_about_its_narrowing_is_refused(self, tmp_path: Path) -> None:
        """R9 — `unsafe` on its own accounts for nothing, because the engine reports it to nobody.

        The word satisfies a reader; the declaration is what the engine can question a user's file
        about. An entry that says `unsafe` and names no path passes this gate while every user
        whose value the new schema refuses is left with a failing boot and no message.
        """
        ops = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "label"
new_key    = "title"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=self._entry_with_ops(safety="unsafe", ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedTightenedAndRenamed, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_BoundedTightenedAndRenamed), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.VALUE_DOMAIN_NARROWED]
        assert "declared_narrowed_paths" in issues[0].message

    def test_an_unsafe_entry_declaring_its_narrowing_beside_a_rename_is_green(self, tmp_path: Path) -> None:
        """The same entry, with the one line that makes it reach the user it is written for."""
        ops = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "label"
new_key    = "title"
"""
        entry = self._entry_with_ops(safety="unsafe", ops=ops, declared_narrowed_paths='declared_narrowed_paths = ["retries"]')
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=entry)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedTightenedAndRenamed, schema_version=2)
        assert check_surface(surface=_surface(config_model=_BoundedTightenedAndRenamed), migration_dir=tmp_path) == []

    def test_a_pre_history_entry_cannot_hide_a_narrowing_either(self, tmp_path: Path) -> None:
        """The flag exempts an entry from accounting, so it must not be a way past this one."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_pre_history_entry())
        _snapshot(migration_dir=tmp_path, config_model=_BoundedOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_BoundedTightened, schema_version=2)
        issues = check_surface(surface=_surface(config_model=_BoundedTightened), migration_dir=tmp_path)
        assert _kinds(issues) == [CoverageIssueKind.PRE_HISTORY_HAS_A_DIFF]
        assert "'retries'" in issues[0].message


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
