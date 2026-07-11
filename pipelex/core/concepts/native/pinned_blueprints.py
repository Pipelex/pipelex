"""Pinned normative blueprints of the native concepts, per MTHDS standard version.

The MTHDS standard pins every native concept's exact blueprint form — fields, types, and
descriptions — in `mthds/docs/spec/native-concepts.md`. This module is the runtime copy of that
pinned set: crate materialization looks definitions up here instead of reflecting over the runtime
content classes, so two independent implementations byte-agree on materialized natives (and
therefore on crate fingerprints). Any edit here is a standard change and must land in the spec
page first; the consistency test in `tests/unit/pipelex/codegen/` proves each runtime content
class still matches its pinned blueprint, so the two can never drift silently.

The set below is the MTHDS 1.0.0 pinned set. Version-keyed lookup can come when a second
standard version exists; today `mthds_version` on the crate records which set was used.
"""

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode

PINNED_NATIVES_MTHDS_VERSION = "1.0.0"


def make_pinned_native_blueprint(native_code: NativeConceptCode) -> ConceptBlueprint:
    """Build the pinned normative `ConceptBlueprint` for a native concept (fresh instance per call)."""
    return ConceptBlueprint(
        source=None,
        description=_pinned_description(native_code),
        structure=_pinned_structure(native_code),
    )


def _pinned_description(native_code: NativeConceptCode) -> str:
    match native_code:
        case NativeConceptCode.DYNAMIC:
            return "A dynamic concept"
        case NativeConceptCode.TEXT:
            return "A text"
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
            return {
                "text": _text_field(description="The text", required=True),
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
            return {
                "inner_html": _text_field(description="The inner HTML of the content", required=True),
                "css_class": _text_field(description="The CSS class of the content", required=True),
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
            return {
                "json_obj": ConceptStructureBlueprint(
                    description="The JSON object",
                    type=ConceptStructureBlueprintFieldType.DICT,
                    key_type="text",
                    value_type="Any",
                    required=True,
                ),
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


def _text_field(*, description: str, required: bool = False) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint(description=description, type=ConceptStructureBlueprintFieldType.TEXT, required=required)
