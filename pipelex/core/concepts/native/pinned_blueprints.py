"""Pinned normative blueprints of the native concepts, per MTHDS standard version.

The MTHDS standard pins every native concept's exact blueprint form — fields, types, and
descriptions — in `mthds/docs/spec/native-concepts.md`. This module is the runtime copy of that
pinned set: crate materialization looks definitions up here instead of reflecting over the runtime
content classes, so two independent implementations byte-agree on materialized natives (and
therefore on crate fingerprints). Any edit here is a standard change and must land in the spec
page first, except for a native Pipelex defines ahead of the standard
(`NativeConceptCode.is_pinned_by_the_standard` is False for it), whose blueprint is Pipelex's own
until the page defines it in exactly these words; the consistency test in `tests/unit/pipelex/codegen/`
proves each runtime content class still matches its pinned blueprint, so the two can never drift silently — and
`tests/unit/pipelex/core/concepts/test_pinned_natives_vs_standard.py` holds this set to the
standard's page itself, read live from the sibling `mthds/` checkout (the `MTHDS standard
conformance` CI workflow runs it against a fresh checkout on every pull request), so the day the
standard moves a definition, this repo goes red instead of a downstream port.

The set below is the one the standard pinned at MTHDS 9.0.0, named by
`PINNED_NATIVES_MTHDS_VERSION`. Version-keyed lookup can come when a second pinned set exists;
until then an implementation of standard version `V` materializes the greatest pinned set not
above `V`, and this is the only one there is.
"""

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_structure_blueprint import ANY_NESTED_FIELD_TYPE, ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.stored_value_content import STORED_VALUE_REFERENCE_FIELDS, StoredValueContent

# The standard version in which the pinned set below last changed — the standard asks each
# implementation to declare that number once, in one place, naming its source: the page's own
# "The Pinned Set — Pinned at MTHDS <version>" heading in `mthds/docs/spec/native-concepts.md`.
# It is NOT the standard version this engine implements (`MTHDS_STANDARD_VERSION`, which is what a
# crate's `mthds_version` stamp records), and the two only coincide while the set's last re-pinning
# is the latest release of the standard. `tests/unit/pipelex/core/concepts/test_pinned_natives_vs_standard.py`
# holds this value to the page; `test_pinned_natives_version.py` beside it holds it to the standard
# version this engine implements, which is the reading that needs no sibling checkout.
PINNED_NATIVES_MTHDS_VERSION = "9.0.0"


def make_pinned_native_blueprint(native_code: NativeConceptCode) -> ConceptBlueprint:
    """Build the pinned normative `ConceptBlueprint` for a native concept (fresh instance per call)."""
    return ConceptBlueprint(
        source=None,
        description=_pinned_description(native_code),
        structure=_pinned_structure(native_code),
    )


def make_pinned_native_value_blueprint(native_code: NativeConceptCode) -> ConceptBlueprint:
    """The pinned blueprint of a native concept without the fields carrying a stored value: the parts of the value itself.

    For a native that may hold its value stored (`Text`, `Markdown`, `Html`, `JSON`, whose content classes are the
    `StoredValueContent` ones), it drops `url`, `size`, `mime_type` and `preview` (`STORED_VALUE_REFERENCE_FIELDS`), which
    say where the value is rather than what it holds: the standard's binding walk treats them as no field of the value,
    and a caller supplying an input supplies the value itself. So `Text` holds its value in the single field `text`,
    which this marks required: the value is always there, inline or once loaded from its URL. The value field is the
    content class's own `value_field_name`. Every other native is its pinned blueprint as is.
    """
    blueprint = make_pinned_native_blueprint(native_code)
    if not isinstance(blueprint.structure, dict):
        return blueprint
    value_structure = make_native_value_structure(native_code, structure=blueprint.structure)
    if value_structure is None:
        return blueprint
    return ConceptBlueprint(source=None, description=blueprint.description, structure=value_structure)


