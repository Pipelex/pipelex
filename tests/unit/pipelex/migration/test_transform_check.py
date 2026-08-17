"""Unit tests for the transform goldens — does an entry's operations really do what it claims?

Every test here points the check at a **synthetic** surface whose golden chain is written by hand
into a temporary directory, for the reason the whole registry is an injected parameter: wire the
real configuration models in and every legitimate configuration change turns this suite red
alongside the gate, which is how a gate goes permanently green while catching nothing. The real
surfaces get one smoke test, in `test_real_surfaces.py`.

Writing the reference documents by hand rather than snapshotting them from a model is deliberate
too: a golden chain *is* checked-in text, and half of what this check has to tolerate — a comment
edited between versions, a default flipped, a key added to a packaged document — cannot be
expressed by a model at all.
"""

from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.exceptions import MigrationGoldenError
from pipelex.migration.fingerprint import compute_fingerprint
from pipelex.migration.goldens import defaults_golden_path, pre_history_document_path, write_defaults_golden, write_fingerprint_golden
from pipelex.migration.ledger import ledgers_dir
from pipelex.migration.surfaces import DefaultsLayerKind, Surface
from pipelex.migration.transform_check import TransformIssue, TransformIssueKind, check_transform_chain

SURFACE_ID = "synthetic-config"


class _TierAtTwo(StrEnum):
    PREMIUM = "premium"
    STANDARD = "standard"


class _Renamed(BaseModel):
    """Schema 2 of the rename story: `label` is now `title`."""

    model_config = ConfigDict(extra="forbid")

    title: str = "hello"


class _RenamedWithMotto(BaseModel):
    """The same bump, which also added a key — the additive change every honest bump carries."""

    model_config = ConfigDict(extra="forbid")

    title: str = "hello"
    motto: str = "onwards"


class _WithOptional(BaseModel):
    """Schema 2 with an optional destination: legal path, no value any TOML document can carry."""

    model_config = ConfigDict(extra="forbid")

    nickname: str | None = None


class _DeckEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_name: str = "a"


class _Deck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deck: dict[str, _DeckEntry] = Field(default_factory=dict[str, _DeckEntry])


class _Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: int = 1


class _WithSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settings: _Settings = Field(default_factory=_Settings)


