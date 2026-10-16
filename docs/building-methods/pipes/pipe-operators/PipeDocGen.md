---
description: "Generate a document file, such as a PDF, from a method's structured result with PipeDocGen. It calls no AI model: a document engine lays out or fills what its inputs already hold."
---

# PipeDocGen

The `PipeDocGen` operator turns a method's result into a document file: a PDF, and with the Pipelex document generation plugin an Excel workbook, a Word document or a PowerPoint deck. The file is stored like any other file a run produces, and the step outputs a `Document`.

`PipeDocGen` calls no AI model, unlike `PipeImgGen`, whose name it echoes. It lays out, or fills a template with, what its inputs already hold, so it costs nothing to run and produces the same file every time for the same inputs. The AI work, such as an LLM writing a report or extracting an invoice, happens in the steps before it. Its `model` is the **document engine** that prints the file, such as `reportlab-pdf` or, with the plugin, `pipelex-pdf`, chosen the way a step chooses any model.

## How it works

The step runs in two stages:

1. **Compose.** Pipelex lays the inputs out, or renders the step's HTML template against them, and renders the file's name. Every template here renders strictly: a field the inputs do not have fails the step instead of printing as empty text.
2. **Print.** The step's document engine turns the composition into the file's bytes, and Pipelex stores them. The output is a `Document` whose URL ends in the file's own name, such as `invoice-INV-2026-0142.pdf`.

With no template, the step lays its inputs out by itself, which is called the auto-layout:

- the scalar fields of a structure, such as a number, a date or a short text, make a grid of labels and values, labelled from the fields' titles;
- a list of structures the method declares, whose fields are all flat, makes a table, whose header row repeats on every page;
- a nested structure makes a section with a heading, and so does a nested object of a `JSON` input; a `Composite` lays out its components like a structure's fields;
- a `Text` input prints as paragraphs, and a [`Markdown`](../../concepts/native-concepts.md) input prints formatted, with its headings, emphasis, lists, tables, code blocks and links;
- an `Html` input prints as its text with the tags removed, since the auto-layout does not interpret HTML, a table row on one line with its cells separated by `|`;
- an `Image` prints as a picture, with its caption;
- a verdict prints as its verdict alone, like any scalar: a `YesNo` as its answer, a `Choice` as its option key and a `Rating` as its level, without the probability or confidence a producer reported;
- a list of images, of `Markdown` texts or of other native values prints item by item, each as it would print alone.

A single input is the document itself: an invoice's fields fill the page. Several inputs each get a section, in the order the step declares them. Every page carries the document's title in a running header and "Page N of M" in its footer, on A4 portrait, in a font bundled with Pipelex so that a PDF looks the same on every machine.

## Document engines

A document engine is a model of the `doc_gen` family. A step names one with `model`; a step that names none prints on the model deck's default for its format and for whether it has a template:

| The step asks for | Default engine | Other engines that print it | Comes with |
| --- | --- | --- | --- |
| `pdf` without a template | `reportlab-pdf` | `pipelex-pdf` | Pipelex; `pipelex-pdf` with the plugin |
| `pdf` with an HTML template | `pipelex-pdf` | | The Pipelex document generation plugin |
| `xlsx`, with or without a template file | `pipelex-xlsx` | | The plugin |
| `docx`, with or without a template file | `pipelex-docx` | | The plugin |
| `pptx` with a template file | `pipelex-pptx` | | The plugin |

Open Pipelex prints a `pdf` without a template on its built-in `reportlab-pdf`, whose default is in `.pipelex/inference/deck/5_doc_gen_deck.toml`. The plugin declares its engines and their defaults itself when it loads, so installing it is all it takes. A step that names its engine prints the same file wherever it runs; a step that names none follows the deck of the install it runs on, and a default set in an `x_custom_*.toml` deck file overrides both the kit's and the plugin's.

A step whose engine is not installed is refused **when the method loads**, before a run spends anything on inference, with an error naming the engine and the plugin that provides it:

```
PipeDocGen 'render_invoice_xlsx' asks for an xlsx from the auto-layout of its inputs, and no document engine for it is installed in this runtime. It comes with the Pipelex document generation plugin, pipelex-doc-gen.
```

An install set up before `reportlab-pdf` existed declares neither the engine in its `internal.toml` nor its default in the model deck, so a `pdf` step that would print on `reportlab-pdf`, by naming it or by default, is refused with an error saying to run `pipelex update`, which refreshes those files from the kit. A step that prints on the plugin's `pipelex-pdf` is unaffected.

A step that names an engine which does not print its format from its source, such as `reportlab-pdf` with an HTML template, is refused at load as well.

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

To print the same invoice on the plugin's `pipelex-pdf`, the step names it: `model = "pipelex-pdf"`.

### MTHDS parameters