def make_native_value_structure(
    native_code: NativeConceptCode,
    *,
    structure: dict[str, ConceptStructureBlueprintType],
) -> dict[str, ConceptStructureBlueprintType] | None:
    """A storable native's structure as its value alone: without `url`, `size`, `mime_type` and `preview`, its value field required.

    It reads the structure it is given, the pinned one or a crate's copy of it, so a reader of a crate takes the value
    form from the crate itself. A field written as a bare description is kept as it is.

    Returns:
        The value form, or None for a native that never holds its value in storage.
    """
    structure_class = native_code.structure_class
    if structure_class is None or not issubclass(structure_class, StoredValueContent):
        return None
    value_field_name = structure_class.value_field_name
    value_structure: dict[str, ConceptStructureBlueprintType] = {}
    for field_name, field_blueprint in structure.items():
        if field_name in STORED_VALUE_REFERENCE_FIELDS:
            continue
        if field_name == value_field_name and isinstance(field_blueprint, ConceptStructureBlueprint):
            value_structure[field_name] = field_blueprint.model_copy(update={"required": True})
        else:
            value_structure[field_name] = field_blueprint
    return value_structure


def _pinned_description(native_code: NativeConceptCode) -> str:
    match native_code:
        case NativeConceptCode.DYNAMIC:
            return "A dynamic concept"
        case NativeConceptCode.TEXT:
            return "A text"
        case NativeConceptCode.MARKDOWN:
            return "A text written in Markdown"
        case NativeConceptCode.IMAGE:
            return "An image"
        case NativeConceptCode.DOCUMENT:
            return "A document"
        case NativeConceptCode.HTML:
            return "HTML content"
        case NativeConceptCode.TEXT_AND_IMAGES:
            return "A text and an image"
        case NativeConceptCode.NUMBER:
            return "A number"
        case NativeConceptCode.YES_NO:
            return "The answer to a yes/no question"
        case NativeConceptCode.CHOICE:
            return "One option picked out of a declared set"
        case NativeConceptCode.RATING:
            return "A position on an ordered scale of described levels"
        case NativeConceptCode.DATE:
            return "A calendar date, optionally with a time of day — as precise as its source states."
        case NativeConceptCode.TIME:
            return "A time of day, optionally with a UTC offset — as precise as its source states."
        case NativeConceptCode.PAGE:
            return "The content of a page of a document, comprising text and linked images and an optional page view image"
        case NativeConceptCode.JSON:
            return "A JSON object"
        case NativeConceptCode.SEARCH_RESULT:
            return "A search result with answer and sources"
        case NativeConceptCode.ANYTHING:
            return "Anything"
        case NativeConceptCode.COMPOSITE:
            return "A named composition of contents"