class _Tiered(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: _TierAtTwo = _TierAtTwo.PREMIUM


class _Inner(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inner_new: int = 1


class _Shell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shell: _Inner = Field(default_factory=_Inner)


def _surface(*, config_model: type[BaseModel]) -> Surface:
    return Surface(
        surface_id=SURFACE_ID,
        title="A synthetic surface",
        base_file="synthetic.toml",
        tier_glob="synthetic_*.toml",
        config_model=config_model,
        defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
    )


def _write_ledger(*, migration_dir: Path, entries: str, current_schema_version: int = 2) -> None:
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


def _entry(*, ops: str, to_schema_version: int = 2, safety: str = "safe", declared: str = "") -> str:
    return f"""
[[migration]]
id                = "{SURFACE_ID}@{to_schema_version}"
to_schema_version = {to_schema_version}
introduced_in     = "0.46.0"
breaking          = true
safety            = "{safety}"
title             = "Reshape the synthetic surface"
description       = "The surface changed shape."
{declared}
{ops}
"""


def _defaults(*, migration_dir: Path, schema_version: int, document: str) -> None:
    write_defaults_golden(migration_dir=migration_dir, surface_id=SURFACE_ID, schema_version=schema_version, document=document)


def _rename(*, key: str, new_key: str, table_path: str = "[]") -> str:
    return f"""
[[migration.ops]]
kind       = "rename_table_key"
table_path = {table_path}
key        = "{key}"
new_key    = "{new_key}"
"""


def _kinds(issues: list[TransformIssue]) -> list[TransformIssueKind]:
    return [issue.kind for issue in issues]


def _messages(issues: list[TransformIssue]) -> str:
    return " ".join(issue.message for issue in issues)


def _pre_history_entry(*, ops: str) -> str:
    return f"""
[[migration]]
id                     = "{SURFACE_ID}@2"
to_schema_version      = 2
introduced_in          = "0.46.0"
breaking               = true
safety                 = "safe"
title                  = "Carry a shape that predates the chain"
description            = "There was no snapshot on the far side of this one."
pre_history            = true
declared_removed_paths = ["legacy_label"]
{ops}
"""


def _pre_history_document(*, migration_dir: Path, document: str) -> None:
    path = pre_history_document_path(migration_dir=migration_dir, surface_id=SURFACE_ID, schema_version=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")


def _fingerprint(*, migration_dir: Path, config_model: type[BaseModel], schema_version: int) -> None:
    write_fingerprint_golden(
        migration_dir=migration_dir,
        fingerprint=compute_fingerprint(
            surface_id=SURFACE_ID,
            schema_version=schema_version,
            config_model=config_model,
            defaults_document=_surface(config_model=config_model).read_defaults_document(),
        ),
    )


class TestThePreHistoryLink:
    def test_a_pre_history_entry_is_verified_against_its_hand_authored_document(self, tmp_path: Path) -> None:
        """The exception's whole shape: a different starting document, then the same three claims."""
        _write_ledger(migration_dir=tmp_path, entries=_pre_history_entry(ops=_rename(key="legacy_label", new_key="title")))
        _pre_history_document(migration_dir=tmp_path, document='legacy_label = "hello"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\n')
        assert check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path) == []

    def test_a_pre_history_entry_with_no_document_to_start_from_is_refused(self, tmp_path: Path) -> None:
        """Nothing else verifies it, so an absent document is the escape hatch reopening."""
        _write_ledger(migration_dir=tmp_path, entries=_pre_history_entry(ops=_rename(key="legacy_label", new_key="title")))
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\n')
        issues = check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path)
        assert _kinds(issues) == [TransformIssueKind.PRE_HISTORY_DOCUMENT_MISSING]
        assert "before@2.toml" in _messages(issues)

    def test_a_misspelled_destination_is_caught_on_the_pre_history_link_too(self, tmp_path: Path) -> None:
        """The exception changes where the link starts, and nothing about what it proves."""
        _write_ledger(migration_dir=tmp_path, entries=_pre_history_entry(ops=_rename(key="legacy_label", new_key="titel")))
        _pre_history_document(migration_dir=tmp_path, document='legacy_label = "hello"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\n')
        issues = check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path)
        assert TransformIssueKind.DESTINATION_NOT_IN_NEW_SHAPE in _kinds(issues)
        assert "titel" in _messages(issues)


