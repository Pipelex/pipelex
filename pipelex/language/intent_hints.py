"""Intent hints — the language-standard knowledge shared by every hints consumer.

Single owner of the MTHDS hints vocabularies (spec: `mthds/docs/spec/intent-hints.md`): the three
defined keys, `intent`, `role` and `part`, the closed word list of each, the one precedence
implementation (`merge_hints`), and the applicability judgments. The refinement-chain walks stay where
they are (crate normalization, the input-form deriver); they all call the merge defined here so the
standard's key-by-key precedence has exactly one implementation.

The vocabularies are the ones the standard pinned at 9.2.0. Hints are non-normative: nothing in this
module participates in any verdict or execution decision.
"""

from collections.abc import Sequence
from enum import StrEnum

INTENT_HINT_KEY = "intent"
"""The key whose word says what a value is: prose, a label, a rating, a photo..."""

ROLE_HINT_KEY = "role"
"""The key whose word says what part an input slot plays in the job the method does."""

PART_HINT_KEY = "part"
"""The key whose word says what part of its record a structure field is."""

KNOWN_HINT_KEYS = frozenset({INTENT_HINT_KEY, ROLE_HINT_KEY, PART_HINT_KEY})
"""Keys defined by the pinned standard version; anything else is preserved-but-warned content."""


class IntentWord(StrEnum):
    """The closed `intent` vocabulary, pinned per standard version like the native concept definitions."""

    PROSE = "prose"
    LABEL = "label"
    RATING = "rating"
    QUANTITY = "quantity"
    CODE = "code"
    IDENTIFIER = "identifier"
    QUESTION = "question"
    PHOTO = "photo"
    SCREENSHOT = "screenshot"
    SCAN = "scan"


class RoleWord(StrEnum):
    """The closed `role` vocabulary: what part an input plays in the job, from what changes every run to what rarely does."""

    SUBJECT = "subject"
    CONTEXT = "context"
    GUIDANCE = "guidance"
    REFERENCE = "reference"
    SETTING = "setting"


class PartWord(StrEnum):
    """The closed `part` vocabulary: what part of its record a structure field is."""

    TITLE = "title"
    SUMMARY = "summary"
    VERDICT = "verdict"
    METRIC = "metric"
    BODY = "body"
    EVIDENCE = "evidence"
    DETAIL = "detail"

    @property
    def is_held_once(self) -> bool:
        """Whether one structure should give this part to one field at most: its title, its summary and its verdict."""
        match self:
            case PartWord.TITLE | PartWord.SUMMARY | PartWord.VERDICT:
                return True
            case PartWord.METRIC | PartWord.BODY | PartWord.EVIDENCE | PartWord.DETAIL:
                return False


class HintSiteValueKind(StrEnum):
    """What a site's value is, for applicability judgment.

    Callers classify their site with their own structural knowledge (field types; refinement chains
    reaching a native; description-only concepts are text-valued; plural sites judged per item for an
    intent word) and hand the classification here. The text, number, date and time kinds are also the
    standard's value classes, which decide where a contract fact applies (`pipelex.language.contract_facts`).
    """

    TEXT_VALUED = "text_valued"
    NUMBER_VALUED = "number_valued"
    DATE_VALUED = "date_valued"
    TIME_VALUED = "time_valued"
    IMAGE_VALUED = "image_valued"
    DOCUMENT_VALUED = "document_valued"
    OTHER = "other"

    @property
    def is_text_valued(self) -> bool:
        match self:
            case HintSiteValueKind.TEXT_VALUED:
                return True
            case (
                HintSiteValueKind.NUMBER_VALUED
                | HintSiteValueKind.DATE_VALUED
                | HintSiteValueKind.TIME_VALUED
                | HintSiteValueKind.IMAGE_VALUED
                | HintSiteValueKind.DOCUMENT_VALUED
                | HintSiteValueKind.OTHER
            ):
                return False

    @property
    def is_number_valued(self) -> bool:
        match self:
            case HintSiteValueKind.NUMBER_VALUED:
                return True
            case (
                HintSiteValueKind.TEXT_VALUED
                | HintSiteValueKind.DATE_VALUED
                | HintSiteValueKind.TIME_VALUED
                | HintSiteValueKind.IMAGE_VALUED
                | HintSiteValueKind.DOCUMENT_VALUED
                | HintSiteValueKind.OTHER
            ):
                return False

    @property
    def is_file_valued(self) -> bool:
        """Whether a value of this kind is a file: an image or a document."""
        match self:
            case HintSiteValueKind.IMAGE_VALUED | HintSiteValueKind.DOCUMENT_VALUED:
                return True
            case (
                HintSiteValueKind.TEXT_VALUED
                | HintSiteValueKind.NUMBER_VALUED
                | HintSiteValueKind.DATE_VALUED
                | HintSiteValueKind.TIME_VALUED
                | HintSiteValueKind.OTHER
            ):
                return False


