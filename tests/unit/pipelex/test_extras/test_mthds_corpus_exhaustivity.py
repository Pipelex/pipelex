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
"""

from pipelex.test_extras.mthds_corpus.loader import iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryGranularity, EntryValidity
from pipelex.test_extras.mthds_corpus.vocabulary import load_vocabulary


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
        """The two spellings of one fault must agree.

        The join runs through the vocabulary's own ``code`` field rather than by re-normalizing
        ``expected_error`` here: ``code`` records the registry spelling verbatim, so looking the
        tag up by it keeps this gate from carrying a second copy of the normalization rule that
        could drift from the generator's.
        """
        tag_by_error_code = {
            tag.code: f"{namespace}.{local_name}"
            for namespace, tags_in_namespace in load_vocabulary().namespaces.items()
            if namespace == "error"
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
            elif owed_tag not in entry.manifest.covers:
                disagreements.append(f"{entry.name}: expected_error '{expected_error}' means it must cover '{owed_tag}'")
        assert not disagreements, "Invalid entries disagree with themselves: " + "; ".join(sorted(disagreements))
