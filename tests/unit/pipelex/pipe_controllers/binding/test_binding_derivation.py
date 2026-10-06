import pytest

from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.pipe_controllers.binding.binding_derivation import BindingRoot, BindingValueKind, derive_binding
from tests.unit.pipelex.pipe_controllers.binding.test_data import INVOICE, RESOLVER, make_root

# The segment a caller of `provenance_path` chooses to stand for any item of a list.
_ITEM = "[]"


class TestBindingDerivationTable:
    @pytest.mark.parametrize(
        ("path", "root", "concept_ref", "multiplicity", "leaf_kind"),
        [
            # `type = "concept"`: the referenced concept, walked by the next segment
            ("invoice.supplier", INVOICE, "billing.Supplier", None, BindingValueKind.CONCEPT),
            ("invoice.supplier.address.city", INVOICE, "native.Text", None, BindingValueKind.TEXT),
            # `type = "list"` of concepts: the item concept, crossing a list
            ("invoice.lines", INVOICE, "billing.InvoiceLine", True, BindingValueKind.CONCEPT),
            ("invoice.lines.amount", INVOICE, "native.Number", True, BindingValueKind.NUMBER),
            # `type = "text"` and `choices`: a text leaf
            ("invoice.supplier_name", INVOICE, "native.Text", None, BindingValueKind.TEXT),
            ("invoice.priority", INVOICE, "native.Text", None, BindingValueKind.TEXT),
            # `type = "number"` and `"integer"`: a number leaf
            ("invoice.total", INVOICE, "native.Number", None, BindingValueKind.NUMBER),
            ("invoice.item_count", INVOICE, "native.Number", None, BindingValueKind.NUMBER),
            # `type = "boolean"`: a yes/no leaf
            ("invoice.paid", INVOICE, "native.YesNo", None, BindingValueKind.YES_NO),
            # `type = "date"` and `"datetime"`: a date leaf
            ("invoice.issued_on", INVOICE, "native.Date", None, BindingValueKind.DATE),
            ("invoice.issued_at", INVOICE, "native.Date", None, BindingValueKind.DATETIME),
            # `type = "time"`: a time leaf
            ("invoice.cutoff", INVOICE, "native.Time", None, BindingValueKind.TIME),
            # `type = "list"` of a scalar: that scalar's native concept, crossing a list
            ("invoice.tags", INVOICE, "native.Text", True, BindingValueKind.TEXT),
            # `type = "dict"`: a JSON leaf
            ("invoice.metadata", INVOICE, "native.JSON", None, BindingValueKind.JSON),
            # A native concept walks through its pinned definition
            ("page.page_view", make_root("native.Page"), "native.Image", None, BindingValueKind.CONCEPT),
            ("page.page_view.caption", make_root("native.Page"), "native.Text", None, BindingValueKind.TEXT),
            ("invoice.scan.url", INVOICE, "native.Text", None, BindingValueKind.TEXT),
            # A concept field may end on a native holding its value in a single field
            ("invoice.amount_due", INVOICE, "native.Number", None, BindingValueKind.CONCEPT),
            # A path may end on a concept declared with a description alone
            ("invoice.remark", INVOICE, "billing.Remark", None, BindingValueKind.CONCEPT),
            # A refined concept walks the structure it inherits
            ("receipt.supplier.name", make_root("billing.Receipt"), "native.Text", None, BindingValueKind.TEXT),
            # A list root maps the path over its items, and a fixed count becomes a variable-length list
            ("pages.page_view", make_root("native.Page", multiplicity=True), "native.Image", True, BindingValueKind.CONCEPT),
            ("pages.page_view", make_root("native.Page", multiplicity=3), "native.Image", True, BindingValueKind.CONCEPT),
            # Two lists crossed flatten into one
            ("shipments.parcels", make_root("billing.Shipment", multiplicity=True), "billing.Parcel", True, BindingValueKind.CONCEPT),
            ("invoice.pages.page_view", INVOICE, "native.Image", True, BindingValueKind.CONCEPT),
            # A bare name keeps its root's concept and multiplicity unchanged
            ("departure_board", make_root("rail.DepartureBoard"), "rail.DepartureBoard", None, BindingValueKind.CONCEPT),
            ("pages", make_root("native.Page", multiplicity=3), "native.Page", 3, BindingValueKind.CONCEPT),
        ],
    )
    def test_derives_the_concept_and_multiplicity(
        self,
        path: str,
        root: BindingRoot,
        concept_ref: str,
        multiplicity: VariableMultiplicity | None,
        leaf_kind: BindingValueKind,
    ):
        derivation = derive_binding(path=path, root=root, resolver=RESOLVER)

        assert derivation.concept_ref == concept_ref
        assert derivation.multiplicity == multiplicity
        assert derivation.leaf_kind == leaf_kind

    @pytest.mark.parametrize(
        ("path", "root", "may_find_nothing", "first_optional_path"),
        [
            # A required field is never absent, and neither is a field with a default value
            ("invoice.total", INVOICE, False, None),
            ("invoice.currency", INVOICE, False, None),
            # A field that is neither required nor defaulted may hold nothing, at the leaf or before it
            ("invoice.note", INVOICE, True, "invoice.note"),
            ("invoice.scan.url", INVOICE, True, "invoice.scan"),
            ("page.page_view", make_root("native.Page"), True, "page.page_view"),
            # A list result is never absent, even when a field before the first list may hold nothing
            ("invoice.lines.amount", INVOICE, False, None),
            ("invoice.pages.page_view", INVOICE, False, None),
            ("pages.page_view", make_root("native.Page", multiplicity=True), False, None),
            # A bare name adds no absence of its own
            ("invoice", INVOICE, False, None),
        ],
    )
    def test_derives_the_static_absence(self, path: str, root: BindingRoot, may_find_nothing: bool, first_optional_path: str | None):
        derivation = derive_binding(path=path, root=root, resolver=RESOLVER)

        assert derivation.may_find_nothing is may_find_nothing
        assert derivation.first_optional_path == first_optional_path

    @pytest.mark.parametrize(
        ("path", "root", "provenance_path"),
        [
            # A single value sits at its path's fields
            ("invoice.total", INVOICE, ("total",)),
            ("invoice.supplier.address.city", INVOICE, ("supplier", "address", "city")),
            # A bare name is its root's own value, a list root's included
            ("invoice", INVOICE, ()),
            ("pages", make_root("native.Page", multiplicity=True), ()),
            # One list field of a single root is the list at that field's path
            ("invoice.lines", INVOICE, ("lines",)),
            # A list gathered across items whose last field is a list: the item segment follows a list root and every list crossed before
            ("shipments.parcels", make_root("billing.Shipment", multiplicity=True), (_ITEM, "parcels")),
            ("manifest.shipments.parcels", make_root("billing.Manifest"), ("shipments", _ITEM, "parcels")),
            ("manifests.shipments.parcels", make_root("billing.Manifest", multiplicity=3), (_ITEM, "shipments", _ITEM, "parcels")),
            # A list gathered from a field that is not itself a list holds values that are items of no list at one path
            ("pages.page_view", make_root("native.Page", multiplicity=True), None),
            ("invoice.lines.amount", INVOICE, None),
            ("invoice.pages.page_view", INVOICE, None),
        ],
    )
    def test_provenance_path_places_the_item_segment_after_every_list_crossed(
        self, path: str, root: BindingRoot, provenance_path: tuple[str, ...] | None
    ):
        derivation = derive_binding(path=path, root=root, resolver=RESOLVER)

        assert derivation.provenance_path(item_segment=_ITEM) == provenance_path

    def test_segments_record_the_lists_they_cross(self):
        derivation = derive_binding(path="invoice.lines.amount", root=INVOICE, resolver=RESOLVER)

        assert [(segment.name, segment.crosses_list) for segment in derivation.segments] == [("lines", True), ("amount", False)]
        assert derivation.root_name == "invoice"
        assert not derivation.is_bare_name
