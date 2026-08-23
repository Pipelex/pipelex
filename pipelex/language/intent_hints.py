"""Intent hints — the language-standard knowledge shared by every hints consumer.

Single owner of the MTHDS intent-hints vocabulary (spec: `mthds/docs/spec/intent-hints.md`), the
one precedence implementation (`merge_hints`), and the applicability judgment. The refinement-chain
walks stay where they are (crate normalization, the input-form deriver); they all call the merge
defined here so the standard's key-by-key precedence has exactly one implementation.

Hints are non-normative: nothing in this module participates in any verdict or execution decision.
"""

from collections.abc import Sequence
from enum import StrEnum

INTENT_HINT_KEY = "intent"
"""The one hint key this version of the standard defines."""

KNOWN_HINT_KEYS = frozenset({INTENT_HINT_KEY})
"""Keys defined by the pinned standard version; anything else is preserved-but-warned content."""


class IntentWord(StrEnum):
    """The closed `intent` vocabulary, pinned per standard version like the native concept definitions."""

    PROSE = "prose"
    LABEL = "label"
    RATING = "rating"
    QUANTITY = "quantity"


class HintSiteValueKind(StrEnum):
    """What a site's value is, for applicability judgment.

    Callers classify their site with their own structural knowledge (field types; refinement chains
    reaching `native.Text` / `native.Number`; description-only concepts are text-valued; plural
    sites judged per item) and hand the classification here.
    """

    TEXT_VALUED = "text_valued"
    NUMBER_VALUED = "number_valued"
    OTHER = "other"


_TEXT_INTENT_WORDS = frozenset({IntentWord.PROSE, IntentWord.LABEL})
_NUMBER_INTENT_WORDS = frozenset({IntentWord.RATING, IntentWord.QUANTITY})


def merge_hints(layers: Sequence[dict[str, str] | None]) -> dict[str, str] | None:
    """Merge hint layers key by key, ordered farthest to nearest — a later layer wins.

    The one precedence implementation: the refinement chain (base before refiner) and the
    site-over-concept merge (concept layer before site layer) both express their order here.
    An empty result is `None` — absent hints are an absent member, never an empty table.
    """
    merged: dict[str, str] = {}
    for layer in layers:
        if layer:
            merged.update(layer)
    return merged or None


def is_intent_word_known(word: str) -> bool:
    return word in set(IntentWord)


def intent_word_applies(word: str, *, site_kind: HintSiteValueKind) -> bool:
    """Whether a KNOWN intent word applies to a site of the given value kind (unknown words never apply)."""
    match site_kind:
        case HintSiteValueKind.TEXT_VALUED:
            return word in _TEXT_INTENT_WORDS
        case HintSiteValueKind.NUMBER_VALUED:
            return word in _NUMBER_INTENT_WORDS
        case HintSiteValueKind.OTHER:
            return False


def applicable_intent(hints: dict[str, str] | None, *, site_kind: HintSiteValueKind) -> str | None:
    """The effective `intent` word, only when it is known AND applicable to the site.

    The deriver's and the lint's shared question: absent, unknown, and inapplicable intents all
    answer `None`, leaving the consumer on its own semantic-layer defaults.
    """
    if not hints:
        return None
    word = hints.get(INTENT_HINT_KEY)
    if word is None or not is_intent_word_known(word):
        return None
    if not intent_word_applies(word, site_kind=site_kind):
        return None
    return word
