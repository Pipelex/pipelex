# The PipeDocGen playground

This directory is where to try methods that end in a `PipeDocGen` step and write a PDF you can open. Open Pipelex prints a `pdf` without a template, laid out from the step's inputs by the built-in ReportLab engine, so everything here runs with nothing more than `make install`. A `pdf` from an HTML template, and the `xlsx`, `docx` and `pptx` formats, need the Pipelex document generation plugin, and without it such a step is refused when the method loads. Run the commands below from the repository's root.

## Printing without inference

Each `PipeDocGen` step runs alone on a saved inputs file, so it spends nothing on inference. The file lands in `results/<pipe>_output_NN/`, under its own name, and the command prints its path.

```bash
P=tests/e2e/pipelex/pipes/pipe_operators/pipe_doc_gen
.venv/bin/pipelex run bundle $P/invoice --pipe render_invoice_pdf --inputs $P/invoice/inputs.json
.venv/bin/pipelex run bundle $P/report --pipe render_report_pdf --inputs $P/report/render_inputs.json
```

| Pipe | What comes out |
| --- | --- |
| `render_invoice_pdf` | The invoice of `invoice/inputs.json`, with sixty line items, laid out from its structure alone: the fields in a grid, the customer as a section, the line items as a table whose header repeats on every page, a running title and "Page N of M" |
| `render_report_pdf` | The Markdown report of `report/render_inputs.json`, formatted: headings, emphasis, lists, a table, a code block and links |

**This is the loop for working on a document**: change the inputs or the concept, rerun the pipe, open the file. To print other data, write an inputs file shaped like `invoice/inputs.json`, one entry per input with its concept and content.

## End to end, with inference

An LLM writes a report in Markdown on the topic in `report/inputs.json`, and the last step prints it formatted:

```bash
.venv/bin/pipelex run bundle $P/report --inputs $P/report/inputs.json
```

An LLM invents an invoice from the brief in `invoice/brief_inputs.json`, and the last step prints it:

```bash
.venv/bin/pipelex run bundle $P/invoice --inputs $P/invoice/brief_inputs.json
```

## Writing a PipeDocGen step

```toml
[concept.InvoicePdf]
description = "The invoice laid out as a printable PDF"
refines     = "Document"

[pipe.render_invoice_pdf]
type        = "PipeDocGen"
description = "Lay out the invoice as a paginated PDF from its structure alone"
inputs      = { invoice = "Invoice" }
output      = "InvoicePdf"
format      = "pdf"
filename    = "invoice-{{ invoice.number }}"
```

- **`format`** is `pdf`, `xlsx`, `docx` or `pptx`; open Pipelex prints a `pdf` without a template.
- **`model`** names the document engine, such as `reportlab-pdf`, or `pipelex-pdf` with the plugin. Without it, the model deck's default for the format prints the file, which for a `pdf` without a template is `reportlab-pdf`.
- **`filename`** is a Jinja expression over the inputs, and the suffix is added. It defaults to the pipe's code. It renders strictly, so a field the inputs do not have fails the step, and its field paths are checked against the inputs' concepts when the method loads.
- **The output** is `Document` or a concept that refines it, and a single file.
- **The inputs** each get a section when there are several, in the order the step declares them; a single input is the document itself.
- **A report an LLM writes** prints formatted when its output is declared `Markdown`; declared `Text`, its `#` and `**` print as they are.

The operator's page in the docs, `docs/building-methods/pipes/pipe-operators/PipeDocGen.md`, covers templates and what each format needs.
