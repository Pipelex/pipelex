import datetime
from typing import cast

import pytest

from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.pipe_controllers.binding.binding_derivation import BindingDerivation, BindingRoot, derive_binding
from pipelex.pipe_controllers.binding.binding_value import FoundNothing, bind_content
from pipelex.pipe_controllers.binding.exceptions import BindingStepRunError
from tests.unit.pipelex.pipe_controllers.binding.test_data import (
    INVOICE,
    INVOICE_ISSUED_AT,
    RESOLVER,
    InvoiceLineRecord,
    ParcelRecord,
    ShipmentRecord,
    SupplierRecord,
    make_invoice_record,
    make_page,
    make_root,
    make_view,
)


def _derive(path: str, *, root: BindingRoot = INVOICE) -> BindingDerivation:
    return derive_binding(path=path, root=root, resolver=RESOLVER)


def _list_items(content: StuffContent | FoundNothing) -> list[StuffContent]:
    assert isinstance(content, ListContent)
    return list(cast("ListContent[StuffContent]", content).items)


class TestBindContent:
    @pytest.mark.parametrize(
        ("path", "expected_content"),
        [
            pytest.param("invoice.supplier_name", TextContent(text="Atelier Morvan"), id="V1-text"),
            pytest.param("invoice.total", NumberContent(number=1250.5), id="V2-number"),
            pytest.param("invoice.item_count", NumberContent(number=3), id="V3-integer"),
            pytest.param("invoice.paid", YesNoContent(yes_no=True), id="V4-boolean"),
            pytest.param("invoice.issued_on", DateContent(date=datetime.date(2026, 3, 14)), id="V5-date"),
            pytest.param("invoice.issued_at", DateContent(date=INVOICE_ISSUED_AT.date(), time=INVOICE_ISSUED_AT.timetz()), id="V5-datetime"),
            pytest.param("invoice.cutoff", TimeContent(time=datetime.time(17, 0)), id="V5-time"),
            pytest.param("invoice.priority", TextContent(text="high"), id="V6-choices"),
            pytest.param("invoice.metadata", JSONContent(json_obj={"order_ref": "PO-118"}), id="V7-dict"),
            pytest.param("invoice.supplier.address.city", TextContent(text="Quimper"), id="V9-nested"),
        ],
    )
    def test_a_plain_value_is_stored_as_the_native_its_field_derives(self, path: str, expected_content: StuffContent) -> None:
        """The structure classes hold raw Python values; the binding stores each as the native concept the derivation names."""
        bound = bind_content(root_content=make_invoice_record(), derivation=_derive(path))

        assert bound == expected_content
        assert type(bound) is type(expected_content)

    def test_v8_a_concept_field_is_copied_whole(self) -> None:
        invoice = make_invoice_record()

        bound = bind_content(root_content=invoice, derivation=_derive("invoice.supplier"))

        assert isinstance(bound, SupplierRecord)
        assert bound == invoice.supplier
        assert bound is not invoice.supplier
        assert bound.address is not invoice.supplier.address

    def test_v11_a_list_of_concepts_binds_a_list_of_copies(self) -> None:
        invoice = make_invoice_record()

        items = _list_items(bind_content(root_content=invoice, derivation=_derive("invoice.lines")))

        assert items == invoice.lines
        assert all(item is not original for item, original in zip(items, invoice.lines, strict=True))

    def test_a_list_of_plain_values_binds_a_list_of_natives(self) -> None:
        items = _list_items(bind_content(root_content=make_invoice_record(), derivation=_derive("invoice.tags")))

        assert items == [TextContent(text="urgent"), TextContent(text="export")]

    def test_v13_v15_a_list_crossed_mid_path_maps_and_drops_items_holding_nothing(self) -> None:
        """The second line has no amount: it is dropped from the list, which is never an absence."""
        items = _list_items(bind_content(root_content=make_invoice_record(), derivation=_derive("invoice.lines.amount")))

        assert items == [NumberContent(number=1000.0), NumberContent(number=250.5)]

    def test_v16_an_empty_list_binds_an_empty_list(self) -> None:
        invoice = make_invoice_record()
        invoice.lines = []

        bound = bind_content(root_content=invoice, derivation=_derive("invoice.lines.amount"))

        assert _list_items(bound) == []

    def test_v12_v15_a_list_root_maps_its_items_and_drops_pages_without_a_view(self) -> None:
        pages = ListContent[StuffContent](
            items=[
                make_page(text="Cover", view=make_view(url="https://example.com/cover.png")),
                make_page(text="Blank", view=None),
                make_page(text="Index", view=make_view(url="https://example.com/index.png")),
            ]
        )

        items = _list_items(bind_content(root_content=pages, derivation=_derive("pages.page_view", root=make_root("native.Page", multiplicity=True))))

        assert items == [make_view(url="https://example.com/cover.png"), make_view(url="https://example.com/index.png")]

    def test_v14_two_lists_crossed_flatten_into_one(self) -> None:
        shipments = ListContent[StuffContent](
            items=[
                ShipmentRecord(parcels=[ParcelRecord(weight=1.5), ParcelRecord(weight=2.0)]),
                ShipmentRecord(parcels=[]),
                ShipmentRecord(parcels=[ParcelRecord(weight=4.25)]),
            ]
        )

        items = _list_items(
            bind_content(root_content=shipments, derivation=_derive("shipments.parcels", root=make_root("billing.Shipment", multiplicity=True)))
        )

        assert items == [ParcelRecord(weight=1.5), ParcelRecord(weight=2.0), ParcelRecord(weight=4.25)]

    def test_v17_an_optional_field_holding_a_value_binds_it(self) -> None:
        bound = bind_content(root_content=make_invoice_record(note="Deliver to the back door"), derivation=_derive("invoice.note"))

        assert bound == TextContent(text="Deliver to the back door")

    @pytest.mark.parametrize(
        ("path", "empty_path"),
        [
            pytest.param("invoice.note", "invoice.note", id="V18-optional-field-absent"),
            pytest.param("invoice.scan.url", "invoice.scan", id="V19-intermediate-none"),
        ],
    )
    def test_a_single_path_reaching_nothing_names_the_segment_that_held_nothing(self, path: str, empty_path: str) -> None:
        bound = bind_content(root_content=make_invoice_record(), derivation=_derive(path))

        assert bound == FoundNothing(empty_path=empty_path)

    def test_a_present_intermediate_value_is_walked_through(self) -> None:
        invoice = make_invoice_record(scan=DocumentContent(url="https://example.com/scan.pdf"))

        bound = bind_content(root_content=invoice, derivation=_derive("invoice.scan.url"))

        assert bound == TextContent(text="https://example.com/scan.pdf")

    def test_v24_a_bare_name_binds_a_deep_copy_of_the_whole_value(self) -> None:
        invoice = make_invoice_record()

        bound = bind_content(root_content=invoice, derivation=_derive("invoice"))

        assert bound == invoice
        assert bound is not invoice
        assert isinstance(bound, type(invoice))
        assert bound.supplier is not invoice.supplier

    def test_c1_the_bound_value_is_isolated_from_its_root_both_ways(self) -> None:
        invoice = make_invoice_record()
        bound = bind_content(root_content=invoice, derivation=_derive("invoice.supplier"))
        assert isinstance(bound, SupplierRecord)

        invoice.supplier.address.city = "Brest"
        assert bound.address.city == "Quimper"

        bound.name = "Someone else"
        assert invoice.supplier.name == "Atelier Morvan"

    def test_c1_a_bound_list_is_isolated_from_its_root(self) -> None:
        invoice = make_invoice_record()
        items = _list_items(bind_content(root_content=invoice, derivation=_derive("invoice.lines")))

        invoice.lines[0].amount = 1.0
        invoice.lines.append(InvoiceLineRecord(amount=9.0))

        assert items == [InvoiceLineRecord(amount=1000.0), InvoiceLineRecord(amount=None), InvoiceLineRecord(amount=250.5)]

    def test_c1_a_bound_dict_is_isolated_from_its_root(self) -> None:
        invoice = make_invoice_record()
        bound = bind_content(root_content=invoice, derivation=_derive("invoice.metadata"))
        assert isinstance(bound, JSONContent)

        invoice.metadata["order_ref"] = "PO-999"

        assert bound.json_obj == {"order_ref": "PO-118"}

    def test_c4_a_bound_image_keeps_every_field(self) -> None:
        view = make_view(url="https://example.com/cover.png")
        page = make_page(text="Cover", view=view)

        bound = bind_content(root_content=page, derivation=_derive("page.page_view", root=make_root("native.Page")))

        assert isinstance(bound, ImageContent)
        assert bound.model_dump() == view.model_dump()
        assert bound.caption == "The view at https://example.com/cover.png"
        assert bound.source_prompt == "A catalog page, photographed flat"
        assert bound.source_negative_prompt == "No glare"
        assert bound is not view

    def test_a_value_contradicting_its_declared_structure_is_a_run_error(self) -> None:
        """The structure says `supplier` holds a Supplier; content lacking the field is a broken contract, not an absence."""
        with pytest.raises(BindingStepRunError, match="has no such field"):
            bind_content(root_content=ParcelRecord(weight=1.0), derivation=_derive("invoice.supplier.name"))

    def test_a_plain_value_of_the_wrong_kind_is_a_run_error(self) -> None:
        invoice = make_invoice_record()
        invoice.supplier_name = cast("str", 12)

        with pytest.raises(BindingStepRunError, match="cannot be stored as"):
            bind_content(root_content=invoice, derivation=_derive("invoice.supplier_name"))
