from typing import Any, ClassVar, NamedTuple

from pipelex.core.memory.absence import AbsenceKind
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, PRIVATE_BINDING_NAME_PREFIX


class Bound(NamedTuple):
    """A value the run must leave in working memory: its concept, and the fields its content must hold.

    The content is matched as a subset: every key written here must be present with this value, and a list
    must have exactly these items, each matched the same way. Fields the run stamps (an image's mime type,
    a relocated url) are left out.
    """

    concept_ref: str
    content: Any


class Absent(NamedTuple):
    """A name the run must leave without a value, with a recorded absence of this kind."""

    kind: AbsenceKind


class OfflineRunExpectations:
    """What each offline-tier corpus entry leaves in working memory once run with its `inputs.json`, keyed by entry name.

    A corpus entry holds no expected outputs, so the expectations live here. Every offline entry has one, the
    entries that predate the binding step included, so the runner pins what each of them produces.
    """

    BY_ENTRY: ClassVar[dict[str, dict[str, Bound | Absent]]] = {
        "operator_compose_delivery_docket": {
            MAIN_STUFF_NAME: Bound(
                concept_ref="deliveries.DeliveryDocket",
                content={"weight_kg": 3.4, "destination": "Quimper", "carrier": "Morvan et Fils"},
            ),
        },
        "operator_doc_gen_door_notice": {
            MAIN_STUFF_NAME: Bound(
                concept_ref="shop_notices.PrintedNotice", content={"mime_type": "application/pdf", "filename": "notice-Boulangerie-Kerlann.pdf"}
            ),
        },
        "feature_binding_step_invoice_fields": {
            "supplier_name": Bound(concept_ref="native.Text", content={"text": "Atelier Morvan"}),
            "total_amount": Bound(concept_ref="native.Number", content={"number": 1250.5}),
            "line_count": Bound(concept_ref="native.Number", content={"number": 3}),
            "priority": Bound(concept_ref="native.Text", content={"text": "urgent"}),
            "order_details": Bound(concept_ref="native.JSON", content={"json_obj": {"order_ref": "PO-118", "delivery_slot": "morning"}}),
            "supplier_city": Bound(concept_ref="native.Text", content={"text": "Quimper"}),
            "acknowledgement": Bound(
                concept_ref="native.Text",
                content={
                    "text": (
                        "Received from Atelier Morvan of Quimper: 3 lines, 1250.5 euros due, urgent.\n"
                        'Order details: {\n    "order_ref": "PO-118",\n    "delivery_slot": "morning"\n}'
                    )
                },
            ),
        },
        "feature_binding_step_parcel_recipient": {
            "fragile": Bound(concept_ref="native.YesNo", content={"yes_no": True}),
            "recipient": Bound(
                concept_ref="parcel_counter.Recipient",
                content={"name": "Maëlle Le Gall", "street": "12 rue des Tanneurs", "town": "Morlaix"},
            ),
            "label": Bound(
                concept_ref="parcel_counter.ParcelLabel",
                content={"addressee": "Maëlle Le Gall", "street": "12 rue des Tanneurs", "town": "Morlaix", "handling": "Fragile, handle with care"},
            ),
        },
        "feature_binding_step_departure_times": {
            "day": Bound(concept_ref="native.Date", content={"date": "2026-04-02"}),
            "scheduled_at": Bound(concept_ref="native.Date", content={"date": "2026-04-02", "time": "08:15:00+02:00"}),
            "boarding_time": Bound(concept_ref="native.Time", content={"time": "07:45:00"}),
        },
        "feature_binding_step_page_views": {
            "cover_view": Bound(
                concept_ref="native.Image",
                content={"caption": "The spring cover", "source_prompt": "A cover photographed flat"},
            ),
            "page_views": Bound(
                concept_ref="native.Image",
                content={"items": [{"caption": "Garden chairs on a lawn"}, {"caption": "Two parasols"}]},
            ),
        },
        "feature_binding_step_order_lines": {
            "lines": Bound(
                concept_ref="order_desk.OrderLine",
                content={
                    "items": [
                        {"article": "Linen tea towel", "amount": 12.5},
                        {"article": "Sample swatch", "amount": None},
                        {"article": "Enamel mug", "amount": 9.0},
                    ]
                },
            ),
            "amounts": Bound(concept_ref="native.Number", content={"items": [{"number": 12.5}, {"number": 9.0}]}),
            "backorder_amounts": Bound(concept_ref="native.Number", content={"items": []}),
        },
        "feature_binding_step_delivery_note": {
            "morning_note": Bound(concept_ref="native.Text", content={"text": "Gate code changed to 4471"}),
            "evening_note": Absent(kind=AbsenceKind.DECLARED_ABSENT),
            "board_notice": Bound(concept_ref="native.Text", content={"text": "Morning: Gate code changed to 4471\nEvening: no note"}),
            "evening_reminder": Absent(kind=AbsenceKind.SKIPPED),
        },
        "feature_binding_step_missing_values": {
            "invoice_number": Bound(concept_ref="native.Text", content={"text": "F-2026-0412"}),
            "scan_link": Absent(kind=AbsenceKind.DECLARED_ABSENT),
            "copy_total": Absent(kind=AbsenceKind.SKIPPED),
            "filing_note": Bound(concept_ref="native.Text", content={"text": "Invoice F-2026-0412 filed.\nNo scan on file.\nNo courtesy copy."}),
        },
        "feature_binding_step_receipt_inherited": {
            "amount_paid": Bound(concept_ref="native.Number", content={"number": 42.8}),
            "line": Bound(concept_ref="native.Text", content={"text": "Paid: 42.8 euros"}),
        },
        "feature_binding_step_board_rename": {
            "board": Bound(concept_ref="station_board.DepartureBoard", content={"station": "Landerneau", "next_train": "Brest"}),
            "announcement": Bound(concept_ref="native.Text", content={"text": "At Landerneau, the next train goes to Brest."}),
        },
        "feature_binding_step_batch_views": {
            "page_views": Bound(concept_ref="native.Image", content={"items": [{"caption": "Garden chairs on a lawn"}, {"caption": "Two parasols"}]}),
            "index_lines": Bound(
                concept_ref="native.Text",
                content={"items": [{"text": "Photograph: Garden chairs on a lawn"}, {"text": "Photograph: Two parasols"}]},
            ),
        },
        # A dotted `batch_over` binds its path under a private name, then batches over it: the bound list is kept there.
        "feature_binding_step_batch_over_catalog_pages": {
            f"{PRIVATE_BINDING_NAME_PREFIX}catalog_pages": Bound(
                concept_ref="nursery_catalog.CatalogPage", content={"items": [{"title": "Climbing roses"}, {"title": "Fruit trees"}]}
            ),
            "index_lines": Bound(concept_ref="native.Text", content={"items": [{"text": "Page: Climbing roses"}, {"text": "Page: Fruit trees"}]}),
        },
        "feature_binding_step_batch_over_catalogs": {
            f"{PRIVATE_BINDING_NAME_PREFIX}catalogs_pages": Bound(
                concept_ref="furniture_catalogs.CatalogPage",
                content={"items": [{"title": "Garden chairs"}, {"title": "Parasols"}, {"title": "Bookcases"}]},
            ),
            "index_lines": Bound(
                concept_ref="native.Text",
                content={"items": [{"text": "Page: Garden chairs"}, {"text": "Page: Parasols"}, {"text": "Page: Bookcases"}]},
            ),
        },
        "feature_binding_step_batch_over_equivalence": {
            f"{PRIVATE_BINDING_NAME_PREFIX}order_lines": Bound(
                concept_ref="order_pricing.OrderLine",
                content={"items": [{"article": "Linen tea towel", "amount": 12.5}, {"article": "Enamel mug", "amount": 9.0}]},
            ),
            "lines": Bound(
                concept_ref="order_pricing.OrderLine",
                content={"items": [{"article": "Linen tea towel", "amount": 12.5}, {"article": "Enamel mug", "amount": 9.0}]},
            ),
            "priced_by_path": Bound(
                concept_ref="native.Text", content={"items": [{"text": "Linen tea towel: 12.5 euros"}, {"text": "Enamel mug: 9.0 euros"}]}
            ),
            "priced_by_binding": Bound(
                concept_ref="native.Text", content={"items": [{"text": "Linen tea towel: 12.5 euros"}, {"text": "Enamel mug: 9.0 euros"}]}
            ),
        },
        "feature_binding_step_parallel_root": {
            "price_tag": Bound(concept_ref="market_stall.PriceTag", content={"produce": "Plougastel strawberries", "price": 3.2}),
            "price": Bound(concept_ref="native.Number", content={"number": 3.2}),
            "price_line": Bound(concept_ref="native.Text", content={"text": "3.2 euros a kilo"}),
        },
        "feature_binding_step_nested_sequence": {
            "loaf_count": Bound(concept_ref="native.Number", content={"number": 12}),
            "confirmation": Bound(concept_ref="native.Text", content={"text": "Confirmed: 12 loaves"}),
        },
        "feature_binding_step_shipment_parcels": {
            "parcels": Bound(
                concept_ref="depot_loading.Parcel",
                content={"items": [{"tracking_number": "QP-1001"}, {"tracking_number": "QP-1002"}, {"tracking_number": "BR-2001"}]},
            ),
            "loading_list": Bound(concept_ref="native.Text", content={"text": "- QP-1001\n- QP-1002\n- BR-2001\n"}),
        },
    }
