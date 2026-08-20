"""The corpus-side exhaustivity gate — the gate the whole corpus exists for.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Gates" →
"Corpus-side: exhaustivity".

The moment a runtime registry grows a code, regeneration adds its tag and this gate stays red
until a focused entry covers it. It is why "the `Time` native concept has no fixture anywhere"
cannot happen again silently.

The agreement check is the third arm and belongs here rather than with the entry-validation
gate, because it compares two *declarations* and needs no runtime: an invalid entry states its
fault twice in one file — once as ``expected_error``, the wire string the runtime emits, and once
as an ``error.*`` tag in ``covers``, the normalized form the vocabulary declares. Nothing else
checks that the two agree, so without it an entry could claim coverage of a tag it does not
produce and the exhaustivity arm above would count that claim.

The ``fails_at`` arm extends exhaustivity from tags to what a tag has to *say*. A consumer sweeping the
corpus with a structural checker branches on ``fails_at``, so a tag that is owed an entry and
declares no layer leaves that consumer with nothing to branch on — the same hole as a tag with no
entry, one level down. Keeping it here rather than with the generator's own drift gate is
deliberate: this reads the loaded vocabulary, which is what a consumer sees, so the requirement
survives a change in how the file comes to be written.
"""

from pipelex.test_extras.mthds_corpus.loader import iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryGranularity, EntryValidity
from pipelex.test_extras.mthds_corpus.vocabulary import ERROR_NAMESPACE, load_vocabulary


class TestMthdsCorpusExhaustivity:
    def test_every_required_tag_has_a_focused_entry(self) -> None:
        covered_by_focused: set[str] = set()
        for entry in iter_entries(granularity=EntryGranularity.FOCUSED):
            covered_by_focused.update(entry.manifest.covers)
        uncovered = sorted(load_vocabulary().required_tags - covered_by_focused)
        assert not uncovered, f"Vocabulary tags with no focused corpus entry: {', '.join(uncovered)}"

    def test_every_tag_an_entry_covers_exists_in_the_vocabulary(self) -> None:
        declared = load_vocabulary().tags
        unknown: set[str] = set()
        for entry in iter_entries():
            for tag in entry.manifest.covers:
                if tag not in declared:
                    unknown.add(f"{entry.name}: {tag}")
        assert not unknown, f"Corpus entries cover tags that are not in the vocabulary: {', '.join(sorted(unknown))}"

    def test_every_invalid_entry_covers_the_tag_its_expected_error_names(self) -> None:
        """The two spellings of one fault must agree, and the fault is all the entry covers.

        Equality rather than membership, because the arm above counts every focused entry's
        ``covers`` regardless of validity — it has to, since the ``error.*`` tags are covered by
        nothing else. A broken bundle that also tagged the pipe kind carrying its fault would
        therefore satisfy that tag, and the working feature would silently lose its own fixture.

        The join runs through the vocabulary's own ``code`` field rather than by re-normalizing
        ``expected_error`` here: ``code`` records the registry spelling verbatim, so looking the
        tag up by it keeps this gate from carrying a second copy of the normalization rule that
        could drift from the generator's.
        """
        tag_by_error_code = {
            tag.code: f"{namespace}.{local_name}"
            for namespace, tags_in_namespace in load_vocabulary().namespaces.items()
            if namespace == ERROR_NAMESPACE
            for local_name, tag in tags_in_namespace.items()
            if tag.code is not None
        }
        disagreements: list[str] = []
        for entry in iter_entries(validity=EntryValidity.INVALID):
            expected_error = entry.manifest.expected_error
            assert expected_error, f"Corpus entry '{entry.name}' is invalid, so the manifest guarantees an expected_error"
            owed_tag = tag_by_error_code.get(expected_error)
            if owed_tag is None:
                disagreements.append(f"{entry.name}: expected_error '{expected_error}' is in no error.* tag's `code`")
            elif entry.manifest.covers != [owed_tag]:
                disagreements.append(f"{entry.name}: expected_error '{expected_error}' means `covers` must be exactly ['{owed_tag}']")
        assert not disagreements, (
            "Invalid entries disagree with themselves: "
            + "; ".join(sorted(disagreements))
            + ". An invalid entry's `covers` is its error.* tag and nothing else: the arm above reads `covers` as the "
            "claim that a tag has a focused entry, and a deliberately broken bundle must never be what satisfies that "
            "claim for a working feature."
        )

    def test_every_required_error_tag_declares_the_layer_it_fails_at(self) -> None:
        """A fault a consumer is owed an entry for must also say which layer catches it first.

        Required rather than universal: an excluded ``error.*`` tag has no entry, so no measurement
        of it exists and inventing one would be an argument dressed as a measurement. The other
        namespaces name language features, not faults, and have no layer to declare at all.
        """
        vocabulary = load_vocabulary()
        error_prefix = f"{ERROR_NAMESPACE}."
        silent = sorted(
            f"{ERROR_NAMESPACE}.{local_name}"
            for local_name, tag in vocabulary.namespaces[ERROR_NAMESPACE].items()
            if tag.fails_at is None and f"{error_prefix}{local_name}" in vocabulary.required_tags
        )
        assert not silent, (
            "Required error.* tags declare no `fails_at`: "
            + ", ".join(silent)
            + ". A structural consumer expects a diagnostic on exactly the `schema` faults and none on the "
            "`runtime` ones, so a fault that names no layer is one it cannot sweep for. Declare it in the "
            "vocabulary generator's schema-fault set and regenerate with `make generate-corpus-vocabulary`."
        )

    def test_no_valid_entry_claims_an_error_tag(self) -> None:
        """The other half of the same hole: a bundle that validates cannot cover a fault.

        The arm above stops an invalid entry from claiming a tag it does not produce. Nothing
        stopped a *valid* one from doing it, and the first arm counts every focused entry's
        ``covers`` regardless of validity — so a valid entry carrying an ``error.*`` tag would
        satisfy that tag's exhaustivity claim while its bundle, by definition, produces no error
        at all. The fault would then have no entry exercising it and the gate would stay green.

        An ``error.*`` tag is a claim about a diagnostic, and only an entry that declares an
        ``expected_error`` can honour one.
        """
        error_namespace_prefix = f"{ERROR_NAMESPACE}."
        offenders = [
            f"{entry.name}: {tag}"
            for entry in iter_entries(validity=EntryValidity.VALID)
            for tag in entry.manifest.covers
            if tag.startswith(error_namespace_prefix)
        ]
        assert not offenders, (
            "Valid entries cover error.* tags they cannot produce: "
            + "; ".join(sorted(offenders))
            + ". Only an invalid entry, which declares the `expected_error` it must fail with, can cover an error.* tag."
        )
