from typing import ClassVar

from pipelex.pipe_machinery.pipe_blueprint import PipeType


class InputNameRefusalTestData:
    """Pipe tables for the input-name refusal: one per pipe kind, valid on its own, each declaring `inputs` on one line."""

    PIPE_TABLES: ClassVar[dict[PipeType, str]] = {
        PipeType.PIPE_FUNC: """type = "PipeFunc"
description = "Totals an invoice"
inputs = { invoice = "Invoice" }
output = "Number"
function_name = "total_invoice"
""",
        PipeType.PIPE_IMG_GEN: """type = "PipeImgGen"
description = "Draws the letterhead of an invoice"
inputs = { invoice = "Invoice" }
output = "Image"
prompt = "A letterhead for $invoice"
""",
        PipeType.PIPE_COMPOSE: """type = "PipeCompose"
description = "Writes the reference line of an invoice"
inputs = { invoice = "Invoice" }
output = "Text"
template = "Invoice: $invoice"
""",
        PipeType.PIPE_LLM: """type = "PipeLLM"
description = "Summarizes an invoice"
inputs = { invoice = "Invoice" }
output = "Text"
prompt = "Summarize $invoice"
""",
        PipeType.PIPE_EXTRACT: """type = "PipeExtract"
description = "Reads the pages of an invoice scan"
inputs = { invoice = "Document" }
output = "Page[]"
""",
        PipeType.PIPE_SEARCH: """type = "PipeSearch"
description = "Looks up the supplier of an invoice"
inputs = { invoice = "Invoice" }
output = "SearchResult"
prompt = "Who issued $invoice?"
""",
        PipeType.PIPE_STRUCTURE: """type = "PipeStructure"
description = "Fills in an invoice from its text"
inputs = { invoice = "Text" }
output = "Invoice"
""",
        PipeType.PIPE_DOC_GEN: """type = "PipeDocGen"
description = "Prints an invoice"
inputs = { invoice = "Invoice" }
output = "Document"
format = "pdf"
filename = "invoice-{{ invoice.number }}"
""",
        PipeType.PIPE_JUDGE: """type = "PipeJudge"
description = "Judges whether an invoice is overdue"
inputs = { invoice = "Invoice" }
output = "YesNo"
question = "Is this invoice overdue?"
""",
        PipeType.PIPE_BATCH: """type = "PipeBatch"
description = "Totals each invoice"
inputs = { invoices = "Invoice[]" }
output = "Number[]"
branch_pipe_code = "total_invoice"
input_list_name = "invoices"
input_item_name = "invoice"
""",
        PipeType.PIPE_CONDITION: """type = "PipeCondition"
description = "Routes an invoice by its status"
inputs = { invoice = "Invoice" }
output = "Text"
expression = "invoice.status"
default_outcome = "fail"
outcomes = { paid = "summarize_invoice" }
""",
        PipeType.PIPE_PARALLEL: """type = "PipeParallel"
description = "Reads an invoice two ways at once"
inputs = { invoice = "Invoice" }
output = "InvoiceReading"
branches = [{ pipe = "summarize_invoice", result = "summary" }]
""",
        PipeType.PIPE_SEQUENCE: """type = "PipeSequence"
description = "Summarizes an invoice"
inputs = { invoice = "Invoice" }
output = "Text"
steps = [{ pipe = "summarize_invoice", result = "summary" }]
""",
    }

    # A pipe with no `type` and only the contract fields is a signature: the check covers it too.
    SIGNATURE_TABLE: ClassVar[str] = """description = "Summarizes an invoice"
inputs = { invoice = "Invoice" }
output = "Text"
"""

    BUNDLE_HEADER: ClassVar[str] = """domain = "invoicing"
description = "Invoices received from suppliers"

[concept]
Invoice = "An invoice received from a supplier"
InvoiceReading = "What was read off an invoice"
Catalog = "A supplier catalog"

[pipe.the_pipe]
"""

    BATCH_OVER_A_FIELD_TABLE: ClassVar[str] = """type = "PipeBatch"
description = "Totals each page of a catalog"
inputs = { catalog = "Catalog" }
output = "Number[]"
branch_pipe_code = "total_page"
input_list_name = "catalog.pages"
input_item_name = "page"
"""
