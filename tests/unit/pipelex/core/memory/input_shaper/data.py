"""Shared fixtures data for the InputShaper unit tests.

Defines a small library of concepts covering each D5 arm — Text/Number/YesNo/Date/Image/Document
refinements plus structured concepts — and a helper to build an ``InputStuffSpecs`` fixture from a
list of ``(variable_name, concept_ref, multiplicity)`` entries resolved against the current library.
"""

from pydantic import Field

from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent

SHAPER_TEST_DOMAIN = "shaper_test"


class Question(TextContent):
    """Refines native Text — mirrors the subclass the refinement machinery generates for `refines = "Text"`."""


class Priority(NumberContent):
    """Refines native Number — the subclass generated for `refines = "Number"`."""


class Verdict(YesNoContent):
    """Refines native YesNo."""


class Deadline(DateContent):
    """Refines native Date."""


class OpeningTime(TimeContent):
    """Refines native Time."""


class Photo(ImageContent):
    """Refines native Image."""


class Exhibit(DocumentContent):
    """Refines native Document."""


# Structured test concepts carry a `Shaper`-prefixed name so their registration in the by-name
# global class registry can never be shadowed by an identically-named StructuredContent from another
# test suite (e.g. an integration test's `Person`/`Invoice`). The concept code matches the class name
# (the bottom-up factory maps a prebuilt StuffContent to its concept by class name), so both are
# prefixed; the `shaper_test.<Code>` refs used in the tests are `shaper_test.Shaper<Name>`.
class ShaperInvoice(StructuredContent):
    invoice_number: str = Field(description="The invoice number")
    amount: float = Field(description="The invoice amount")


class ShaperPerson(StructuredContent):
    name: str = Field(description="The person's name")


class ShaperWeird(StructuredContent):
    """A pathological structure whose fields are literally `concept` and `content` (collision-rule test)."""

    concept: str = Field(description="A field named concept")
    content: str = Field(description="A field named content")


# Non-StructuredContent refinements — registered explicitly (the refinement machinery would register
# a subclass like these for a `refines = "<native>"` concept).
REFINING_CLASSES = [Question, Priority, Verdict, Deadline, OpeningTime, Photo, Exhibit]

# (concept_code, structure_class_name, refines) for every test concept.
CONCEPT_DEFS: list[tuple[str, str, str | None]] = [
    ("Question", "Question", "native.Text"),
    ("Priority", "Priority", "native.Number"),
    ("Verdict", "Verdict", "native.YesNo"),
    ("Deadline", "Deadline", "native.Date"),
    ("OpeningTime", "OpeningTime", "native.Time"),
    ("Photo", "Photo", "native.Image"),
    ("Exhibit", "Exhibit", "native.Document"),
    ("ShaperInvoice", "ShaperInvoice", None),
    ("ShaperPerson", "ShaperPerson", None),
    ("ShaperWeird", "ShaperWeird", None),
]

CONCEPT_REFS: list[str] = [f"{SHAPER_TEST_DOMAIN}.{concept_code}" for concept_code, _, _ in CONCEPT_DEFS]


def build_input_specs(entries: list[tuple[str, str, VariableMultiplicity | None]]) -> InputStuffSpecs:
    """Build an ``InputStuffSpecs`` from ``(variable_name, concept_ref, multiplicity)`` entries.

    Concepts are resolved against the current concept library, so this must run after the
    ``shaper_library`` fixture has registered the test concepts.
    """
    from pipelex.method_hub import get_concept_library  # noqa: PLC0415

    library = get_concept_library()
    root: dict[str, StuffSpec] = {}
    for variable_name, concept_ref, multiplicity in entries:
        concept = library.get_required_concept(concept_ref=concept_ref)
        root[variable_name] = StuffSpec(concept=concept, multiplicity=multiplicity)
    return InputStuffSpecs(root=root)