| Parameter | Type | Description | Required |
| --- | --- | --- | --- |
| `type` | string | `PipeDocGen` | Yes |
| `description` | string | What the document is | Yes |
| `inputs` | dictionary | The inputs the document shows. Every declared input is in the template's context, so several inputs combine into one document. | Yes |
| `output` | string | `Document`, or a concept that refines it. A single file: no multiplicity. | Yes |
| `format` | string | `pdf`, `xlsx`, `docx` or `pptx`. It sets the file's type and suffix. | Yes |
| `model` | string | The document engine that prints the file, a `doc_gen` model, alias or preset, such as `reportlab-pdf` or, with the plugin, `pipelex-pdf`. It defaults to the model deck's engine for the format and source. | No |
| `template` | string | An inline HTML and Jinja2 template, for `pdf` only. A `pdf` with a template is printed by the plugin. | No |
| `template_file` | string | A template file relative to the bundle's file, written with forward slashes: `.html` for `pdf`, `.xlsx`, `.docx` or `.pptx`. An empty or absolute path, a URL, a backslash and a colon are refused. When the bundle is read from a folder, the file is the one its [method tree](../../method-trees.md#file-references) holds at that path, a `..` climbing to another folder of the tree included, and a file the tree keeps out, such as a gitignored one, is refused; a bundle file run alone with no `METHODS.toml` at or above it reads no other file. When the bundle is loaded from a string, the file is one of the files sent with it, each keyed by a path inside the bundle, so a path no such file could be keyed by, one holding a `..` segment or a NUL character, or naming no file, is refused when the bundle is parsed, as a validation error at the step that does not repeat the path. It excludes `template`. `pptx` requires one. | No |
| `filename` | string | A Jinja expression over the inputs for the file's name, without its suffix, such as `invoice-{{ invoice.number }}`. It defaults to the pipe's code. The rendered name is made into one every storage reader serves, the hosted API's included, spelled in ASCII with hyphens for the rest: see [The file's name](#the-files-name). | No |

### The file's name

The document is stored, and downloaded, under its `filename` plus the format's suffix. A storage URI names it, and the hosted API serves a stored file only when its name is ASCII letters, digits, hyphens and underscores, one dot and the suffix, so the step makes every rendered name into one of those before it stores the file:

- **Letters are spelled in ASCII where they can be.** Accents are dropped (`Bäckerei Müller` gives `Backerei-Muller`, `İstanbul` gives `Istanbul`), and the letters that carry no accent to drop are spelled as a reader would type them: `ø` as `o`, `æ` as `ae`, `œ` as `oe`, `ł` as `l`, `đ` and `ð` as `d`, `þ` as `th`, `ß` as `ss`, `ı` as `i`.
- **Every other character becomes a hyphen**: a space, punctuation, a dot inside the name, and a letter of a script with no ASCII spelling here, such as Greek, Cyrillic, Han, Hangul, Arabic or Hebrew. A run of hyphens and underscores collapses into one, and none is kept at either end.
- **A name already ending in the suffix keeps it once**: `report.pdf` stays `report.pdf`.
- **The name is cut at 120 characters**, and a name that leaves nothing falls back to the pipe's code.

So `Halden Brook Review Q3 2026 — Zoë Ångström · Ærøskøbing · Москва · 東京都` is stored as `Halden-Brook-Review-Q3-2026-Zoe-Angstrom-AEroskobing.docx`. Keep a name you want to read whole to Latin letters and digits.

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

- **A field a template names must exist.** Each path a template reads, such as `invoice.customer.name`, is checked against the inputs' concepts when the method loads, including a path through a loop variable: in `{% for item in invoice.line_items %}`, `item.amount` is checked against the line item's concept. A name the template sets with `{% set %}` is followed no further, so a field read through it is checked when the template renders at the dry run, where a missing value is an error rather than empty text; a name only some branches of an `{% if %}` set is still checked as the input of that name, which the template reads on the paths where no branch ran. An absent optional input can still be tested with `{% if notes %}` or `is defined`.
- **Pipelex's `format` filter shadows Jinja's own.** To format a number, write `{{ '%.2f' % invoice.total }}` rather than `{{ '%.2f' | format(invoice.total) }}`.
- **The `markdown` filter** turns Markdown held in a plain text field into HTML: `{{ invoice.notes | markdown }}`. A `Markdown` input needs no filter.

An inline `template` is rendered where the step runs, its text being the bundle's own. A `template_file` is read where the document is printed: the step names the file by its method tree and its path there, and the print stage reads it, renders it with the step's data and prints it, a dry run's print included, so a value the template reads that does not exist fails the dry run as it fails a live one. On a distributed orchestrator such as Temporal, the step runs in a workflow, which reads no file, and the print runs in an activity, which reads the file from the method file store of the deployment. An HTML template file is printed with the inputs the step declares, the only data it may read, so an HTML step's print carries none of the run's other data.

### Images, stylesheets and fonts beside a template

An HTML template names the files of its method by relative URLs, as a web page names the files beside it. A relative URL resolves against the template file's own place in the method's folder, and an inline `template`'s against its bundle file, so a brand kit travels with its method: the logo beside the template, the stylesheet that lays it out, the font in `fonts/`. Take a method whose folder holds these files:

```text
METHODS.toml
invoice.mthds
templates/invoice.html
templates/logo.png
styles/print.css
fonts/brand.woff2
```

The template names the logo beside it and the stylesheet one folder up:

```html
<link rel="stylesheet" href="../styles/print.css">
<img src="logo.png" alt="Acme">
<h1>Invoice {{ invoice.number }}</h1>
```

A URL inside a stylesheet resolves against the stylesheet, as in a browser, so `styles/print.css` names the font from its own folder:

```css
@font-face { font-family: Brand; src: url("../fonts/brand.woff2"); }
body { font-family: Brand; }
```

- **The files are read from the method, never from a disk.** The print reads each file from the method's tree, under the run's read scope, wherever it prints: in the process that loaded the method, and on a distributed orchestrator such as Temporal, where the print activity reads it from the method file store of the deployment.
- **Only images, stylesheets and fonts are read.** A relative URL naming any other file of the method, such as its Python, a bundle, `METHODS.toml`, `requirements.txt` or a data file, is refused, by its suffix: a URL may come from a run's input, such as `<img src="{{ photo.url }}">`, and a document can carry what it reads, as a `rel="attachment"` link embeds its file in the PDF, so a caller allowed to run a method does not get to read its files that way. The images are `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg`, `.avif`, `.apng`, `.bmp`, `.ico`, `.tif` and `.tiff`, the stylesheets `.css`, and the fonts `.woff`, `.woff2`, `.ttf`, `.otf`, `.ttc` and `.eot`.
- **`..` climbs anywhere inside the method, never above its root.** A URL that climbs above the folder holding `METHODS.toml`, a root-relative URL such as `/logo.png`, a folder, a missing file, and a file the method leaves out, such as a hidden or a gitignored one, are refused with a message naming the URL, the template and the reason. A file outside the method is never read, even when it exists. A bundle named alone, with no `METHODS.toml` at or above it, is a method of that one file, so a file beside it is refused with the advice to hand over the method's folder.
- **A URL the template writes is checked when the method loads.** `pipelex validate`, a dry run and every load check each literal relative URL of the template and of the stylesheets it links, such as `<img src="logo.png">`, so a missing or misspelt file fails before any print. A URL the template builds from the run's inputs is checked when the document prints, and a refused one fails the print with a `TemplateUrlRefusedError`.
- **A URL with a scheme is left as written.** An `https://` URL is fetched through the SSRF guard, a `data:` URL is decoded, and a `pipelex-storage://` URL is read under the run's read scope, as before, so a template's split between the method's files and the caller's is the URL's own: relative for the method, a stored URI for a caller's file or an earlier output. A URL with no path, such as `#top`, names no file.
- **A file name holding `?`, `#` or `%` is written percent-encoded**, `100%25.png` for `100%.png`, since a URL's query and fragment are dropped before it resolves and a `%` starts an escape.
- **A bundle loaded from a string** resolves its inline template's relative URLs from the root of the files sent with it, and with no file sent beside it, it belongs to no method tree, so a relative URL its template writes is refused when the method loads, and one built from the run's inputs fails the print. Load such a method from its folder, or send it to the API server as a tree, in `files` (see [Pipe Run](../../../api-server/pipe-run.md#sending-a-method-as-a-tree)), where every file of the folder travels with it.

The engine that prints HTML joins each relative URL to a base URL Pipelex hands it and reads the file through Pipelex ([Document Engine Plugins](../../../under-the-hood/document-engine-plugins.md#relative-urls-the-files-of-the-templates-method-tree)).

### Office template files

An `.xlsx`, `.docx` or `.pptx` template file is filled by its engine from the inputs as plain data, so it sees fields, not the sigils and filters of HTML templates. In plain data a native value is its value, and a verdict is its verdict: a `YesNo` is its boolean, a `Choice` its option key and a `Rating` its level, so the file reads `team` rather than `team.choice`, and a verdict's probability or confidence does not reach it. A `pdf` template reads the verdict whole, `team.choice` and `team.confidence` included, as a `PipeCompose` template does. Its contract is documented with the plugin. When the plugin's engine checks templates, `pipelex validate` and the dry run compare the file with the inputs' concepts: a misspelled name is reported before any run.

A bundle loaded from a directory, a dependency package's included, finds its template file beside its own file, and never among the files sent with a request. A bundle loaded from a string has no directory, so its template files come with it: the API's routes take the whole method as a tree in `files`, or its bundles as strings with their template files in the request's `resources`, each keyed by exactly the path its step names, and the Python entry points take them as `submitted_files` (see [Template files sent with a bundle](#template-files-sent-with-a-bundle)). A string-loaded step whose file was not supplied is refused at load, saying so, whatever source label the bundle carries: only a bundle file the runtime read itself has a directory beside it, so a label naming a path, or a `source` written in the bundle's text, never makes the runtime read its own disk. An inline `template` works on every load path.

### Template files sent with a bundle

A method sent to the [API server](../../../api-server/pipe-run.md#sending-a-method-as-a-tree) as a tree, in `files`, carries its folder whole: its bundles, its template files and every image, stylesheet and font its templates name, each at its path in the method, whether a step names it or not, and it loads as if read from its folder. When the bundles are sent as strings instead, in `mthds_contents`, every template file a step reads travels beside them:

```json
{
  "mthds_contents": ["domain = \"invoicing\"\n..."],
  "resources": {"templates/invoice.docx": "UEsDBBQABgAIAAAAIQ..."}
}
```

- **The key is the path the step names**, relative to the bundle and written with forward slashes: a step with `template_file = "templates/invoice.docx"` reads the file sent as `templates/invoice.docx`, and `./templates/invoice.docx` or `templates//invoice.docx`, as a key or as the path a step names, names the same file. Every bundle of the request is read as sitting in one directory. An absolute path, a `..` segment, a backslash and a colon are refused, as a key and as the path a step names: a step whose `template_file` could not be a key is refused when its bundle is parsed, whatever the request sends, so every file a string-loaded step can name can be sent with it.
- **The value is the file's bytes** in standard base64.
- **Every file sent must be one a step names.** A file no step reads is refused, so a misspelled key fails loudly rather than leaving its step without a template. A file a template names by a relative URL, such as its logo, is named by no step, so it cannot be sent this way: send such a method as a tree, in `files`, or load it from its folder.
- **The files are checked like files on disk.** An `.html` template file is checked against the inputs when the method loads, and the engine's template check runs on an office template file at validation and in the dry run.

The files sent with a bundle make one method tree, with the bundles sent as strings at its root: the run names that tree by its digest, as it names the tree of a bundle loaded from a directory, and carries none of its files. The print stage reads a template file from the tree, under the run's read scope, to print it or to check it, wherever it runs: in the process that loaded the method, the tree is the one its library holds; on a remote orchestrator such as Temporal, the deployment's method file store serves it. No template file rides in the run's payloads, so none is bounded by them.

From Python, the same files are passed as `submitted_files`, a mapping from the path the step names to the file's bytes:

```python
from pathlib import Path

from pipelex.pipeline.runner import PipelexMTHDSProtocol

submitted_files = {"templates/invoice.docx": Path("templates/invoice.docx").read_bytes()}
result = await PipelexMTHDSProtocol(submitted_files=submitted_files).execute(mthds_contents=[bundle_text], inputs=inputs)
```

## Running and iterating

`pipelex run` copies the file into the run's results folder, under its own name, and prints its path:

```bash
pipelex run bundle invoice/ --pipe render_invoice_pdf --inputs invoice/inputs.json
```

Running the `PipeDocGen` step alone on inputs saved from an earlier run is the loop for working on a document's layout: it spends nothing on inference. Write the inputs file in the shape `pipelex run` takes, one entry per input with its concept and content.

A dry run composes for real against mock inputs, which checks the templates and the file's name, and its print reads the template file, renders an HTML one and hands an office one to the engine's template checker, then prints nothing and outputs a mock `Document`.

When the plugin's engine checks an office template file, validation reports what it finds in two ways. An error, such as a Word tag that names no field, fails the step's dry run, and so the validation. A warning, such as an Excel defined name or a PowerPoint shape name that matches no field, leaves the bundle valid and rides the verdict's advisory `warnings` as a `template_check_warning` item naming the step (`pipe_code`, `domain_code`), the file (`template_file`) and the place in it (`template_location`). Read it all the same: a misspelled name fills nothing, so the document keeps the template's sample value there. The warning reaches every surface that returns the verdict: `pipelex validate`, `pipelex-agent validate` and the API server's `POST /v1/validate`. A dry run that returns no verdict, such as `pipelex run --dry-run`, `pipelex fix bundle` or `pipelex build inputs`, logs it instead.

## Related documentation

- [PipeCompose](./PipeCompose.md), which renders a template into a `Text` or `Html` output
- [Native concepts](../../concepts/native-concepts.md), for `Document` and `Markdown`
- [`pipelex run`](../../../tools/cli/run.md)
- [Document Engine Plugins](../../../under-the-hood/document-engine-plugins.md), for how a runtime finds the engine that prints a step