class TestTheTransformGoldens:
    def test_a_destination_the_fingerprint_records_but_the_document_cannot_carry_is_tolerated(self, tmp_path: Path) -> None:
        """An optional key defaulting to `None` is a legal path with no value in any document.

        TOML has no null, so the reference document simply lacks it — and a migration moving a
        user's value onto it creates a path that document does not have. Checking the document
        alone would refuse the one destination the schema most obviously has.
        """
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="nickname")))
        _defaults(migration_dir=tmp_path, schema_version=1, document='label = "hello"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document="")
        _fingerprint(migration_dir=tmp_path, config_model=_WithOptional, schema_version=2)
        assert check_transform_chain(surface=_surface(config_model=_WithOptional), migration_dir=tmp_path) == []

    def test_a_surface_that_has_never_changed_shape_has_no_link_to_check(self, tmp_path: Path) -> None:
        """The overwhelmingly common state, and the one every shipped surface is in today."""
        _write_ledger(migration_dir=tmp_path, entries="", current_schema_version=1)
        _defaults(migration_dir=tmp_path, schema_version=1, document='label = "hello"\n')
        assert check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path) == []

    def test_a_correct_rename_lands_exactly_on_the_new_shape(self, tmp_path: Path) -> None:
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="title")))
        _defaults(migration_dir=tmp_path, schema_version=1, document='label = "hello"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\n')
        assert check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path) == []

    def test_a_misspelled_destination_is_refused(self, tmp_path: Path) -> None:
        """The defect the transform goldens exist for: coverage and convergence both pass it.

        The removed path is accounted for, and over a current document the source is absent so the
        operation skips — and every user file is then migrated to a key the schema rejects, with
        the tool reporting success.
        """
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="titel")))
        _defaults(migration_dir=tmp_path, schema_version=1, document='label = "hello"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\n')
        issues = check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path)
        assert _kinds(issues) == [TransformIssueKind.DESTINATION_NOT_IN_NEW_SHAPE, TransformIssueKind.MIGRATED_DOCUMENT_REJECTED]
        assert "titel" in _messages(issues)

    def test_operations_applied_in_the_wrong_order_are_refused(self, tmp_path: Path) -> None:
        """Renaming the parent first leaves the child operation addressing a table that is gone.

        It skips, silently and forever — the applier cannot tell a dead operation from one whose
        work is already done. What lands is the new parent holding the old child key.
        """
        ops = _rename(key="outer", new_key="shell") + _rename(key="inner_old", new_key="inner_new", table_path='["outer"]')
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=ops))
        _defaults(migration_dir=tmp_path, schema_version=1, document="[outer]\ninner_old = 1\n")
        _defaults(migration_dir=tmp_path, schema_version=2, document="[shell]\ninner_new = 1\n")
        issues = check_transform_chain(surface=_surface(config_model=_Shell), migration_dir=tmp_path)
        assert TransformIssueKind.DESTINATION_NOT_IN_NEW_SHAPE in _kinds(issues)
        assert "shell.inner_old" in _messages(issues)

    def test_over_deletion_is_refused(self, tmp_path: Path) -> None:
        """A `delete_table` one level too high takes material the new shape still has.

        A subset comparison would pass this, which is why the check is not one.
        """
        ops = """
[[migration.ops]]
kind       = "delete_table"
table_path = ["settings"]
"""
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=ops))
        _defaults(migration_dir=tmp_path, schema_version=1, document="[settings]\nretries = 3\nattempts = 1\n")
        _defaults(migration_dir=tmp_path, schema_version=2, document="[settings]\nattempts = 1\n")
        issues = check_transform_chain(surface=_surface(config_model=_WithSettings), migration_dir=tmp_path)
        assert _kinds(issues) == [TransformIssueKind.SURVIVING_PATH_REMOVED]
        assert "'settings'" in issues[0].message

    def test_a_remap_to_a_spelling_the_new_schema_rejects_is_refused(self, tmp_path: Path) -> None:
        """The value-side defect, which moves no path at all — so only the last link can see it.

        Reading the migrated document beneath the current defaults is what a user's boot does, and
        it is the only oracle that stays sound: comparing values against the new reference document
        would go red whenever a default was flipped in the same commit, with no remedy available.
        """
        ops = """
[[migration.ops]]
kind       = "remap_value"
table_path = []
key        = "tier"
mapping    = { basic = "standrad" }
"""
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=ops))
        _defaults(migration_dir=tmp_path, schema_version=1, document='tier = "basic"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='tier = "premium"\n')
        issues = check_transform_chain(surface=_surface(config_model=_Tiered), migration_dir=tmp_path)
        assert _kinds(issues) == [TransformIssueKind.MIGRATED_DOCUMENT_REJECTED]
        assert "standrad" in issues[0].message

    def test_an_operation_that_conflicts_on_the_reference_document_is_refused(self, tmp_path: Path) -> None:
        """The document at the version an entry migrates *from* is the one it must be able to migrate."""
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="title")))
        _defaults(migration_dir=tmp_path, schema_version=1, document='label = "hello"\ntitle = "taken"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "taken"\n')
        issues = check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path)
        assert _kinds(issues) == [TransformIssueKind.TRANSFORM_CONFLICTED]

    def test_a_key_the_new_document_gained_is_tolerated(self, tmp_path: Path) -> None:
        """Every honest bump adds keys in the same commit; a comparator red on that is worthless."""
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="title")))
        _defaults(migration_dir=tmp_path, schema_version=1, document='label = "hello"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\nmotto = "onwards"\n')
        assert check_transform_chain(surface=_surface(config_model=_RenamedWithMotto), migration_dir=tmp_path) == []

    def test_an_edited_comment_and_a_flipped_default_are_tolerated(self, tmp_path: Path) -> None:
        """Neither moves a path, and both are ordinary edits to a document we ship."""
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="title")))
        _defaults(migration_dir=tmp_path, schema_version=1, document='# what to greet with\nlabel = "hello"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='# how to greet\ntitle = "goodbye"\n')
        assert check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path) == []

    def test_an_entry_added_beneath_an_open_mapping_is_tolerated(self, tmp_path: Path) -> None:
        """The keys of an open mapping are user key space, and no fingerprint records one.

        A comparator built on the fingerprint diff would be blind to this by construction and go
        red the first time we shipped one more model in a packaged deck.
        """
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="old_name", new_key="new_name", table_path='["deck", "*"]')))
        _defaults(migration_dir=tmp_path, schema_version=1, document='[deck.claude]\nold_name = "b"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='[deck.claude]\nnew_name = "b"\n\n[deck.gpt6]\nnew_name = "c"\n')
        assert check_transform_chain(surface=_surface(config_model=_Deck), migration_dir=tmp_path) == []

    def test_a_destination_beneath_an_open_mapping_that_the_new_document_omits_is_tolerated(self, tmp_path: Path) -> None:
        """The fingerprint records `deck.*.new_name`; the document carries `deck.claude.new_name`, or not.

        A packaged deck entry can drop a key in the same commit that renames it, because the new
        default is what it wanted anyway. The destination is then absent from the reference
        document and present in the fingerprint only under the wildcard — a literal comparison
        would call the correct rename a misspelled destination.
        """
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="old_name", new_key="new_name", table_path='["deck", "*"]')))
        _defaults(migration_dir=tmp_path, schema_version=1, document='[deck.claude]\nold_name = "b"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document="[deck.claude]\n")
        _fingerprint(migration_dir=tmp_path, config_model=_Deck, schema_version=2)
        assert check_transform_chain(surface=_surface(config_model=_Deck), migration_dir=tmp_path) == []

    def test_a_reference_document_that_cannot_be_read_is_refused_by_name(self, tmp_path: Path) -> None:
        """A golden that exists but cannot be read is a broken golden, not a crash: the gate names it."""
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="title")))
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\n')
        defaults_golden_path(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1).write_bytes(b"\xff\xfe not utf-8")
        with pytest.raises(MigrationGoldenError, match=r"defaults@1\.toml"):
            check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path)

    def test_an_entry_dropped_from_an_open_mapping_does_not_blame_the_operation(self, tmp_path: Path) -> None:
        """When a whole container is gone from the new document, what happened inside it says nothing.

        The wildcard rename is correct here; only the packaged deck lost one of its entries in the
        same commit. Without the ancestry rule the correct operation would be reported as having
        produced a path the new shape does not have.
        """
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="old_name", new_key="new_name", table_path='["deck", "*"]')))
        _defaults(migration_dir=tmp_path, schema_version=1, document='[deck.gpt5]\nold_name = "a"\n\n[deck.claude]\nold_name = "b"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='[deck.claude]\nnew_name = "b"\n')
        assert check_transform_chain(surface=_surface(config_model=_Deck), migration_dir=tmp_path) == []

    def test_an_unsafe_entry_is_not_held_to_the_new_shape(self, tmp_path: Path) -> None:
        """An unsafe entry is reported and never applied, so no document makes this transition.

        The vocabulary grants it the right to be incomplete — an entry with no operations at all is
        legal precisely when it is unsafe — so demanding its operations reach the new shape would
        contradict the one thing `unsafe` means.
        """
        # `title`, not `label`: an entry declares a path its *own* version records, and `label` is
        # the one this bump removes. Declaring a removed path is the shape `make check-ledger`
        # refuses as DECLARED_NARROWED_PATH_IS_ABSENT — a fixture that only escapes it by calling a
        # different gate would put an illegal ledger in front of the next reader as an example.
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops="", safety="unsafe", declared='declared_narrowed_paths = ["title"]'))
        _defaults(migration_dir=tmp_path, schema_version=1, document='label = "hello"\n')
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\n')
        assert check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path) == []

    def test_a_frozen_reference_document_that_went_missing_is_named(self, tmp_path: Path) -> None:
        """A link below the head is history: it is restored, never regenerated."""
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="title")))
        _defaults(migration_dir=tmp_path, schema_version=2, document='title = "hello"\n')
        issues = check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path)
        assert _kinds(issues) == [TransformIssueKind.DEFAULTS_GOLDEN_MISSING]
        assert "defaults@1.toml" in issues[0].message

    def test_the_head_link_waits_for_its_snapshot_in_silence(self, tmp_path: Path) -> None:
        """Between a bump and the `umig` that snapshots it, the coverage gate already says so.

        It names the missing snapshot and the command that writes it; saying it a second time here
        would only make the same bump look like two problems.
        """
        _write_ledger(migration_dir=tmp_path, entries=_entry(ops=_rename(key="label", new_key="title")))
        _defaults(migration_dir=tmp_path, schema_version=1, document='label = "hello"\n')
        assert check_transform_chain(surface=_surface(config_model=_Renamed), migration_dir=tmp_path) == []
