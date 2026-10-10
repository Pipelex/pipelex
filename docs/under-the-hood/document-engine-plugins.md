---
title: "Document Engine Plugins"
description: "How a PipeDocGen step finds the engine that prints it, a model of the doc_gen family, how a plugin declares its engines and their defaults, the render job an engine receives, what it shares with the built-in engine, the template checker it may offer, and how a runtime refuses at load what it cannot print."
---

# Document Engine Plugins

A [`PipeDocGen`](../building-methods/pipes/pipe-operators/PipeDocGen.md) step turns its inputs into a document file in two stages. The **compose stage** is Pipelex's own and is pure: it lays the inputs out, or renders the step's HTML template, or gathers the inputs as plain data for a template file, and it renders the file's name. The **print stage** hands the result to a **document engine**, which returns the file's bytes, and Pipelex stores them.

A document engine is a **model** of the `doc_gen` family, chosen the way a step chooses any model: by the step's `model`, or by the model deck's default. Its worker is contributed by a plugin, through the same `add_inference_backend` seam the inference backends use. Open Pipelex ships one engine, `reportlab-pdf`, which prints a `pdf` from the auto-layout of a step's inputs, and declares it in the kit's `internal.toml`. The Pipelex document generation plugin, `pipelex-doc-gen`, ships the engines for a `pdf` from an HTML template and for the office formats from outside this repository, and declares their models and their deck defaults itself when it loads.

---

## Sources, and the engines that print them

A step asks for a **format** (`pdf`, `xlsx`, `docx`, `pptx`), and its template decides the **source** the compose stage hands an engine:

| The step has | Source | What the engine receives |
| --- | --- | --- |
| No template (a `pdf`, `xlsx` or `docx`; a `pptx` needs a template file) | `layout` | The layout tree of the inputs |
| An HTML `template` or `.html` `template_file` (a `pdf` only) | `html` | The template rendered against the inputs |
| An office `template_file` | `template_file` | The file's bytes and the inputs as plain data |

Each engine is a model of the `internal` backend, declared with the sources it prints from as its `inputs` and its format as its `outputs`. The built-in engine is declared in the kit's `internal.toml`, which `pipelex update` refreshes, so an existing install receives it:

```toml
[reportlab-pdf]
model_type = "doc_gen"
sdk = "reportlab"
model_id = "print-pdf"
inputs = ["layout"]
outputs = ["pdf"]
costs = {}
```

| Engine | Prints | From | Declared by |
| --- | --- | --- | --- |
| `reportlab-pdf` | `pdf` | `layout` | Pipelex, in the kit's `internal.toml` |
| `pipelex-pdf` | `pdf` | `html`, `layout` | `pipelex-doc-gen`, when it loads |
| `pipelex-xlsx` | `xlsx` | `layout`, `template_file` | `pipelex-doc-gen`, when it loads |
| `pipelex-docx` | `docx` | `layout`, `template_file` | `pipelex-doc-gen`, when it loads |
| `pipelex-pptx` | `pptx` | `template_file` | `pipelex-doc-gen`, when it loads |

The model deck names the default engine for each format and source, keyed `<format>.<source>`, and a key naming a format and source no step can ask for fails when the deck loads. The kit's `5_doc_gen_deck.toml` sets the one default open Pipelex prints:

```toml
[doc_gen.choice_defaults]
"pdf.layout" = "@default-pdf"

[doc_gen.aliases]
default-pdf = "reportlab-pdf"
```

The plugin declares the defaults for the formats it prints, beneath the deck files: a deck file that sets the same format and source overrides it, and a user sets any default of their own in an `x_custom_*.toml` deck file, which overrides both. A step that names no engine prints on the deck's default, so it follows the install's deck, as an LLM step does. A step that names one, such as `model = "pipelex-pdf"` on a `pdf` without a template, prints on that engine wherever it runs.

---

## Registering an engine

