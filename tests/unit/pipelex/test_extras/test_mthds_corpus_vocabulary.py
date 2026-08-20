"""The corpus tag vocabulary: normalization, generation drift, and the exclusion mechanism.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Tag vocabulary".

No `native.*` code is excluded today — every one of them turned out to support a meaningful
focused entry — so the exclusion mechanism's semantics are pinned here rather than left to be
discovered broken on the day `operator.*` or `error.*` first needs it. The other half of the
mechanism, that an exclusion cannot outlive the code it names, is held by the generator keying
its exclusion map on the enum: a removed code breaks that module at import, which no test can
provoke without smuggling in a key the annotation forbids.
"""

from pipelex.cli.dev_cli.commands.generate_corpus_vocabulary_cmd import (
    generate_corpus_vocabulary_content,
    normalize_registry_code,
)
from pipelex.test_extras.mthds_corpus.vocabulary import CorpusVocabulary, VocabularyTag, vocabulary_path


class TestMthdsCorpusVocabulary:
    def test_normalization_splits_words_and_keeps_acronyms_whole(self) -> None:
        """The acronym rule is what keeps `JSON` from becoming `j_s_o_n`."""
        assert normalize_registry_code(code="Text") == "text"
        assert normalize_registry_code(code="Html") == "html"
        assert normalize_registry_code(code="YesNo") == "yes_no"
        assert normalize_registry_code(code="TextAndImages") == "text_and_images"
        assert normalize_registry_code(code="SearchResult") == "search_result"
        assert normalize_registry_code(code="JSON") == "json"
        assert normalize_registry_code(code="JSONSchema") == "json_schema"

    def test_committed_vocabulary_matches_a_fresh_generation(self) -> None:
        """The committed file is byte-identical to what the generator produces right now.

        This is the whole freshness story for the vocabulary. It is committed and ships in the
        wheel, so regenerating in memory here is a stronger gate than a `check-` CLI command
        would be, and needs no Make target of its own.
        """
        committed = vocabulary_path().read_text(encoding="utf-8")
        assert committed == generate_corpus_vocabulary_content(), (
            "The committed corpus vocabulary is out of date. Run `make generate-corpus-vocabulary`."
        )

    def test_an_excluded_tag_stays_usable_but_stops_being_required(self) -> None:
        """Exclusions are visible decisions: the tag stays in the vocabulary, it just stops being owed an entry."""
        vocabulary = CorpusVocabulary(
            namespaces={
                "native": {
                    "text": VocabularyTag(code="Text"),
                    "anything": VocabularyTag(code="Anything", excluded="No standalone focused entry could exercise it."),
                }
            }
        )
        assert vocabulary.tags == frozenset({"native.text", "native.anything"})
        assert vocabulary.required_tags == frozenset({"native.text"})
