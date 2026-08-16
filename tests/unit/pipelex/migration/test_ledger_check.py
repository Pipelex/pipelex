"""Unit tests for the ledger check — what an entry may say, and whether replaying it is harmless.

Every test here points the check at a **synthetic** surface with a fixture ledger and a fixture
golden chain in a temporary directory, for the reason the whole registry is an injected parameter:
wire the real configuration models in and every legitimate configuration change turns this suite
red alongside the gate, which is how a gate goes permanently green while catching nothing. The real
surfaces get one smoke test, in `test_real_surfaces.py`.

The shape of each test is the same: describe the schema versions as synthetic models, snapshot the
chain the check will read, hand it a ledger entry, and assert which guarantee broke.
"""

from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from pipelex.migration.exceptions import MigrationLedgerError
from pipelex.migration.fingerprint import compute_fingerprint
from pipelex.migration.goldens import write_fingerprint_golden
from pipelex.migration.ledger import ledgers_dir
from pipelex.migration.ledger_check import LedgerIssue, LedgerIssueKind, check_ledger
from pipelex.migration.surfaces import DefaultsLayerKind, Surface

SURFACE_ID = "synthetic-config"


class _Tier(StrEnum):
    BASIC = "basic"
    PREMIUM = "premium"


class _TierWithoutBasic(StrEnum):
    PREMIUM = "premium"
    STANDARD = "standard"


class _DeckEntry(BaseModel):
    old_name: str = "a"


class _DeckEntryRenamed(BaseModel):
    new_name: str = "a"


class _Settings(BaseModel):
    """A plain nested table — deliberately not an open mapping, so `*` has no business here."""

    retries: int = 3


class _SchemaOne(BaseModel):
    """The starting shape: two keys, one of them enumerated, plus a table and an open mapping."""

    label: str = "hello"
    tier: _Tier = _Tier.BASIC
    settings: _Settings = Field(default_factory=_Settings)
    deck: dict[str, _DeckEntry] = Field(default_factory=dict[str, _DeckEntry])


class _SchemaTwoRenamed(BaseModel):
    """`label` renamed to `title`."""

    title: str = "hello"
    tier: _Tier = _Tier.BASIC
    settings: _Settings = Field(default_factory=_Settings)
    deck: dict[str, _DeckEntry] = Field(default_factory=dict[str, _DeckEntry])


class _SchemaTwoDeckFieldRenamed(BaseModel):
    """A field renamed inside every entry of the open mapping."""

    label: str = "hello"
    tier: _Tier = _Tier.BASIC
    settings: _Settings = Field(default_factory=_Settings)
    deck: dict[str, _DeckEntryRenamed] = Field(default_factory=dict[str, _DeckEntryRenamed])


class _SchemaOneWithLevels(BaseModel):
    """A mapping from the user's own keys to an enumerated value — where `key = "*"` is the only reach."""

    levels: dict[str, _Tier] = Field(default_factory=dict[str, _Tier])


class _SchemaTwoLevelMemberGone(BaseModel):
    levels: dict[str, _TierWithoutBasic] = Field(default_factory=dict[str, _TierWithoutBasic])


class _SchemaTwoEnumMemberGone(BaseModel):
    """`basic` is no longer a legal spelling of `tier`."""

    label: str = "hello"
    tier: _TierWithoutBasic = _TierWithoutBasic.PREMIUM
    settings: _Settings = Field(default_factory=_Settings)
    deck: dict[str, _DeckEntry] = Field(default_factory=dict[str, _DeckEntry])


class _SchemaTwoLabelGone(BaseModel):
    """`label` dropped outright."""

    tier: _Tier = _Tier.BASIC
    settings: _Settings = Field(default_factory=_Settings)
    deck: dict[str, _DeckEntry] = Field(default_factory=dict[str, _DeckEntry])


class _TierWithBasicBack(StrEnum):
    BASIC = "basic"
    PREMIUM = "premium"
    STANDARD = "standard"