A plugin registers a worker factory for its engine's sdk in the `doc_gen` family, declares the engine's model in the `internal` backend with `add_internal_model`, and declares the deck default for each format and source it prints with `add_doc_gen_default`:

```python
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar


class MyDocGenPlugin:
    name = "my_doc_gen"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.DOC_GEN, sdk="openpyxl", make_worker=make_xlsx_worker)
        registrar.add_internal_model(
            name="pipelex-xlsx",
            spec={
                "model_type": "doc_gen",
                "sdk": "openpyxl",
                "model_id": "write-xlsx",
                "inputs": ["layout", "template_file"],
                "outputs": ["xlsx"],
                "costs": {},
            },
        )
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT, model="pipelex-xlsx")
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.TEMPLATE_FILE, model="pipelex-xlsx")
```

The model's `spec` is exactly the table a backend file would hold for it (`model_type`, `sdk`, `model_id`, `inputs`, `outputs`, `costs`, and any other model-spec field), and it is complete on its own: the `[defaults]` table of `internal.toml` is not applied to it. A default names a model, directly or through any reference the deck resolves.

`register` stores these declarations and validates nothing. The model manager merges them at boot, before it builds the deck, and refuses what it cannot merge with `PluginModelDeclarationError`, naming the plugin: a model whose name and model type the install's `internal.toml` already declares (the message names the file too), a table that is not a valid model spec, or a default for a format and source no step composes. A handle names one model per model type, so a plugin may declare another kind of a name the file declares. Model names are not global across backends, so a name another backend declares is left to the routing profile, as it is for a model a file declares. When the install disables the `internal` backend, or declares none, the plugin's models are not merged, as a disabled backend's own models are not loaded, and its defaults are left out with them, so a plugin never makes a boot fail that would succeed without it. A second plugin declaring the same model, the same name with the same model type, fails at registration with `DuplicateInternalModelError`, and the same format and source with `DuplicateDocGenDefaultError`, each naming both plugins. `pipelex plugins list` shows each declaration on the plugin's row.

