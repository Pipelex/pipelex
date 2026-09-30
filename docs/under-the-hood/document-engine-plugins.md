---
title: "Document Engine Plugins"
description: "How a PipeDocGen step finds the engine that prints it, a model of the doc_gen family, the render job an engine receives, the template checker it may offer, and how a runtime refuses at load what it cannot print."
---

# Document Engine Plugins

A [`PipeDocGen`](../building-methods/pipes/pipe-operators/PipeDocGen.md) step turns its inputs into a document file in two stages. The **compose stage** is Pipelex's own and is pure: it lays the inputs out, or renders the step's HTML template, or gathers the inputs as plain data for a template file, and it renders the file's name. The **print stage** hands the result to a **document engine**, which returns the file's bytes, and Pipelex stores them.

A document engine is a **model** of the `doc_gen` family, chosen the way a step chooses any model: by the step's `model`, or by the model deck's default. Its worker is contributed by a plugin, through the same `add_inference_backend` seam the inference backends use. Open Pipelex ships one engine, `reportlab-pdf`, which prints a `pdf` from the auto-layout of a step's inputs. The Pipelex document generation plugin, `pipelex-doc-gen`, registers the engines for a `pdf` from an HTML template and for the office formats from outside this repository.

---

## Sources, and the engines that print them

A step asks for a **format** (`pdf`, `xlsx`, `docx`, `pptx`), and its template decides the **source** the compose stage hands an engine:

| The step has | Source | What the engine receives |
| --- | --- | --- |
| No template | `layout` | The layout tree of the inputs |
| An HTML `template` or `.html` `template_file` (a `pdf` only) | `html` | The template rendered against the inputs |
| An office `template_file` | `template_file` | The file's bytes and the inputs as plain data |

Each engine is declared in the `internal` backend's `internal.toml`, with the sources it prints from as its `inputs` and its format as its `outputs`:

```toml
[reportlab-pdf]
model_type = "doc_gen"
sdk = "reportlab"
model_id = "print-pdf"
inputs = ["layout"]
outputs = ["pdf"]
costs = {}
```

| Engine | Prints | From | Comes with |
| --- | --- | --- | --- |
| `reportlab-pdf` | `pdf` | `layout` | Pipelex |
| `weasyprint-pdf` | `pdf` | `html`, `layout` | `pipelex-doc-gen` |
| `openpyxl-xlsx` | `xlsx` | `layout`, `template_file` | `pipelex-doc-gen` |
| `docxtpl-docx` | `docx` | `layout`, `template_file` | `pipelex-doc-gen` |
| `python-pptx` | `pptx` | `template_file` | `pipelex-doc-gen` |

The model deck's `5_doc_gen_deck.toml` names the default engine for each format and source, keyed `<format>.<source>`, and a key naming a format and source no step can ask for fails when the deck loads:

```toml
[doc_gen.choice_defaults]
"pdf.layout" = "@default-pdf"
"pdf.html" = "@default-pdf-from-template"
"xlsx.layout" = "@default-xlsx"

[doc_gen.aliases]
default-pdf = "reportlab-pdf"
default-pdf-from-template = "weasyprint-pdf"
default-xlsx = "openpyxl-xlsx"
```

A step that names no engine prints on the deck's default, so it follows the install's deck, as an LLM step does. A step that names one, such as `model = "weasyprint-pdf"` on a `pdf` without a template, prints on that engine wherever it runs.

---

## Registering an engine

A plugin registers a worker factory for an engine's sdk in the `doc_gen` family:

```python
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar


class MyDocGenPlugin:
    name = "my_doc_gen"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.DOC_GEN, sdk="openpyxl", make_worker=make_xlsx_worker)
```