class _SchemaThreeBasicBack(BaseModel):
    """`basic` is a legal spelling of `tier` again — the reuse of a retired spelling — and `label` is renamed."""

    title: str = "hello"
    tier: _TierWithBasicBack = _TierWithBasicBack.STANDARD
    settings: _Settings = Field(default_factory=_Settings)
    deck: dict[str, _DeckEntry] = Field(default_factory=dict[str, _DeckEntry])


class _SchemaThreeStaysRetired(BaseModel):
    """Schema three keeps `basic` retired; only `label` is renamed."""

    title: str = "hello"
    tier: _TierWithoutBasic = _TierWithoutBasic.STANDARD
    settings: _Settings = Field(default_factory=_Settings)
    deck: dict[str, _DeckEntry] = Field(default_factory=dict[str, _DeckEntry])


class _SchemaThreeLabelBack(BaseModel):
    """`label` is back — the reuse of a retired name — and `tier` is renamed to `level`."""

    label: str = "hello"
    level: _Tier = _Tier.BASIC
    settings: _Settings = Field(default_factory=_Settings)
    deck: dict[str, _DeckEntry] = Field(default_factory=dict[str, _DeckEntry])


def _surface(
    *,
    config_model: type[BaseModel],
    packaged_document_path: Path | None = None,
    kit_template_path: Path | None = None,
) -> Surface:
    defaults_layer_kind = DefaultsLayerKind.PACKAGED_DOCUMENT if packaged_document_path is not None else DefaultsLayerKind.MODEL_DEFAULTS
    return Surface(
        surface_id=SURFACE_ID,
        title="A synthetic surface",
        base_file="synthetic.toml",
        tier_glob="synthetic_*.toml",
        config_model=config_model,
        defaults_layer_kind=defaults_layer_kind,
        packaged_document_path=packaged_document_path,
        kit_template_path=kit_template_path,
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


def _entry(*, ops: str, to_schema_version: int = 2, safety: str = "safe", pre_history: str = "") -> str:
    return f"""
[[migration]]
id                = "{SURFACE_ID}@{to_schema_version}"
to_schema_version = {to_schema_version}
introduced_in     = "0.46.0"
breaking          = true
safety            = "{safety}"
title             = "Reshape the synthetic surface"
description       = "The surface changed shape."
{pre_history}
{ops}
"""


_RENAME_LABEL_TO_TITLE = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "label"
new_key    = "title"
"""


_DELETE_LEGACY_MODE = """
[[migration.ops]]
kind       = "delete_key"
table_path = []
key        = "legacy_mode"
"""


def _pre_history_entry(*, ops: str, declared: str = 'declared_removed_paths = ["legacy_mode"]') -> str:
    """An entry for material that predates the chain: no fingerprint records `legacy_mode` at all."""
    return _entry(ops=f"{declared}\n{ops}", pre_history="pre_history = true")


def _kinds(issues: list[LedgerIssue]) -> list[LedgerIssueKind]:
    return [issue.kind for issue in issues]


class TestTheLedgerCheck:
    def test_an_empty_ledger_at_the_initial_version_is_green(self, tmp_path: Path) -> None:
        """The overwhelmingly common state: a surface that has never changed shape."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        assert check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path) == []

    def test_a_correct_rename_entry_is_green(self, tmp_path: Path) -> None:
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=_RENAME_LABEL_TO_TITLE))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        assert check_ledger(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path) == []

    def test_a_missing_link_is_named_rather_than_papered_over(self, tmp_path: Path) -> None:
        """An entry checked against a shape nobody snapshotted would be blamed for the gap."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=_RENAME_LABEL_TO_TITLE))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        issues = check_ledger(surface=_surface(config_model=_SchemaTwoRenamed), migration_dir=tmp_path)
        assert _kinds(issues) == [LedgerIssueKind.CHAIN_INCOMPLETE]
        assert "make umig" in issues[0].message

    def test_an_operation_on_material_no_version_removed_is_refused(self, tmp_path: Path) -> None:
        """The premise of always-replay: an operation may only act on what a schema version retired.

        Here the shape does not change at all, so `label` is still live — and an operation that
        renames it would fire on every valid current file, forever.
        """
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=_RENAME_LABEL_TO_TITLE))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert LedgerIssueKind.OP_ACTS_ON_LIVE_MATERIAL in _kinds(issues)

    def test_an_operation_naming_a_key_beneath_an_open_node_is_refused(self, tmp_path: Path) -> None:
        """The keys under an open mapping are the user's, so no schema change can remove one."""
        ops = """
[[migration.ops]]
kind       = "delete_key"
table_path = ["deck"]
key        = "some_model_the_user_chose"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert _kinds(issues) == [LedgerIssueKind.CONCRETE_KEY_UNDER_OPEN_NODE]
        assert "some_model_the_user_chose" in issues[0].message

    def test_a_wildcard_anywhere_but_an_open_node_is_refused(self, tmp_path: Path) -> None:
        ops = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = ["settings", "*"]
key        = "retries"
new_key    = "attempts"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert _kinds(issues) == [LedgerIssueKind.WILDCARD_NOT_AT_OPEN_NODE]
        assert "'settings'" in issues[0].message

    def test_a_wildcard_at_an_open_node_is_exactly_what_it_is_for(self, tmp_path: Path) -> None:
        """A field renamed inside every entry of an open mapping is an ordinary safe operation."""
        ops = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = ["deck", "*"]
key        = "old_name"
new_key    = "new_name"
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoDeckFieldRenamed, schema_version=2)
        assert check_ledger(surface=_surface(config_model=_SchemaTwoDeckFieldRenamed), migration_dir=tmp_path) == []

    def test_a_wildcard_key_remap_beneath_an_open_node_is_legal_and_checked_like_any_other(self, tmp_path: Path) -> None:
        """`key = "*"` addresses the wildcard record, so the remap legality rule reads its member set.

        The keys under `levels` are the user's, so no fixed key reaches the values; the wildcard
        record is where the enumerated members live, and it is exactly what the rule is checked
        against — the operation is neither exempt nor unreachable.
        """
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = ["levels"]
key        = "*"
mapping    = { basic = "standard" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOneWithLevels, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoLevelMemberGone, schema_version=2)
        assert check_ledger(surface=_surface(config_model=_SchemaTwoLevelMemberGone), migration_dir=tmp_path) == []

    def test_a_wildcard_key_remap_that_would_rewrite_a_still_legal_value_is_refused(self, tmp_path: Path) -> None:
        """Wildcard or not, a `safe` remap must be provably unable to fire on a current file."""
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = ["levels"]
key        = "*"
mapping    = { premium = "standard" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOneWithLevels, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoLevelMemberGone, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaTwoLevelMemberGone), migration_dir=tmp_path)
        assert LedgerIssueKind.ILLEGAL_REMAP in _kinds(issues)

    def test_a_safe_remap_of_a_value_that_is_still_legal_is_refused(self, tmp_path: Path) -> None:
        """The remap legality rule, and the reason replay neutrality holds.

        `premium` is still a legal tier at schema 2, so a user who chose it deliberately would
        have it rewritten on every run — and replay over a current-valid file would not be a no-op.
        """
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tier"
mapping    = { basic = "standard", premium = "standard" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaTwoEnumMemberGone), migration_dir=tmp_path)
        assert LedgerIssueKind.ILLEGAL_REMAP in _kinds(issues)
        assert "premium" in " ".join(issue.message for issue in issues)

    def test_a_remap_to_a_spelling_the_new_schema_rejects_is_refused(self, tmp_path: Path) -> None:
        """The value-side twin of the misspelled rename destination.

        Rewriting to a spelling the new schema does not accept migrates every file to something
        the model rejects, with the tool reporting success.
        """
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tier"
mapping    = { basic = "standrad" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaTwoEnumMemberGone), migration_dir=tmp_path)
        assert LedgerIssueKind.ILLEGAL_REMAP in _kinds(issues)
        assert "standrad" in " ".join(issue.message for issue in issues)

    def test_a_safe_remap_of_a_free_string_is_refused(self, tmp_path: Path) -> None:
        """Staleness can never be proven from the schema when any string is legal."""
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "label"
mapping    = { hello = "hi" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert LedgerIssueKind.ILLEGAL_REMAP in _kinds(issues)

    def test_an_unsafe_entry_may_remap_a_value_that_is_still_legal(self, tmp_path: Path) -> None:
        """`unsafe` is exactly the answer to a change the applier cannot make on its own."""
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tier"
mapping    = { premium = "standard" }
"""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=ops, safety="unsafe"))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaTwoEnumMemberGone), migration_dir=tmp_path)
        assert LedgerIssueKind.ILLEGAL_REMAP not in _kinds(issues)

    def test_a_retired_name_that_comes_back_is_refused(self, tmp_path: Path) -> None:
        """And the reuse is not academic: the operation that retired the name starts firing again."""
        delete_label = """
[[migration.ops]]
kind       = "delete_key"
table_path = []
key        = "label"
"""
        rename_tier = """
[[migration.ops]]
kind       = "rename_table_key"
table_path = []
key        = "tier"
new_key    = "level"
"""
        entries = _entry(ops=delete_label, to_schema_version=2) + _entry(ops=rename_tier, to_schema_version=3)
        _write_ledger(migration_dir=tmp_path, current_schema_version=3, entries=entries)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoLabelGone, schema_version=2)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaThreeLabelBack, schema_version=3)
        issues = check_ledger(surface=_surface(config_model=_SchemaThreeLabelBack), migration_dir=tmp_path)
        assert LedgerIssueKind.RESERVED_PATH_REUSED in _kinds(issues)
        assert LedgerIssueKind.CONVERGENCE_BROKEN in _kinds(issues)

    def test_a_retired_spelling_that_comes_back_is_refused(self, tmp_path: Path) -> None:
        """The value-side twin of the retired name: a remapped-away spelling accepted again would be
        rewritten on every run of every file that still carries it.
        """
        remap_basic = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tier"
