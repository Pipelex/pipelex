"""Unit tests for the shared intent-hints language module (spec: mthds/docs/spec/intent-hints.md)."""

import pytest

from pipelex.language.intent_hints import (
    INTENT_HINT_KEY,
    KNOWN_HINT_KEYS,
    HintSiteValueKind,
    IntentWord,
    applicable_intent,
    intent_word_applies,
    is_intent_word_known,
    merge_hints,
)


class TestMergeHints:
    def test_later_layer_wins_key_by_key(self):
        base = {"intent": "prose", "extra": "kept"}
        site = {"intent": "label"}
        assert merge_hints([base, site]) == {"intent": "label", "extra": "kept"}

    def test_none_and_empty_layers_are_transparent(self):
        assert merge_hints([None, {"intent": "prose"}, None, {}]) == {"intent": "prose"}

    def test_empty_merge_is_none(self):
        assert merge_hints([]) is None
        assert merge_hints([None, {}]) is None

    def test_key_overridden_not_cleared(self):
        """No layer can unset an inherited key — an unknown word replaces, absence inherits."""
        base = {"intent": "prose"}
        assert merge_hints([base, {"intent": "banana"}]) == {"intent": "banana"}
        assert merge_hints([base, {}]) == {"intent": "prose"}

    def test_result_is_a_fresh_dict(self):
        base = {"intent": "prose"}
        merged = merge_hints([base])
        assert merged == base
        assert merged is not base


class TestVocabulary:
    def test_known_words(self):
        for word in ("prose", "label", "rating", "quantity"):
            assert is_intent_word_known(word)
        assert not is_intent_word_known("banana")
        assert not is_intent_word_known("")

    def test_known_keys(self):
        assert INTENT_HINT_KEY in KNOWN_HINT_KEYS


class TestApplicability:
    @pytest.mark.parametrize(
        ("word", "site_kind", "applies"),
        [
            (IntentWord.PROSE, HintSiteValueKind.TEXT_VALUED, True),
            (IntentWord.LABEL, HintSiteValueKind.TEXT_VALUED, True),
            (IntentWord.RATING, HintSiteValueKind.TEXT_VALUED, False),
            (IntentWord.QUANTITY, HintSiteValueKind.TEXT_VALUED, False),
            (IntentWord.PROSE, HintSiteValueKind.NUMBER_VALUED, False),
            (IntentWord.LABEL, HintSiteValueKind.NUMBER_VALUED, False),
            (IntentWord.RATING, HintSiteValueKind.NUMBER_VALUED, True),
            (IntentWord.QUANTITY, HintSiteValueKind.NUMBER_VALUED, True),
            (IntentWord.PROSE, HintSiteValueKind.OTHER, False),
            (IntentWord.RATING, HintSiteValueKind.OTHER, False),
        ],
    )
    def test_intent_word_applies(self, word: IntentWord, site_kind: HintSiteValueKind, applies: bool):
        assert intent_word_applies(word, site_kind=site_kind) is applies

    def test_unknown_word_never_applies(self):
        for site_kind in HintSiteValueKind:
            assert not intent_word_applies("banana", site_kind=site_kind)


class TestApplicableIntent:
    def test_known_and_applicable(self):
        assert applicable_intent({"intent": "prose"}, site_kind=HintSiteValueKind.TEXT_VALUED) == "prose"
        assert applicable_intent({"intent": "rating"}, site_kind=HintSiteValueKind.NUMBER_VALUED) == "rating"

    def test_absent_unknown_and_inapplicable_answer_none(self):
        assert applicable_intent(None, site_kind=HintSiteValueKind.TEXT_VALUED) is None
        assert applicable_intent({}, site_kind=HintSiteValueKind.TEXT_VALUED) is None
        assert applicable_intent({"other": "x"}, site_kind=HintSiteValueKind.TEXT_VALUED) is None
        assert applicable_intent({"intent": "banana"}, site_kind=HintSiteValueKind.TEXT_VALUED) is None
        assert applicable_intent({"intent": "rating"}, site_kind=HintSiteValueKind.TEXT_VALUED) is None
        assert applicable_intent({"intent": "prose"}, site_kind=HintSiteValueKind.OTHER) is None
