---
title: "Document Engine Plugins"
description: "How a PipeDocGen step finds the engine that prints it, the render job an engine receives, the template checker it may offer, and how a runtime refuses at load what no installed engine prints."
---

# Document Engine Plugins

A [`PipeDocGen`](../building-methods/pipes/pipe-operators/PipeDocGen.md) step turns its inputs into a document file in two stages. The **compose stage** is Pipelex's own and is pure: it lays the inputs out, or renders the step's HTML template, or gathers the inputs as plain data for a template file, and it renders the file's name. The **print stage** hands the result to a **document engine**, which returns the file's bytes, and Pipelex stores them. The engines are plugins: Pipelex names none of them by import, and which formats a runtime prints depends only on which engines are installed in it.

Open Pipelex ships one, the built-in `reportlab` plugin, which prints a `pdf` from the auto-layout of a step's inputs. The Pipelex document generation plugin, `pipelex-doc-gen`, registers the engines for a `pdf` from an HTML template and for the office formats from outside this repository, through the same seam this page documents.

---

## Engines are keyed by format and source

A step asks for a **format** (`pdf`, `xlsx`, `docx`, `pptx`), and its template decides the **source** the compose stage hands an engine:

| The step has | Source | What the engine receives |
| --- | --- | --- |
| No template | `layout` | The layout tree of the inputs |
| An HTML `template` or `.html` `template_file` (a `pdf` only) | `html` | The template rendered against the inputs |
| An office `template_file` | `template_file` | The file's bytes and the inputs as plain data |

A `pdf` from the layout tree and a `pdf` from HTML are different engines, so an engine registers for a format **and** a source, under an engine name:

```python
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar


class MyDocGenPlugin:
    name = "my_doc_gen"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_document_renderer(
            doc_gen_format=DocGenFormat.XLSX,
            source=DocGenSource.TEMPLATE_FILE,
            engine="openpyxl",
            make_renderer=make_xlsx_renderer,
            check_template=check_xlsx_template,
        )
```

A document engine is a kernel-layer capability, so an out-of-tree engine publishes under the `pipelex.plugins.kernel` entry-point group (see [Inference Backend Plugins](inference-backend-plugins.md#shipping-it-as-an-out-of-tree-plugin) for the groups). `make_renderer` is called once per process, the first time a document is printed with the engine, and never at registration, so `register` stays import-light and a process that never prints never imports the engine's library. A second registration of the same engine name for the same format and source fails loud at boot with `DuplicateDocumentRendererError`, naming both plugins.

---

## Refused at load, not at run

When a method loads, each `PipeDocGen` step resolves its format and source in the registry. If no installed engine prints them, the step is refused right there with `DocGenEngineMissingError`, before a run spends anything on inference: the error names the format, the source and the plugin that prints it. A runtime therefore needs no rule of its own about what it prints: a host that must not print documents disables the built-in plugin with `runtime.plugins.disabled = ["reportlab"]` and installs no other engine, and every `PipeDocGen` step is refused at load.

When two installed engines print the same format from the same source, the configuration chooses one, keyed by `format.source`:

```toml
[runtime.doc_gen]
engines = { "pdf.layout" = "reportlab" }
```

Without a choice, two engines for one key raise `DocumentEngineChoiceError`, and so does a choice that names an engine that is not installed.

---

## The contract: a render job in, bytes out

An engine implements `DocumentRendererProtocol` from `pipelex.cogt.doc_gen.render_job`:

```python
def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument: ...
```

- **`RenderJob`** is plain data, which crosses a process boundary as JSON (the template's bytes as base64): the format and source, the file's name with its suffix, the document's title, and exactly the payload its source names, `layout` (a `LayoutDocument` from `layout_tree.py`), `html`, or `template` with `data`, the inputs as plain data by input name. It carries no Pipelex object, so an ordinary Pipelex release does not break an engine; a change to it is a change of the plugin contract.
- **`RenderResources.load(uri=…, position=…)`** is how an engine reads a file its document names, such as an image. It resolves `pipelex-storage://` keys through the run's storage provider, decodes `data:` URLs, fetches `https://` through the SSRF guard, and refuses what the run's read scope does not allow, a local path included, with `UriReadRefusedError`. An engine reads nothing any other way.
- **`RenderedDocument`** holds the bytes. Their MIME type and suffix are the format's.

`render` is synchronous and runs in a worker thread, while `RenderResources.load` hands each read back to the event loop the print started from. One engine instance serves every print of its process, so it keeps no state from one print into the next. An engine signals a document it cannot print with a `ValueError`, which Pipelex reports as `DocGenRenderError`.

---

## The template checker

An office template names the fields it is filled with in its own way, which Pipelex cannot read: an Excel workbook through its defined names and Tables, a Word document through its tags. So an engine that fills a template file may register a `check_template` beside its renderer (`pipelex.cogt.doc_gen.template_check`):

```python
def check_template(*, request: TemplateCheckRequest) -> list[TemplateFinding]: ...
```

The request carries the template file's bytes and name, the shape of each input as an `InputShape` tree (which fields exist, which are lists, and what their items hold), and the dry run's mock inputs as plain data, so the checker can also fill the template in memory. The dry run, and so `pipelex validate`, calls it for every step with a template file that the engine prints: a finding of severity `error` fails the step with `PipeDocGenTemplateCheckError`, listing the findings, and a `warning` is logged. Pipelex checks HTML templates itself, against the inputs' concepts, so an HTML engine registers no checker.

---

## Where the print stage runs

The print stage is a content-generation leaf, like image generation or extraction: `ContentGenerator.make_rendered_document` hands a `RenderDocumentAssignment` to `render_document_and_store`, which authorizes the images the document names against the run's read scope, takes the dry-run branch, prints and stores the file, and returns only the `DocumentContent` pointing at it, so the file's bytes never cross a workflow boundary. The dry run composes for real, which checks the templates against mock inputs, runs the template checker, and prints and stores nothing. See [Content Generation Across Boundaries](distributed-content-generation.md) for the leaves.

---

## Related

- [PipeDocGen](../building-methods/pipes/pipe-operators/PipeDocGen.md) — the operator, its formats and its templates
- [Inference Backend Plugins](inference-backend-plugins.md) — plugin discovery, the entry-point groups and the `runtime.plugins.disabled` denylist
- [Storage Provider Plugins](storage-provider-plugins.md) — where the printed file is stored
- [Template Sandbox](template-sandbox.md) — what a composed template may read