class FieldShape(StrEnum):
    """The shape of a structure field, beyond its value kind, that decides where a `part` word applies."""

    # A field holding one value of its value kind, a concept-typed field included.
    SCALAR = "scalar"
    # An enumeration field: `choices` declared.
    ENUMERATION = "enumeration"
    # A `boolean` field.
    BOOLEAN = "boolean"
    # A concept-typed field whose concept is a verdict native, `YesNo`, `Choice` or `Rating`, or refines one.
    VERDICT_NATIVE = "verdict_native"
    # A `list` field, judged as a whole and never by its item.
    LIST = "list"
    # Any other field: a `dict`, or a concept field holding a structure.
    OTHER = "other"

    @property
    def is_scalar(self) -> bool:
        match self:
            case FieldShape.SCALAR:
                return True
            case FieldShape.ENUMERATION | FieldShape.BOOLEAN | FieldShape.VERDICT_NATIVE | FieldShape.LIST | FieldShape.OTHER:
                return False


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
    # Sorted here too: merged results are installed via model_copy(update=...), which bypasses the
    # blueprint validators that sort authored tables, yet still reach canonical serialization.
    return dict(sorted(merged.items())) or None


def is_intent_word_known(word: str) -> bool:
    return word in set(IntentWord)


def is_role_word_known(*, word: str) -> bool:
    return word in set(RoleWord)


def is_part_word_known(*, word: str) -> bool:
    return word in set(PartWord)


def intent_applicable_kinds(*, word: IntentWord) -> frozenset[HintSiteValueKind]:
    """The site value kinds an intent word applies to.

    Exhaustive over the vocabulary, so a new word cannot land without an explicit applicability
    decision here (unknown raw words are filtered out by `is_intent_word_known` upstream).
    """
    match word:
        case IntentWord.PROSE | IntentWord.LABEL | IntentWord.CODE | IntentWord.IDENTIFIER | IntentWord.QUESTION:
            return frozenset({HintSiteValueKind.TEXT_VALUED})
        case IntentWord.RATING | IntentWord.QUANTITY:
            return frozenset({HintSiteValueKind.NUMBER_VALUED})
        case IntentWord.PHOTO | IntentWord.SCREENSHOT:
            return frozenset({HintSiteValueKind.IMAGE_VALUED})
        case IntentWord.SCAN:
            return frozenset({HintSiteValueKind.IMAGE_VALUED, HintSiteValueKind.DOCUMENT_VALUED})


def intent_word_applies(word: IntentWord, *, site_kind: HintSiteValueKind) -> bool:
    """Whether an intent word applies to a site of the given value kind."""
    return site_kind in intent_applicable_kinds(word=word)


def part_word_applies(*, word: PartWord, site_kind: HintSiteValueKind, field_shape: FieldShape) -> bool:
    """Whether a `part` word applies to a structure field, judged against the field itself, never a list field's item.

    `title` and `summary` take a text-valued field, `metric` a number-valued one, `verdict` an enumeration, a boolean,
    a number-valued field or a verdict native, and `body`, `evidence` and `detail` any field.
    """
    match word:
        case PartWord.BODY | PartWord.EVIDENCE | PartWord.DETAIL:
            return True
        case PartWord.TITLE | PartWord.SUMMARY:
            return field_shape.is_scalar and site_kind.is_text_valued
        case PartWord.METRIC:
            return field_shape.is_scalar and site_kind.is_number_valued
        case PartWord.VERDICT:
            match field_shape:
                case FieldShape.ENUMERATION | FieldShape.BOOLEAN | FieldShape.VERDICT_NATIVE:
                    return True
                case FieldShape.SCALAR:
                    return site_kind.is_number_valued
                case FieldShape.LIST | FieldShape.OTHER:
                    return False


def applicable_intent(hints: dict[str, str] | None, *, site_kind: HintSiteValueKind) -> IntentWord | None:
    """The effective `intent` word, only when it is known AND applicable to the site.

    The deriver's and the lint's shared question: absent, unknown, and inapplicable intents all
    answer `None`, leaving the consumer on its own semantic-layer defaults.
    """
    if not hints:
        return None
    word = hints.get(INTENT_HINT_KEY)
    if word is None or not is_intent_word_known(word):
        return None
    intent = IntentWord(word)
    if not intent_word_applies(intent, site_kind=site_kind):
        return None
    return intent