def _pinned_structure(native_code: NativeConceptCode) -> dict[str, ConceptStructureBlueprintType] | None:
    match native_code:
        case NativeConceptCode.DYNAMIC | NativeConceptCode.ANYTHING | NativeConceptCode.COMPOSITE:
            # Structureless by design: their shape is intentionally open, surfaced as such per the
            # crate sufficiency guarantee — never a guessed structure.
            return None
        case NativeConceptCode.TEXT:
            # The text inline, or a URL to it in storage with its size, MIME type and preview: a compliant value
            # carries exactly one of `text` and `url`, and the three others only with `url`. The structure language
            # has no cross-field form, so the rule constrains values, not this blueprint.
            return {
                "text": _text_field(description="The text"),
                **_stored_value_fields(stored_desc="text", measured_desc="text", mime_types_desc="text/plain or text/markdown"),
            }
        case NativeConceptCode.MARKDOWN:
            # Text's fields, its value holding the Markdown source. A blueprint states `structure` or `refines`,
            # never both, so the refinement of `Text` lives on the runtime concept (`ConceptFactory`), not here.
            # Pipelex defines Markdown ahead of the standard, so this is not yet a copy of the standard's page.
            return {
                "text": _text_field(description="The text, written in Markdown"),
                **_stored_value_fields(stored_desc="text", measured_desc="text", mime_types_desc="text/plain or text/markdown"),
            }
        case NativeConceptCode.IMAGE:
            return {
                "url": _text_field(description="The image URL: a storage URI, an HTTP(S) URL, or a base64 data URL", required=True),
                "public_url": _text_field(description="The public URL of the image"),
                "source_prompt": _text_field(description="The source prompt of the image"),
                "source_negative_prompt": _text_field(description="The source negative prompt of the image"),
                "caption": _text_field(description="The caption of the image"),
                "mime_type": _text_field(description="The MIME type of the image"),
                "width": ConceptStructureBlueprint(description="The width of the image, in pixels", type=ConceptStructureBlueprintFieldType.INTEGER),
                "height": ConceptStructureBlueprint(
                    description="The height of the image, in pixels", type=ConceptStructureBlueprintFieldType.INTEGER
                ),
                "filename": _text_field(description="The original filename of the image"),
            }
        case NativeConceptCode.DOCUMENT:
            return {
                "url": _text_field(description="The document URL: a storage URI, an HTTP(S) URL, or a base64 data URL", required=True),
                "public_url": _text_field(description="The public HTTPS URL of the document"),
                "mime_type": _text_field(description="The MIME type of the document"),
                "filename": _text_field(description="The original filename of the document"),
                "title": _text_field(description="The title of the document or source"),
                "snippet": _text_field(description="A text snippet or excerpt from the document"),
            }
        case NativeConceptCode.HTML:
            # As Text: the HTML inline or a URL to it, exactly one; `css_class` stays inline in both forms.
            return {
                "inner_html": _text_field(description="The inner HTML of the content"),
                "css_class": _text_field(description="The CSS class of the content"),
                **_stored_value_fields(stored_desc="inner HTML", measured_desc="inner HTML", mime_types_desc="text/html"),
            }
        case NativeConceptCode.TEXT_AND_IMAGES:
            return {
                "text": ConceptStructureBlueprint(
                    description="A text content",
                    type=ConceptStructureBlueprintFieldType.CONCEPT,
                    concept_ref=NativeConceptCode.TEXT.concept_ref,
                ),
                "images": ConceptStructureBlueprint(
                    description="A list of images that were extracted from the text",
                    type=ConceptStructureBlueprintFieldType.LIST,
                    item_type="concept",
                    item_concept_ref=NativeConceptCode.IMAGE.concept_ref,
                ),
                "raw_html": _text_field(description="The raw HTML of the fetched page, if requested"),
            }
        case NativeConceptCode.NUMBER:
            return {
                "number": ConceptStructureBlueprint(description="The number", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            }
        case NativeConceptCode.YES_NO:
            return {
                "yes_no": ConceptStructureBlueprint(
                    description="Whether the answer is yes (true) or no (false).", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=True
                ),
                "probability": _number_field(
                    description="The probability that the answer is yes, from 0 to 1, when the producer reports one.",
                ),
            }
        case NativeConceptCode.CHOICE:
            return {
                "choice": _text_field(description="The key of the selected option.", required=True),
                "confidence": _number_field(description="The producer's confidence in the choice, from 0 to 1, when it reports one."),
                "probabilities": _number_dict_field(
                    description="The probability of each option, keyed by option key, when the producer measures a distribution.",
                ),
            }
        case NativeConceptCode.RATING:
            return {
                "level": ConceptStructureBlueprint(
                    description="The index of the selected level, 0 being the first level declared.",
                    type=ConceptStructureBlueprintFieldType.INTEGER,
                    required=True,
                ),
                "label": _text_field(description="The label of the selected level, when the scale declares labels."),
                "confidence": _number_field(description="The producer's confidence in the level, from 0 to 1, when it reports one."),
                "probabilities": _number_dict_field(
                    description="The probability of each level, keyed by level index written as text, when the producer measures a distribution.",
                ),
                "position": _number_field(
                    description="A continuous position on the scale, from 0 to the index of the last level, when the producer measures one.",
                ),
            }
        case NativeConceptCode.DATE:
            return {
                "date": ConceptStructureBlueprint(
                    description="The calendar date, in ISO 8601 (e.g. 2026-07-07). Always required.",
                    type=ConceptStructureBlueprintFieldType.DATE,
                    required=True,
                ),
                "time": ConceptStructureBlueprint(
                    description=(
                        "The time of day, in ISO 8601 (e.g. 15:40:00, or 15:40:00+02:00 with a UTC offset). "
                        "Include it only when the source states a time — never invent a time. "
                        "Keep the UTC offset exactly when the source states one."
                    ),
                    type=ConceptStructureBlueprintFieldType.TIME,
                ),
            }
        case NativeConceptCode.TIME:
            return {
                "time": ConceptStructureBlueprint(
                    description="The time of day, in ISO 8601 (e.g. 15:40:00, or 15:40:00+02:00 with a UTC offset).",
                    type=ConceptStructureBlueprintFieldType.TIME,
                    required=True,
                ),
            }
        case NativeConceptCode.PAGE:
            return {
                "text_and_images": ConceptStructureBlueprint(
                    description="The text and images content extracted from the page",
                    type=ConceptStructureBlueprintFieldType.CONCEPT,
                    concept_ref=NativeConceptCode.TEXT_AND_IMAGES.concept_ref,
                    required=True,
                ),
                "page_view": ConceptStructureBlueprint(
                    description="The screenshot of the page",
                    type=ConceptStructureBlueprintFieldType.CONCEPT,
                    concept_ref=NativeConceptCode.IMAGE.concept_ref,
                ),
            }
        case NativeConceptCode.JSON:
            # As Text: the object inline or a URL to its serialized form, exactly one.
            return {
                "json_obj": ConceptStructureBlueprint(
                    description="The JSON object",
                    type=ConceptStructureBlueprintFieldType.DICT,
                    key_type="text",
                    value_type=ANY_NESTED_FIELD_TYPE,
                ),
                **_stored_value_fields(stored_desc="JSON object", measured_desc="JSON object's serialized form", mime_types_desc="application/json"),
            }
        case NativeConceptCode.SEARCH_RESULT:
            return {
                "answer": _text_field(description="The answer to the search query", required=True),
                "sources": ConceptStructureBlueprint(
                    description="The source documents supporting the answer",
                    type=ConceptStructureBlueprintFieldType.LIST,
                    item_type="concept",
                    item_concept_ref=NativeConceptCode.DOCUMENT.concept_ref,
                    required=True,
                ),
            }


def _stored_value_fields(*, stored_desc: str, measured_desc: str, mime_types_desc: str) -> dict[str, ConceptStructureBlueprintType]:
    """The stored form's fields of `Text`, `Html` and `JSON`, in the order and the words the standard pins them.

    Args:
        stored_desc: What is stored, as the descriptions name it: "text", "inner HTML", "JSON object".
        measured_desc: What `size` and `preview` are taken from, the same but for JSON, measured on its serialized form.
        mime_types_desc: The MIME types the stored value declares, as the description lists them.
    """
    return {
        "url": _text_field(description=f"The URL of the stored {stored_desc}: a storage URI, an HTTP(S) URL, or a base64 data URL"),
        "size": ConceptStructureBlueprint(
            description=f"The length of the stored {measured_desc}, in bytes as stored", type=ConceptStructureBlueprintFieldType.INTEGER
        ),
        "mime_type": _text_field(description=f"The MIME type of the stored {stored_desc}: {mime_types_desc}"),
        "preview": _text_field(description=f"The first few hundred characters of the stored {measured_desc}, always its true start"),
    }


def _text_field(*, description: str, required: bool = False) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint(description=description, type=ConceptStructureBlueprintFieldType.TEXT, required=required)


def _number_field(*, description: str) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint(description=description, type=ConceptStructureBlueprintFieldType.NUMBER)


def _number_dict_field(*, description: str) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint(
        description=description,
        type=ConceptStructureBlueprintFieldType.DICT,
        key_type="text",
        value_type=ConceptStructureBlueprintFieldType.NUMBER.value,
    )