A document engine is a kernel-layer capability, so an out-of-tree engine publishes under the `pipelex.plugins.kernel` entry-point group (see [Inference Backend Plugins](inference-backend-plugins.md#shipping-it-as-an-out-of-tree-plugin) for the groups). `make_worker` is called for each print, with the model's spec, and imports the engine's library inside it, so `register` stays import-light and a process that never prints never imports the library. An engine loads its library, fonts and styles once per process, in the module that holds its worker, rather than per worker. A second registration of the same sdk fails loud at boot with `DuplicateInferenceBackendError`, naming both plugins.

---

## Refused at load, not at run

When a method loads, each `PipeDocGen` step resolves its engine: the model it names, or the deck's default for its format and source. The step is refused right there, before a run spends anything on inference, when:

- the deck names no engine for its format and source, and it names none (`DocGenEngineMissingError`, which says to run `pipelex update`);
- the engine it names is not a model the deck defines (an unknown model, located on the step's `model` field);
- the engine does not print its format from its source, by the `inputs` and `outputs` it declares (`DocGenModelCapabilityError`);
- no installed plugin registers the engine's sdk (`DocGenEngineMissingError`, naming the engine and `pipelex-doc-gen`, or saying the built-in engine is disabled).

The other model families find a missing worker only when they build it, at run time; a document engine is checked when the method loads as well. A runtime therefore needs no rule of its own about what it prints: a host that must not print documents disables the built-in plugin with `runtime.plugins.disabled = ["reportlab"]` and installs no other engine, and every `PipeDocGen` step is refused at load.

---

## The contract: a render job in, bytes out

An engine's worker subclasses `DocGenWorkerAbstract` from `pipelex.cogt.doc_gen.doc_gen_worker_abstract`:

```python
def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument: ...
```

- **`RenderJob`** is plain data, which crosses a process boundary as JSON (the template's bytes as base64): the format and source, the file's name with its suffix, the document's title, and exactly the payload its source names, `layout` (a `LayoutDocument` from `layout_tree.py`), `html`, or `template` with `data`, the inputs as plain data by input name. It carries no Pipelex object, so an ordinary Pipelex release does not break an engine; a change to it, or to the worker, is a change of the plugin contract.
- **`RenderResources.load(uri=…, position=…)`** is how an engine reads a file its document names, such as an image. It resolves `pipelex-storage://` keys through the run's storage provider, decodes `data:` URLs, fetches `https://` through the SSRF guard, and refuses what the run's read scope does not allow, a local path included, with `UriReadRefusedError`. An engine reads nothing any other way.
- **`RenderedDocument`** holds the bytes. Their MIME type and suffix are the format's.

`render` is synchronous and runs on a thread of a print pool of its own, never on the event loop's default executor, which the engine's reads need, while `RenderResources.load` hands each read back to the event loop the print started from. An engine keeps no state from one print into the next. It signals a document it cannot print by raising `DocGenRenderError`, which passes through; anything else it raises, beyond a Pipelex error, is reported as a `DocGenRenderError` naming the engine and the file.

---

## The template checker

An office template names the fields it is filled with in its own way, which Pipelex cannot read: an Excel workbook through its defined names and Tables, a Word document through its tags. So an engine that fills a template file overrides its worker's `check_template` (the request and findings are in `pipelex.cogt.doc_gen.template_check`):

```python
def check_template(self, *, request: TemplateCheckRequest) -> list[TemplateFinding]: ...
```

The request carries the template file's bytes and name, the shape of each input as an `InputShape` tree (which fields exist, which are lists, and what their items hold), and the dry run's mock inputs as plain data, so the checker can also fill the template in memory. The dry run, and so `pipelex validate`, calls it for every step with a template file: a finding of severity `error` fails the step with `PipeDocGenTemplateCheckError`, listing the findings, and a `warning` is logged. The default finds nothing: Pipelex checks HTML templates itself, against the inputs' concepts, and the built-in engine takes no template.

---

## Where the print stage runs

The print stage is a content-generation leaf, like image generation or extraction: `ContentGenerator.make_rendered_document` hands a `RenderDocumentAssignment`, which carries the composition and the resolved engine, to `render_document_and_store`. The leaf authorizes the images the document names against the run's read scope, takes the dry-run branch, builds the engine's worker, prints and stores the file, and returns only the `DocumentContent` pointing at it, so the file's bytes never cross a workflow boundary. The dry run composes for real, which checks the templates against mock inputs, runs the template checker, and prints and stores nothing. See [Content Generation Across Boundaries](distributed-content-generation.md) for the leaves.

---

## Related

- [PipeDocGen](../building-methods/pipes/pipe-operators/PipeDocGen.md) — the operator, its formats, its templates and its `model`
- [Inference Backend Plugins](inference-backend-plugins.md) — plugin discovery, the entry-point groups and the `runtime.plugins.disabled` denylist
- [Storage Provider Plugins](storage-provider-plugins.md) — where the printed file is stored
- [Template Sandbox](template-sandbox.md) — what a composed template may read
