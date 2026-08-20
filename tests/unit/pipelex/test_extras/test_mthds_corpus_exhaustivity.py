"""The corpus-side exhaustivity gate — the gate the whole corpus exists for.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Gates" →
"Corpus-side: exhaustivity".

The moment a runtime registry grows a code, regeneration adds its tag and this gate stays red
until a focused entry covers it. It is why "the `Time` native concept has no fixture anywhere"
cannot happen again silently.
"""

from pipelex.test_extras.mthds_corpus.loader import iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryGranularity
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
