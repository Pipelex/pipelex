import datetime
from typing import Any

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_controllers.binding.binding_concept_resolvers import BlueprintConceptWalkResolver
from pipelex.pipe_controllers.binding.binding_derivation import BindingRoot

FieldType = ConceptStructureBlueprintFieldType


def make_field(*, field_type: FieldType | None, required: bool = False, **kwargs: Any) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint(description="A field", type=field_type, required=required, **kwargs)


CONCEPTS: dict[str, ConceptBlueprint | str] = {
    "billing.Invoice": ConceptBlueprint(
        description="An invoice received from a supplier",
        structure={
            "supplier_name": make_field(field_type=FieldType.TEXT, required=True),
            "total": make_field(field_type=FieldType.NUMBER, required=True),
            "item_count": make_field(field_type=FieldType.INTEGER, required=True),
            "paid": make_field(field_type=FieldType.BOOLEAN, required=True),
            "issued_on": make_field(field_type=FieldType.DATE, required=True),
            "issued_at": make_field(field_type=FieldType.DATETIME, required=True),
            "cutoff": make_field(field_type=FieldType.TIME, required=True),
            "priority": make_field(field_type=None, choices=["low", "high"], required=True),
            "metadata": make_field(field_type=FieldType.DICT, key_type="text", value_type="text", required=True),
            "supplier": make_field(field_type=FieldType.CONCEPT, concept_ref="Supplier", required=True),
            "lines": make_field(field_type=FieldType.LIST, item_type="concept", item_concept_ref="InvoiceLine", required=True),
            "tags": make_field(field_type=FieldType.LIST, item_type="text", required=True),
            "attachments": make_field(field_type=FieldType.LIST, required=True),
            "scan": make_field(field_type=FieldType.CONCEPT, concept_ref="native.Document"),
            "pages": make_field(field_type=FieldType.LIST, item_type="concept", item_concept_ref="native.Page"),
            "amount_due": make_field(field_type=FieldType.CONCEPT, concept_ref="native.Number", required=True),
            "note": make_field(field_type=FieldType.TEXT),
            "currency": make_field(field_type=FieldType.TEXT, default_value="EUR"),
            "remark": make_field(field_type=FieldType.CONCEPT, concept_ref="Remark", required=True),
        },
    ),
    "billing.Supplier": ConceptBlueprint(
        description="A supplier",
        structure={
            "name": make_field(field_type=FieldType.TEXT, required=True),
            "address": make_field(field_type=FieldType.CONCEPT, concept_ref="Address", required=True),
        },
    ),
    "billing.Address": ConceptBlueprint(description="A postal address", structure={"city": make_field(field_type=FieldType.TEXT, required=True)}),
    "billing.InvoiceLine": ConceptBlueprint(description="One line of an invoice", structure={"amount": make_field(field_type=FieldType.NUMBER)}),
    "billing.Receipt": ConceptBlueprint(description="A receipt, an invoice once paid", refines="Invoice"),
    "billing.Remark": "A remark written on an invoice",
    "billing.Memo": ConceptBlueprint(description="A memo with no structure"),
    "billing.MemoCopy": ConceptBlueprint(description="A copy of a memo", refines="Memo"),
    "billing.Caption": ConceptBlueprint(description="A caption", refines="Text"),
    "billing.Shipment": ConceptBlueprint(
        description="A shipment of parcels",
        structure={"parcels": make_field(field_type=FieldType.LIST, item_type="concept", item_concept_ref="Parcel", required=True)},
    ),
    "billing.Parcel": ConceptBlueprint(description="A parcel", structure={"weight": make_field(field_type=FieldType.NUMBER, required=True)}),
    "billing.Manifest": ConceptBlueprint(
        description="A manifest of shipments",
        structure={"shipments": make_field(field_type=FieldType.LIST, item_type="concept", item_concept_ref="Shipment", required=True)},
    ),
    "billing.Crate": ConceptBlueprint(
        description="A crate holding anything",
        structure={
            "contents": make_field(field_type=FieldType.CONCEPT, concept_ref="native.Anything", required=True),
            "extras": make_field(field_type=FieldType.LIST, item_type="concept", item_concept_ref="native.Anything", required=True),
        },
    ),
}


def make_root(concept_ref: str, *, multiplicity: VariableMultiplicity | None = None) -> BindingRoot:
    return BindingRoot(concept_ref=concept_ref, multiplicity=multiplicity)


RESOLVER = BlueprintConceptWalkResolver(concept_blueprints=CONCEPTS)

INVOICE = BindingRoot(concept_ref="billing.Invoice")


# The content the runtime holds for the concepts above, as the structure generator would make it: raw Python
# values for plain fields, content classes for concept fields.
class AddressRecord(StructuredContent):
    city: str


class SupplierRecord(StructuredContent):
    name: str
    address: AddressRecord


class InvoiceLineRecord(StructuredContent):
    amount: float | None = None


class InvoiceRecord(StructuredContent):
    supplier_name: str
    total: float
    item_count: int
    paid: bool
    issued_on: datetime.date
    issued_at: datetime.datetime
    cutoff: datetime.time
    priority: str
    metadata: dict[str, str]
    supplier: SupplierRecord
    lines: list[InvoiceLineRecord]
    tags: list[str]
    scan: DocumentContent | None = None
    pages: list[PageContent] | None = None
    note: str | None = None
    currency: str = "EUR"


class ParcelRecord(StructuredContent):
    weight: float


class ShipmentRecord(StructuredContent):
    parcels: list[ParcelRecord]


class CrateRecord(StructuredContent):
    """A `native.Anything` field is generated as `Any`, so it holds a raw value of any type."""

    contents: Any
    extras: list[Any]


INVOICE_ISSUED_AT = datetime.datetime(2026, 3, 14, 9, 30, tzinfo=datetime.UTC)


def make_invoice_record(*, note: str | None = None, scan: DocumentContent | None = None) -> InvoiceRecord:
    """A fresh invoice each call, so a test mutating one never leaks into another."""
    return InvoiceRecord(
        supplier_name="Atelier Morvan",
        total=1250.5,
        item_count=3,
        paid=True,
        issued_on=datetime.date(2026, 3, 14),
        issued_at=INVOICE_ISSUED_AT,
        cutoff=datetime.time(17, 0),
        priority="high",
        metadata={"order_ref": "PO-118"},
        supplier=SupplierRecord(name="Atelier Morvan", address=AddressRecord(city="Quimper")),
        lines=[InvoiceLineRecord(amount=1000.0), InvoiceLineRecord(amount=None), InvoiceLineRecord(amount=250.5)],
        tags=["urgent", "export"],
        scan=scan,
        note=note,
    )


def make_page(*, text: str, view: ImageContent | None) -> PageContent:
    return PageContent(text_and_images=TextAndImagesContent(text=TextContent(text=text)), page_view=view)


def make_view(*, url: str) -> ImageContent:
    """An image carrying every field a whole-value copy must keep."""
    return ImageContent(
        url=url,
        caption=f"The view at {url}",
        source_prompt="A catalog page, photographed flat",
        source_negative_prompt="No glare",
        mime_type="image/png",
        width=800,
        height=1200,
    )