mapping    = { basic = "standard" }
"""
        entries = _entry(ops=remap_basic, to_schema_version=2) + _entry(ops=_RENAME_LABEL_TO_TITLE, to_schema_version=3)
        _write_ledger(migration_dir=tmp_path, current_schema_version=3, entries=entries)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaThreeBasicBack, schema_version=3)
        issues = check_ledger(surface=_surface(config_model=_SchemaThreeBasicBack), migration_dir=tmp_path)
        assert LedgerIssueKind.RESERVED_VALUE_REUSED in _kinds(issues)
        assert "'basic'" in " ".join(issue.message for issue in issues)

    def test_a_spelling_that_stays_retired_is_not_an_issue(self, tmp_path: Path) -> None:
        remap_basic = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tier"
mapping    = { basic = "standard" }
"""
        entries = _entry(ops=remap_basic, to_schema_version=2) + _entry(ops=_RENAME_LABEL_TO_TITLE, to_schema_version=3)
        _write_ledger(migration_dir=tmp_path, current_schema_version=3, entries=entries)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoEnumMemberGone, schema_version=2)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaThreeStaysRetired, schema_version=3)
        issues = check_ledger(surface=_surface(config_model=_SchemaThreeStaysRetired), migration_dir=tmp_path)
        assert LedgerIssueKind.RESERVED_VALUE_REUSED not in _kinds(issues)

    def test_a_reference_document_the_ledger_still_changes_is_refused(self, tmp_path: Path) -> None:
        """A packaged document left behind by its own model would be migrated on every user's run."""
        packaged = tmp_path / "packaged.toml"
        packaged.write_text('label = "hello"\ntier = "basic"\n', encoding="utf-8")
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=_RENAME_LABEL_TO_TITLE))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        surface = _surface(config_model=_SchemaTwoRenamed, packaged_document_path=packaged)
        issues = check_ledger(surface=surface, migration_dir=tmp_path)
        assert _kinds(issues) == [LedgerIssueKind.CONVERGENCE_BROKEN]
        assert "reference document" in issues[0].message

    def test_the_sparse_kit_template_is_a_witness_of_its_own(self, tmp_path: Path) -> None:
        """The two witnesses are different shapes on purpose: one has every key set, one almost none."""
        packaged = tmp_path / "packaged.toml"
        packaged.write_text('title = "hello"\ntier = "basic"\n', encoding="utf-8")
        template = tmp_path / "template.toml"
        template.write_text('label = "hello"\n', encoding="utf-8")
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_entry(ops=_RENAME_LABEL_TO_TITLE))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaTwoRenamed, schema_version=2)
        surface = _surface(config_model=_SchemaTwoRenamed, packaged_document_path=packaged, kit_template_path=template)
        issues = check_ledger(surface=surface, migration_dir=tmp_path)
        assert _kinds(issues) == [LedgerIssueKind.CONVERGENCE_BROKEN]
        assert "kit template" in issues[0].message

    def test_a_pre_history_entry_addressing_only_what_it_declares_is_green(self, tmp_path: Path) -> None:
        """The shape the flag is for: material that predates the chain, so no fingerprint shows it going away."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_pre_history_entry(ops=_DELETE_LEGACY_MODE))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=2)
        assert check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path) == []

    def test_a_pre_history_entry_declaring_a_path_the_chain_records_is_refused(self, tmp_path: Path) -> None:
        """Otherwise the flag is a way to opt out of accounting for a change that has a diff."""
        _write_ledger(
            migration_dir=tmp_path,
            current_schema_version=2,
            entries=_pre_history_entry(ops=_DELETE_LEGACY_MODE, declared='declared_removed_paths = ["legacy_mode", "label"]'),
        )
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert _kinds(issues) == [LedgerIssueKind.PRE_HISTORY_PATH_IS_RECORDED]
        assert "'label'" in issues[0].message

    def test_a_pre_history_operation_outside_the_declaration_is_refused(self, tmp_path: Path) -> None:
        """The declaration is the entry's only record of what it may address, so it bounds the operations too."""
        ops = (
            _DELETE_LEGACY_MODE
            + """
[[migration.ops]]
kind       = "delete_key"
table_path = []
key        = "label"
"""
        )
        _write_ledger(migration_dir=tmp_path, current_schema_version=2, entries=_pre_history_entry(ops=ops))
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=2)
        issues = check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
        assert LedgerIssueKind.OP_ACTS_ON_LIVE_MATERIAL in _kinds(issues)

    @pytest.mark.parametrize(
        ("current_schema_version", "entries"),
        [
            pytest.param(2, "", id="a version with no entry to produce it"),
            pytest.param(3, _entry(ops=_RENAME_LABEL_TO_TITLE, to_schema_version=3), id="a gap in the entry numbering"),
        ],
    )
    def test_a_ledger_that_does_not_hold_together_is_refused_when_it_is_read(
        self,
        tmp_path: Path,
        current_schema_version: int,
        entries: str,
    ) -> None:
        """Contiguity and matching ids are enforced at parse time — the earliest place they can be."""
        _write_ledger(migration_dir=tmp_path, current_schema_version=current_schema_version, entries=entries)
        _snapshot(migration_dir=tmp_path, config_model=_SchemaOne, schema_version=1)
        with pytest.raises(MigrationLedgerError):
            check_ledger(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)
