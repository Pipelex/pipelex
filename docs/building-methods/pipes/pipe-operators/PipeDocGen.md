---
description: "Generate a document file, such as a PDF, from a method's structured result with PipeDocGen. It calls no model: it lays out or fills what its inputs already hold."
---

# PipeDocGen

The `PipeDocGen` operator turns a method's result into a document file: a PDF, and with the Pipelex document generation plugin an Excel workbook, a Word document or a PowerPoint deck. The file is stored like any other file a run produces, and the step outputs a `Document`.

`PipeDocGen` calls no model, unlike `PipeImgGen`, whose name it echoes. It lays out, or fills a template with, what its inputs already hold, so it costs nothing to run and produces the same file every time for the same inputs. The model work, such as an LLM writing a report or extracting an invoice, happens in the steps before it.

## How it works

The step runs in two stages:

1. **Compose.** Pipelex lays the inputs out, or renders the step's HTML template against them, and renders the file's name. Every template here renders strictly: a field the inputs do not have fails the step instead of printing as empty text.
2. **Print.** A document engine turns the composition into the file's bytes, and Pipelex stores them. The output is a `Document` whose URL ends in the file's own name, such as `invoice-INV-2026-0142.pdf`.

With no template, the step lays its inputs out by itself, which is called the auto-layout:

- the scalar fields of a structure, such as a number, a date or a short text, make a grid of labels and values, labelled from the fields' titles;
- a list of flat structures makes a table, whose header row repeats on every page;
- a nested structure makes a section with a heading;
- a `Text` input prints as paragraphs, and a [`Markdown`](../../concepts/native-concepts.md) input prints formatted, with its headings, emphasis, lists, tables, code blocks and links;
- an `Html` input prints as its text with the tags removed, since the auto-layout does not interpret HTML;
- an `Image` prints as a picture, with its caption.

A single input is the document itself: an invoice's fields fill the page. Several inputs each get a section, in the order the step declares them. Every page carries the document's title in a running header and "Page N of M" in its footer, on A4 portrait, in a font bundled with Pipelex so that a PDF looks the same on every machine.

## What prints where

Which formats a runtime prints depends on the document engines installed in it:

| The step asks for | Open Pipelex | With the Pipelex document generation plugin |
| --- | --- | --- |
| `pdf` without a template | Printed by the built-in engine | The same built-in engine, so the same PDF |
| `pdf` with an HTML template | Refused at load | Printed from the template |
| `xlsx` or `docx`, with or without a template file | Refused at load | Printed |
| `pptx` with a template file | Refused at load | Printed |

A `pdf` without a template prints the same with or without the plugin, so a method prints the same PDF everywhere. A step that no installed engine prints is refused **when the method loads**, before a run spends anything on inference, with an error naming the format and the plugin that prints it:

```
PipeDocGen 'render_invoice_xlsx' asks for a xlsx from the auto-layout of its inputs, and no document engine installed in this runtime prints it. The engines for it come with the Pipelex document generation plugin, pipelex-doc-gen, which is not installed here.
```

## Configuration

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

### MTHDS parameters

| Parameter | Type | Description | Required |
| --- | --- | --- | --- |
| `type` | string | `PipeDocGen` | Yes |
| `description` | string | What the document is | Yes |
| `inputs` | dictionary | The inputs the document shows. Every declared input is in the template's context, so several inputs combine into one document. | Yes |
| `output` | string | `Document`, or a concept that refines it. A single file: no multiplicity. | Yes |
| `format` | string | `pdf`, `xlsx`, `docx` or `pptx`. It sets the file's type and suffix. | Yes |
| `template` | string | An inline HTML and Jinja2 template, for `pdf` only. A `pdf` with a template is printed by the plugin. | No |
| `template_file` | string | A template file beside the bundle, relative to the bundle's file: `.html` for `pdf`, `.xlsx`, `.docx` or `.pptx`. It excludes `template`. `pptx` requires one. | No |
| `filename` | string | A Jinja expression over the inputs for the file's name, without its suffix, such as `invoice-{{ invoice.number }}`. It defaults to the pipe's code. | No |

There is no `engine` field: which engine prints a format is the runtime's business, not the method's.

### An LLM report as a PDF

The most common request needs no template: the LLM step declares its output as `Markdown`, and the `PipeDocGen` step formats it.

```toml
[pipe.write_report]
type   = "PipeLLM"
description = "Write a structured report in Markdown"
inputs = { topic = "Text" }
output = "Markdown"
prompt = "Write a report on this topic, in Markdown: @topic"

[pipe.render_report_pdf]
type        = "PipeDocGen"
description = "Print the Markdown report as a PDF, formatted"
inputs      = { report = "Markdown" }
output      = "Document"
format      = "pdf"
filename    = "report"
```

A `Text` input prints as plain paragraphs, so a report whose output is `Text` prints its `#` and `**` as they are. Declare it `Markdown` to have it formatted.

## Templates

### HTML templates

A `pdf` step's `template`, or its `.html` `template_file`, is rendered with exactly the stack of a `PipeCompose` HTML template: `$x` and `@x`, the `format` and `tag` filters, HTML autoescaping, and the [template sandbox](../../../under-the-hood/template-sandbox.md). A template that is only a fragment is wrapped in the plugin's print stylesheet (A4, running headers, page numbers); a whole HTML document prints as written, with any page setup its CSS gives. Three differences from `PipeCompose` matter:

- **A field a template names must exist.** Each path a template reads, such as `invoice.customer.name`, is checked against the inputs' concepts when the method loads, including a path through a loop variable: in `{% for item in invoice.line_items %}`, `item.amount` is checked against the line item's concept. What the load-time check cannot follow, such as a value set with `{% set %}`, fails when the template renders at the dry run, since a missing value is an error rather than empty text. An absent optional input can still be tested with `{% if notes %}` or `is defined`.
- **Pipelex's `format` filter shadows Jinja's own.** To format a number, write `{{ '%.2f' % invoice.total }}` rather than `{{ '%.2f' | format(invoice.total) }}`.
- **The `markdown` filter** turns Markdown held in a plain text field into HTML: `{{ invoice.notes | markdown }}`. A `Markdown` input needs no filter.

### Office template files

An `.xlsx`, `.docx` or `.pptx` template file is filled by its engine from the inputs as plain data, so it sees fields, not the sigils and filters of HTML templates. Its contract is documented with the plugin. When the plugin's engine checks templates, `pipelex validate` and the dry run compare the file with the inputs' concepts: a misspelled name is reported before any run.

A template file is found beside the bundle, so it works for a bundle loaded from a directory. A bundle loaded from a string, as the hosted API does, cannot name one: the step is refused at load. An inline `template` works on every load path.

## Running and iterating

`pipelex run` copies the file into the run's results folder, under its own name, and prints its path:

```bash
pipelex run bundle invoice/ --pipe render_invoice_pdf --inputs invoice/inputs.json
```

Running the `PipeDocGen` step alone on inputs saved from an earlier run is the loop for working on a document's layout: it spends nothing on inference. Write the inputs file in the shape `pipelex run` takes, one entry per input with its concept and content.

A dry run composes for real against mock inputs, which checks the templates and the file's name, prints nothing, and outputs a mock `Document`.

## Related documentation

- [PipeCompose](./PipeCompose.md), which renders a template into a `Text` or `Html` output
- [Native concepts](../../concepts/native-concepts.md), for `Document` and `Markdown`
- [`pipelex run`](../../../tools/cli/run.md)
- [Document Engine Plugins](../../../under-the-hood/document-engine-plugins.md), for how a runtime finds the engine that prints a step
