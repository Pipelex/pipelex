from typing import Any, ClassVar


class PipeDocGenTestData:
    """An invoice bundle whose PipeDocGen step each test sets: its format, its template and its filename."""

    STEP_SLOT: ClassVar[str] = "#STEP_FIELDS#"

    BUNDLE_MTHDS: ClassVar[str] = """
domain = "doc_gen_tests"
description = "Printing an invoice"
main_pipe = "print_invoice"

[concept.LineItem]
description = "One line of an invoice"

[concept.LineItem.structure]
description = { type = "text", description = "What was sold", required = true }
amount      = { type = "number", description = "The line's amount, in euros", required = true }

[concept.Invoice]
description = "An invoice to print"

[concept.Invoice.structure]
number     = { type = "text", description = "The invoice number", required = true }
customer   = { type = "text", description = "The customer's name", required = true }
notes      = { type = "text", description = "Notes, in Markdown" }
line_items = { type = "list", item_type = "concept", item_concept_ref = "doc_gen_tests.LineItem", description = "The lines", required = true }

[concept.InvoicePdf]
description = "The invoice as a printable file"
refines     = "Document"

[pipe.print_invoice]
type        = "PipeDocGen"
description = "Print the invoice"
inputs      = { invoice = "Invoice" }
output      = "InvoicePdf"
#STEP_FIELDS#
"""

    INVOICE_INPUTS: ClassVar[dict[str, Any]] = {
        "invoice": {
            "concept": "doc_gen_tests.Invoice",
            "content": {
                "number": "INV-2026-0142",
                "customer": "Ada Lovelace",
                "notes": "Paid by **bank transfer**, see https://example.com/terms.",
                "line_items": [{"description": "Tea", "amount": 7.0}, {"description": "Cake", "amount": 4.5}],
            },
        }
    }

    INVOICE_INPUTS_WITHOUT_NOTES: ClassVar[dict[str, Any]] = {
        "invoice": {
            "concept": "doc_gen_tests.Invoice",
            "content": {
                "number": "INV-2026-0143",
                "customer": "Ada Lovelace",
                "line_items": [{"description": "Tea", "amount": 7.0}],
            },
        }
    }

    PDF_LAYOUT_STEP: ClassVar[str] = 'format = "pdf"\nfilename = "invoice-{{ invoice.number }}"'

    # A bundle of another domain whose sequence runs the test bundle's step, which a library directory holds: the step
    # is dry-run only inside the sequence, so what it finds reaches the verdict from a pipe the sweep did not sweep itself.
    CALLER_BUNDLE_MTHDS: ClassVar[str] = """
domain = "doc_gen_caller"
description = "Billing a customer with a printed invoice"
main_pipe = "bill_customer"

[pipe.bill_customer]
type        = "PipeSequence"
description = "Print the customer's invoice"
inputs      = { invoice = "doc_gen_tests.Invoice" }
output      = "doc_gen_tests.InvoicePdf"
steps       = [{ pipe = "doc_gen_tests.print_invoice", result = "invoice_pdf" }]
"""

    # The domain of the same bundle loaded beside the test bundle, so the two declare no pipe or concept twice.
    OTHER_DOMAIN: ClassVar[str] = "doc_gen_other"

    @classmethod
    def bundle(cls, *, step_fields: str) -> str:
        return cls.BUNDLE_MTHDS.replace(cls.STEP_SLOT, step_fields)

    @classmethod
    def bundle_in_the_other_domain(cls, *, step_fields: str) -> str:
        return cls.bundle(step_fields=step_fields).replace("doc_gen_tests", cls.OTHER_DOMAIN)