A document engine is a kernel-layer capability, and so are its model and its defaults, so an out-of-tree engine publishes under the `pipelex.plugins.kernel` entry-point group (see [Inference Backend Plugins](inference-backend-plugins.md#shipping-it-as-an-out-of-tree-plugin) for the groups). `make_worker` is called for each print, with the model's spec, and imports the engine's library inside it, so `register` stays import-light and a process that never prints never imports the library. An engine loads its library, fonts and styles once per process, in the module that holds its worker, rather than per worker. A second registration of the same sdk fails loud at boot with `DuplicateInferenceBackendError`, naming both plugins.

---

## Refused at load, not at run

When a method loads, each `PipeDocGen` step resolves its engine: the model it names, or the deck's default for its format and source. The step is refused right there, before a run spends anything on inference, when:

- the deck names no engine for its format and source, and it names none (`DocGenEngineMissingError`, which names `pipelex-doc-gen` for every format and source but a `pdf` from the auto-layout, and says to run `pipelex update` for that one);
- the engine is `reportlab-pdf`, named by the step or through a default, and the install's `internal.toml` predates it (`DocGenEngineMissingError`, which says to run `pipelex update`);
- the engine it names is one of the plugin's, `pipelex-pdf`, `pipelex-xlsx`, `pipelex-docx` or `pipelex-pptx`, and the plugin is not installed (`DocGenEngineMissingError`, naming `pipelex-doc-gen`);
- the engine it names is any other model the deck does not define (an unknown model, located on the step's `model` field);
- the engine does not print its format from its source, by the `inputs` and `outputs` it declares (`DocGenModelCapabilityError`);
- no installed plugin registers the engine's sdk (`DocGenEngineMissingError`, naming the engine and `pipelex-doc-gen`, or saying the built-in engine is disabled).

The other model families find a missing worker only when they build it, at run time; a document engine is checked when the method loads as well. A runtime therefore needs no rule of its own about what it prints: a host that must not print documents disables the built-in plugin with `runtime.plugins.disabled = ["reportlab"]` and installs no other engine, and every `PipeDocGen` step is refused at load.

---

## The contract: a render job in, bytes out

An engine's worker subclasses `DocGenWorkerAbstract` from `pipelex.cogt.doc_gen.doc_gen_worker_abstract`:

```python
def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument: ...
```

- **`RenderJob`** is plain data, which Pipelex builds in the print stage from the step's composition and hands to the worker in the same process. It has a JSON round trip for an engine that prints in another process, in which the template's bytes are URL-safe base64 and a date or a time is its ISO text. It holds the format and source, the file's name with its suffix, the document's title, and exactly the payload its source names, `layout` (a `LayoutDocument` from `layout_tree.py`), `html`, or `template` with `data`, the inputs as plain data by input name. It carries no Pipelex object, so an ordinary Pipelex release does not break an engine; a change to it, or to the worker, is a change of the plugin contract.
- **`RenderResources.load(uri=…, position=…)`** is how an engine reads a file its document names, such as an image or a stylesheet. It resolves `pipelex-storage://` keys through the run's storage provider, decodes `data:` URLs, fetches `https://` through the SSRF guard, and refuses what the run's read scope does not allow, a local path included, with `UriReadRefusedError`. An engine reads nothing any other way. It returns a **`LoadedResource`**: the file's bytes as `data`, and as `mime_type` the media type the file's source gives it, described below.
- **`RenderedDocument`** holds the bytes. Their MIME type and suffix are the format's.

`render` is synchronous and runs on a thread of a print pool of its own, never on the event loop's default executor, which the engine's reads need, while `RenderResources.load` hands each read back to the event loop the print started from. The print stage that calls it ends the print with the event every inference call ends with, `Inference call ends`, carrying no tokens and no cost since an engine reports none (see [Summary events](../tools/logging.md#summary-events)), logged on the coroutine that awaits the thread, so a print cancelled from outside ends `cancelled` while the thread finishes its render; an engine overrides `render` alone and logs nothing for the print itself. An engine keeps no state from one print into the next. It signals a document it cannot print by raising `DocGenRenderError`, which passes through; anything else it raises, beyond a Pipelex error, is reported as a `DocGenRenderError` naming the engine and the file.

The contract is what an engine uses in `pipelex.cogt.doc_gen`: the worker; the render job, its resources, the `LoadedResource` they return and the rendered document (`render_job.py`); the formats and sources (`doc_gen_format.py`); `DocGenRenderError`, the one error of `exceptions.py` an engine raises, and `MarkdownFormattingBudgetError`, the one the contract raises to an engine that formats Markdown outside a template render; the layout tree (`layout_tree.py`); the template check request and the findings a checker returns (`template_check.py`), with the input shapes the request carries (`InputShape` and `InputShapeKind` in `input_shape.py`); and the modules of the next section. The rest of the package is Pipelex's own side of the print. An engine reaches Pipelex only through the contract and the registration seam every plugin uses, which also hands a worker its model spec, its backend, its SDK clients and its reporting delegate: anything else in Pipelex may move or change in an ordinary release, while a breaking change to the contract moves `PLUGIN_API_VERSION`. A piece an engine is missing is added to the contract, rather than imported from elsewhere in Pipelex.

### The media type of a file an engine reads

`LoadedResource.mime_type` is the type the file's source gives it, lowercased and without its parameters, such as `text/css`. Pipelex never guesses it, so it is `None` when the source gives none:

| Source | `mime_type` |
| --- | --- |
| `https://` | The final response's `Content-Type`, after redirects; `None` when the response sends none. |
| `data:` | The type the URL declares. |
| `pipelex-storage://` on S3 or GCS | The content type recorded when the file was stored. |
| `pipelex-storage://` on the local or in-memory provider | The type identified from the bytes, which covers binary formats only: a stylesheet or an SVG has none. |
| A local path, read only by an unscoped run | `None`: a file system records no type. |

A declared type is returned as declared, even a generic one such as `application/octet-stream`, and is not checked against the bytes. An engine that needs a type keeps its own guess, from the URI's extension or from the bytes, for a file whose source gives none or gives one that says nothing. An HTML engine is the case in point, since a print library such as WeasyPrint keeps a linked stylesheet only when its type is `text/css`, and a stylesheet served from a URL with no extension, as a web font service serves one, can be typed only by what its server declared. The built-in PDF engine reads images only and never looks at the type, because Pillow identifies an image from its bytes.

---

## What an engine shares with the built-in one

A document should read the same whichever engine printed it, and a template should be held to the same rules whichever engine fills it, so an engine takes these from the contract rather than writing its own. None of them imports ReportLab, so an engine can use them without loading the built-in engine's library.

`pipelex.cogt.doc_gen.layout_display` holds the rules by which every engine shows a layout tree's values, the built-in engine included:

- **`display_scalar(value=…)`** writes a scalar as text: blank for nothing, `Yes` or `No` for a boolean, a whole float without its decimals, a date as `2026-09-29`, a datetime as `2026-09-29 14:05`, and a time of day as `09:07`, each followed by the UTC offset it states (` UTC`, ` +02:00`), if any.
- **`is_numeric_column(values=…)`** says whether a table's column holds numbers only, blanks aside, and at least one, a boolean not counting as a number: such a column is aligned right.
- **`markdown_as_html(markdown=…)`** converts a `MarkdownBlock` to an HTML fragment for an engine that writes HTML, with the one parser Pipelex reads Markdown with, as the `markdown` filter and the `Markdown` concept's HTML view do: CommonMark with tables and strikethrough, raw HTML shown as text, and only a URL with a scheme turned into a link, so `README.md` stays text. Called from an engine's own code, outside a template render, it is charged to no render budget, unlike `format_markdown` below, so an engine bounds what it converts itself.

`pipelex.cogt.doc_gen.formatted_markdown` holds what an engine prints a Markdown text from when it formats it in its own format, as a Word or an Excel template fill does, rather than through HTML:

- **`format_markdown(markdown=…)`** reads a Markdown text with the one parser Pipelex reads Markdown with, by the rules the built-in engine prints it by, which it shares from this module: CommonMark with tables and strikethrough; raw HTML shown as text; a soft line break read as a space and a hard one, two trailing spaces or a backslash, as a line break; bullets alternating `•` and `–` by depth and an ordered list numbered from its own start; only an `http`, `https` or `mailto` target kept as a link, any other printing its text alone; an image never fetched, printed as `[image: alt]` in italics; and a node the converter does not know printed as its text rather than failing the document.
- **`FormattedMarkdown`**, what it returns, is plain data, as the layout tree is: its `blocks`, in order, each a `FormattedParagraph`, a `FormattedHeading` with its `level`, a `FormattedListItem` with its `depth` and its `marker` as printed, such as `•` or `3.` (`None` for a later paragraph of the same item), a `FormattedCodeBlock` with its `lines`, a `FormattedQuotation` with its `depth`, a `FormattedRule`, or a `FormattedTable` of rows of cells, each row marked `is_header` or not; and in each block its `spans`, each a `TextSpan` with its `bold`, `italic`, `strikethrough` and `code` flags and the `link` it opens, if any, or a `LineBreakSpan`. A list, a code block, a table or a rule inside a quotation keeps its own kind. `str()` of it is its plain text, each block on a line of its own, list items indented by depth with their markers, table cells separated by tabs, and every other piece of markup gone, for a place that cannot show formatting.
- **Its budget.** Inside a template render, as the `markdown` filter below converts, the conversion is charged to the render's budget the way the HTML conversion is, for every character of its source and every cell of its tables before it parses and for its result, bounded from the parsed tokens, before it builds it, and an overdraft is the render's own `RenderBudgetExceededError`, a Jinja `TemplateError`, which a template fill catches with every other error a tag raises. Called from an engine's own code, outside any render, it spends from a budget of its own, as large as one render's, and an overdraft raises `MarkdownFormattingBudgetError` (from `exceptions.py`), which the engine reports as its own fill error, naming where the value goes.

`pipelex.cogt.doc_gen.template_environment` holds **`make_plain_data_template_environment()`**, the Jinja environment an engine fills a template file's tags in when it fills them itself, as a Word template's tags are filled through docxtpl. It is synchronous; sandboxed as every Pipelex template is, each render spending from a budget of its own (see [Template Sandbox](template-sandbox.md)); strict, so a missing value fails the render instead of printing as empty text; and it registers Jinja's built-in filters and one of Pipelex's, `markdown`, since the plain data it reads holds no stuff for Pipelex's other filters to work on.

`{{ invoice.notes | markdown }}` reads a text as Markdown into a `FormattedMarkdown`, as the HTML templates' `markdown` filter reads it into HTML: None gives an empty one, any other value is read as its string form, and an undefined value fails the render, as it would anywhere in a strict template. How a `FormattedMarkdown` prints is the engine's business, so `make_plain_data_template_environment(finalize=…)` takes a function applied to every value a tag prints, before the environment converts it to text: an engine turns a `FormattedMarkdown` into its own form there and hands every other value back as it is. The environment wraps it to charge what is printed, which is why it is passed at construction rather than assigned afterwards. Without one, a `FormattedMarkdown` prints its plain text, so a place that cannot format, such as a document's properties, prints clean text rather than asterisks.

---

## The template checker

An office template names the fields it is filled with in its own way, which Pipelex cannot read: an Excel workbook through its defined names and Tables, a Word document through its tags. So an engine that fills a template file overrides its worker's `check_template` (the request and findings are in `pipelex.cogt.doc_gen.template_check`):

```python
def check_template(self, *, request: TemplateCheckRequest) -> list[TemplateFinding]: ...
```

The request carries the template file's bytes and name, the shape of each input as an `InputShape` tree (which fields exist, which are lists, and what their items hold), and the dry run's mock inputs as plain data, so the checker can also fill the template in memory. The dry run, and so `pipelex validate`, calls it for every step with an office template file: a finding of severity `error` fails the step with `PipeDocGenTemplateCheckError`, listing the findings, and a `warning` is logged. The default finds nothing. An HTML template, inline or in a `.html` template file, never reaches an engine's checker: Pipelex checks it itself, against the inputs' concepts, when the method loads. The built-in engine takes no template.

---

## Where the print stage runs

The print stage is a content-generation leaf, like image generation or extraction: `ContentGenerator.make_rendered_document` hands a `RenderDocumentAssignment`, which carries the composition and the resolved engine, to `render_document_and_store`. The leaf authorizes the images the document names against the run's read scope, takes the dry-run branch, builds the engine's worker, prints and stores the file, and returns only the `DocumentContent` pointing at it, so the file's bytes never cross a workflow boundary. The dry run composes for real, which checks the templates against mock inputs, runs the template checker, and prints and stores nothing. See [Content Generation Across Boundaries](distributed-content-generation.md) for the leaves.

---

## Related

- [PipeDocGen](../building-methods/pipes/pipe-operators/PipeDocGen.md) — the operator, its formats, its templates and its `model`
- [Inference Backend Plugins](inference-backend-plugins.md) — plugin discovery, the entry-point groups and the `runtime.plugins.disabled` denylist
- [Storage Provider Plugins](storage-provider-plugins.md) — where the printed file is stored
- [Template Sandbox](template-sandbox.md) — what a composed template may read
