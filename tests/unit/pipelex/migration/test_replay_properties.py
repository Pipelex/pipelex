"""Property tests for replay neutrality, and for the two properties that travel with it.

Replay neutrality is the guarantee the whole contract exists to keep true, and it is claimed over
*every* document the current models accept. Example tests cannot express that, and the convergence
witness — a replay over the packaged defaults and the kit template — cannot either: a witness
carries exactly one value per key, so an operation that misbehaves on the *other* legal spelling
of an enumerated field passes it. `test_the_witnesses_cannot_see_an_illegal_remap` is that gap,
demonstrated: the same ledger is green on the witness and red on a generated document.

**Two venues, and the difference between them is the point.** The real surfaces are all at schema
version 1 with no entries at all, so a replay over them has nothing to replay and neutrality holds
for a reason that has nothing to do with the theorem. What does real work over the real surfaces
today is the **vacuity meta-test**: it proves the sampler emits documents the current models
actually accept, so that the property is not passing on garbage on the day the first entry lands —
the reshape's, at the join. Everything that needs a ledger with entries in it runs against a
synthetic surface whose model and ledger are written here and never move.
"""

from enum import StrEnum
from typing import Any, cast

import pytest
import tomlkit
from hypothesis import find, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.fingerprint import ENUM_TYPE
from pipelex.migration.ledger import MigrationEntry, MigrationLedger, MigrationSafety, SurfaceBlock, load_ledger
from pipelex.migration.surfaces import DefaultsLayerKind, Surface, build_config_surface_registry, packaged_migration_dir
from pipelex.suggested_fix import DeleteKeyOp, DeleteTableOp, MigrationOp, MoveKeyOp, RemapValueOp, RenameTableKeyOp
from tests.unit.pipelex.migration.document_strategies import (
    DocumentMutation,
    GeneratedDocument,
    fingerprint_at,
    merge_text_beneath_defaults,
    surface_fingerprint,
    within_schema_documents,
)

MAX_EXAMPLES = 40
PROPERTY_SETTINGS = settings(max_examples=MAX_EXAMPLES, deadline=None)
"""Bounded on purpose. `deadline=None` because these run under `xdist`, where a per-example
wall-clock deadline measures machine contention rather than anything about the engine."""

REAL_SURFACES = build_config_surface_registry().surfaces
REAL_SURFACE_IDS = [surface.surface_id for surface in REAL_SURFACES]


class _Tone(StrEnum):
    QUIET = "quiet"
    LOUD = "loud"
    MUTED = "muted"


class _Deck(BaseModel):
    """The value schema of a genuinely open node — the keys above it belong to the user."""

    model_config = ConfigDict(extra="forbid")

    tone: _Tone = Field(default=_Tone.QUIET, strict=False)
    enabled: bool = True


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: _Tone = Field(default=_Tone.QUIET, strict=False)
    enabled: bool = True


