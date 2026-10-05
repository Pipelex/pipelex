from typing import Any

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
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
}


def make_root(concept_ref: str, *, multiplicity: VariableMultiplicity | None = None) -> BindingRoot:
    return BindingRoot(concept_ref=concept_ref, multiplicity=multiplicity)


RESOLVER = BlueprintConceptWalkResolver(concept_blueprints=CONCEPTS)

INVOICE = BindingRoot(concept_ref="billing.Invoice")