class _SyntheticConfig(BaseModel):
    """A stand-in configuration model, so the properties never move when the real models do.

    It is shaped to carry every mutation the generator can make — an enumerated field whose
    default is not the spelling a migration would target, booleans, and an open node with entries
    in it — because a property over a document with nothing to mutate proves nothing.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = "example"
    verbose: bool = False
    tone: _Tone = Field(default=_Tone.MUTED, strict=False)
    section: _Section = Field(default_factory=_Section)
    decks: dict[str, _Deck] = Field(default_factory=lambda: {"primary": _Deck(), "backup": _Deck(tone=_Tone.LOUD, enabled=False)})


SYNTHETIC_SURFACE = Surface(
    surface_id="synthetic-config",
    title="A synthetic surface whose ledger actually has entries",
    base_file="synthetic.toml",
    config_model=_SyntheticConfig,
    defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
)


def _entry(*, to_schema_version: int, ops: list[MigrationOp], safety: MigrationSafety = MigrationSafety.SAFE) -> MigrationEntry:
    return MigrationEntry(
        id=f"{SYNTHETIC_SURFACE.surface_id}@{to_schema_version}",
        to_schema_version=to_schema_version,
        introduced_in="0.46.0",
        breaking=True,
        safety=safety,
        title=f"The change that produced schema version {to_schema_version}",
        description="A shape change on the synthetic surface.",
        ops=ops,
    )


def _ledger(*, entries: list[MigrationEntry]) -> MigrationLedger:
    return MigrationLedger(
        surface=SurfaceBlock(
            id=SYNTHETIC_SURFACE.surface_id,
            title=SYNTHETIC_SURFACE.title,
            base_file=SYNTHETIC_SURFACE.base_file,
            current_schema_version=1 + len(entries),
            min_supported_schema_version=0,
        ),
        migration=entries,
    )


SYNTHETIC_ENTRIES = [
    _entry(
        to_schema_version=2,
        ops=[
            RenameTableKeyOp(table_path=[], key="heading", new_key="title"),
            MoveKeyOp(table_path=[], key="chatty", new_table_path=["section"], new_key="enabled"),
            RemapValueOp(table_path=[], key="tone", mapping={"shouty": _Tone.LOUD}),
            DeleteKeyOp(table_path=["decks", "*"], key="legacy_flag"),
        ],
    ),
    _entry(to_schema_version=3, ops=[DeleteTableOp(table_path=["legacy"])]),
]
"""Every operation's source is material the current shape no longer has — `heading`, `chatty`,
the spelling `shouty`, `legacy_flag`, the `legacy` table — which is what op legality demands and
what makes the replay a no-op on a current-valid file."""

SYNTHETIC_LEDGER = _ledger(entries=SYNTHETIC_ENTRIES)

_STRATEGIES: dict[str, st.SearchStrategy[GeneratedDocument]] = {}


def _documents_for(*, surface: Surface) -> st.SearchStrategy[GeneratedDocument]:
    """The sampler for a surface, built once — projecting a model tree is not free."""
    if surface.surface_id not in _STRATEGIES:
        _STRATEGIES[surface.surface_id] = within_schema_documents(surface=surface)
    return _STRATEGIES[surface.surface_id]


@st.composite
def _documents_at_an_older_shape(  # kw-only: ignore — Hypothesis passes `draw` positionally to a composite's body.
    draw: st.DrawFn,
) -> str:
    """A current-valid document with some of the synthetic surface's retired material put back.

    Idempotence and prefix coherence are claims about files that still have something to migrate,
    so they need documents the ledger will actually act on — the neutrality domain is exactly the
    set where it does not.
    """
    generated = draw(_documents_for(surface=SYNTHETIC_SURFACE))
    document = tomlkit.loads(generated.text).unwrap()
    if draw(st.booleans()):
        document["heading"] = "a heading from before the rename"
    if draw(st.booleans()):
        document["chatty"] = True
    if draw(st.booleans()):
        document["tone"] = "shouty"
    if draw(st.booleans()):
        document["legacy"] = {"debug": True, "level": 3}
    if draw(st.booleans()):
        for deck in cast("dict[str, dict[str, Any]]", document.get("decks", {})).values():
            deck["legacy_flag"] = True
    text: str = tomlkit.dumps(document)  # pyright: ignore[reportUnknownMemberType]
    return text


class TestTheReplayProperties:
    @pytest.mark.parametrize("surface", REAL_SURFACES, ids=REAL_SURFACE_IDS)
    @PROPERTY_SETTINGS
    @given(data=st.data())
    def test_every_generated_document_is_valid_at_the_current_schema(self, surface: Surface, data: st.DataObject) -> None:
        """The vacuity meta-test: without it, a green property says nothing.

        The generator already checks each *proposed mutation* against the model, so what is left
        for this to catch is everything that happens after — a mis-addressed drop, a path
        translated wrongly beneath an open node, a document whose round-trip through TOML is not
        what was validated — and any future model change that breaks the assembly rather than an
        individual value. It is asserted here, on the emitted text, because that is the artifact
        the property is quantified over.

        The document is validated the way a user's file is really read, merged beneath the
        surface's defaults layer: an absent optional key is the ordinary shape of a configuration
        file, not an error.
        """
        generated = data.draw(_documents_for(surface=surface))

        surface.config_model.model_validate(merge_text_beneath_defaults(surface=surface, text=generated.text))

    @pytest.mark.parametrize("surface", REAL_SURFACES, ids=REAL_SURFACE_IDS)
    def test_the_generator_does_not_merely_re_emit_the_reference_document(self, surface: Surface) -> None:
        """The other direction of vacuity. A sampler of one document satisfies every property."""
        found = find(_documents_for(surface=surface), lambda generated: bool(generated.mutations))

        assert found.mutations

    def test_a_document_path_beneath_an_open_node_resolves_to_its_value_schema(self) -> None:
        """The one translation the generator does that nothing else would notice going wrong.

        A document names the user's own key where the fingerprint names a `*`, so without this
        the values inside an open node would silently stop being mutated and every property would
        stay green over a smaller domain.
        """
        fingerprint = surface_fingerprint(surface=SYNTHETIC_SURFACE)

        beneath_an_open_node = fingerprint_at(fingerprint=fingerprint, path="decks.backup.tone")
        assert beneath_an_open_node is not None
        assert beneath_an_open_node.value_type == ENUM_TYPE
        assert beneath_an_open_node.enum_members == sorted(_Tone)
        assert fingerprint_at(fingerprint=fingerprint, path="decks.backup.invented") is None

    @pytest.mark.parametrize("mutation", list(DocumentMutation), ids=list(DocumentMutation))
    def test_the_generator_reaches_every_mutation_kind(self, mutation: DocumentMutation) -> None:
        """Asked of the synthetic surface, whose model is written here to carry all three.

        Asking it of the real surfaces would couple this test to whichever fields they happen to
        have today, and the service surface has no enumerated field at all.
        """
        found = find(_documents_for(surface=SYNTHETIC_SURFACE), lambda generated: mutation in generated.mutations)

        assert mutation in found.mutations

    @pytest.mark.parametrize("surface", REAL_SURFACES, ids=REAL_SURFACE_IDS)
    @PROPERTY_SETTINGS
    @given(data=st.data())
    def test_a_replay_over_a_current_valid_document_returns_the_very_same_text(self, surface: Surface, data: st.DataObject) -> None:
        """Neutrality over the real surfaces — structurally vacuous until the first entry lands.

        Every surface sits at schema version 1 with an empty ledger today, so this passes because
        there is nothing to replay. It is written now, against the real ledgers rather than a
        copy, so that the reshape entry is measured by it the moment it is added.
        """
        generated = data.draw(_documents_for(surface=surface))
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=surface.surface_id)

        replay = replay_ledger_over_text(ledger=ledger, text=generated.text)

        # The *very* string, not an equal one: neutrality is a property of the engine rather than
        # of tomlkit's round-trip, and identity is what tells the two apart.
        assert replay.text is generated.text
        assert not replay.steps
        assert not replay.blocked

    @PROPERTY_SETTINGS
    @given(data=st.data())
    def test_a_replay_of_a_ledger_with_entries_is_still_neutral_on_a_current_valid_document(self, data: st.DataObject) -> None:
        """The same claim where it is not vacuous: a ledger with five operations across two entries."""
        generated = data.draw(_documents_for(surface=SYNTHETIC_SURFACE))

        replay = replay_ledger_over_text(ledger=SYNTHETIC_LEDGER, text=generated.text)

        assert replay.text is generated.text
        assert not replay.steps
        assert not replay.blocked

    def test_the_older_shape_generator_reaches_documents_the_ledger_acts_on(self) -> None:
        """The vacuity meta-test for the second generator, and it needs one just as much.

        Idempotence and prefix coherence are trivially true of a file with nothing to migrate. If
        the injector ever stopped injecting, both properties would stay green over a sampler of
        documents the ledger never touches.
        """
        found = find(_documents_at_an_older_shape(), lambda text: replay_ledger_over_text(ledger=SYNTHETIC_LEDGER, text=text).did_change_document)

        assert replay_ledger_over_text(ledger=SYNTHETIC_LEDGER, text=found).did_change_document

    @PROPERTY_SETTINGS
    @given(text=_documents_at_an_older_shape())
    def test_replaying_twice_lands_where_replaying_once_landed(self, text: str) -> None:
        """Idempotence. A user who runs the migration twice must not get a second set of changes."""
        once = replay_ledger_over_text(ledger=SYNTHETIC_LEDGER, text=text)
        twice = replay_ledger_over_text(ledger=SYNTHETIC_LEDGER, text=once.text)

        assert twice.text == once.text
        assert not twice.steps

    @PROPERTY_SETTINGS
    @given(text=_documents_at_an_older_shape(), absorbed=st.integers(min_value=0, max_value=len(SYNTHETIC_ENTRIES)))
    def test_a_file_that_already_absorbed_some_entries_lands_where_a_full_replay_lands(self, text: str, absorbed: int) -> None:
        """Prefix coherence. A file caught halfway — by an older release, or by hand — converges.

        This is what makes "every run replays everything" safe without a state stamp: where a file
        starts in the chain cannot change where it ends up.
        """
        partial = replay_ledger_over_text(ledger=_ledger(entries=SYNTHETIC_ENTRIES[:absorbed]), text=text)

        from_the_middle = replay_ledger_over_text(ledger=SYNTHETIC_LEDGER, text=partial.text)
        from_zero = replay_ledger_over_text(ledger=SYNTHETIC_LEDGER, text=text)

        assert from_the_middle.text == from_zero.text

    def test_the_witnesses_cannot_see_an_illegal_remap_and_the_property_can(self) -> None:
        """Why the property exists, shown on the one ledger that separates the two checks.

        A `safe` `remap_value` whose old spelling is still a legal member of the current enum
        breaks neutrality — but only for a file that carries *that* spelling. The reference
        document carries one value per key and it is not that one, so the convergence witness is
        green on this ledger. A generated document reaches the spelling, and the property is red.
        """
        illegal = _ledger(entries=[_entry(to_schema_version=2, ops=[RemapValueOp(table_path=[], key="tone", mapping={_Tone.LOUD: _Tone.QUIET})])])
        witness = SYNTHETIC_SURFACE.render_reference_document()

        assert replay_ledger_over_text(ledger=illegal, text=witness).text is witness

        found = find(
            _documents_for(surface=SYNTHETIC_SURFACE),
            lambda generated: replay_ledger_over_text(ledger=illegal, text=generated.text).text != generated.text,
        )
        assert DocumentMutation.SWAPPED_ENUM_MEMBER in found.mutations
