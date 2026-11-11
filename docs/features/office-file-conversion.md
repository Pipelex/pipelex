---
title: "Office File Conversion"
description: "How Pipelex converts a Word, Excel or PowerPoint file to PDF when the step reading it needs one: the Gotenberg and soffice backends, which steps convert, what a conversion drops, where the PDF is kept, the file_converted trace event and the errors."
---

# Office File Conversion

A `Document` input may hold an Office file: Word (`.docx`, `.doc`, `.odt`), Excel (`.xlsx`, `.xls`, `.ods`) or PowerPoint (`.pptx`, `.ppt`, `.odp`). Many models read only PDFs, and page views are always drawn from a PDF. When the runtime has a document converter, a step that cannot read an Office file as it is reads the file's PDF instead, which Pipelex makes, keeps and reuses. Without a converter, which is the default, nothing is converted and such a file is refused as it always was.

The converter, its configuration and its trace record belong to the Pipelex runtime. The MTHDS standard only says that a `Document` may be a PDF or an Office file; how a runtime gets a model to read one is the runtime's business.

## Turning it on

Conversion is off until `[runtime.document_conversion]` names a backend:

```toml
# .pipelex/pipelex.toml
[runtime.document_conversion]
backend = "gotenberg"          # "none" (the default), "gotenberg" or "soffice"
max_source_bytes = 50_000_000

[runtime.document_conversion.gotenberg]
url = "http://localhost:3000"
timeout_seconds = 360
budget_seconds = 120

[runtime.document_conversion.soffice]
binary = "soffice"
timeout_seconds = 120
```

Every value above except `backend` and `url` is the default. [Document Conversion Configuration](../configuration/config-technical/document-conversion-config.md) describes each key. With `backend = "none"`, every check and every step behaves exactly as if conversion did not exist.

A backend that is named but cannot be used stops Pipelex at startup with `runtime.misconfigured`, rather than at the first Office file a run reads: a Gotenberg backend whose `url` is empty or is not an absolute `http` or `https` URL naming a host, or a `soffice` binary that is not found. A Gotenberg container that is down at startup is not a misconfiguration; a step that needs it then fails as the converter being unavailable. A Gotenberg `timeout_seconds` that does not exceed `budget_seconds` is refused when the configuration loads, with `pipelex.config.invalid`.

## The backends

Each backend drives LibreOffice and makes the same export: the document's printed pages, as it would print on paper.

- **Gotenberg** posts the file to a [Gotenberg](https://gotenberg.dev) container over HTTP (`POST <url>/forms/libreoffice/convert`), always named `document.<extension>` so that nothing of a person's file name reaches the converter's logs. It needs Gotenberg 8.39.0 or later. This is the backend for a server: a server that reads other people's files runs Gotenberg in a container of its own, which keeps a hostile file away from the process running Pipelex, its files and its credentials. For a quick local container, run `docker run --rm -p 3000:3000 gotenberg/gotenberg:9`.
- **soffice** runs LibreOffice's `soffice --headless --convert-to pdf` on this machine, once per conversion, in a temporary directory with a fresh LibreOffice profile, and kills its whole process group at the timeout. It is meant for a developer's machine and for tests. It is **not an isolation boundary**: `soffice` reads the file with the rights of the process that runs Pipelex, so never use it on a server that converts files you did not write.

Each PDF is stamped with the version of the converter that made it, as its `converter-version` metadata:

- **Gotenberg's** is the version the container names in the `Gotenberg-Version` header of the very answer that carried the PDF, such as `9.2.0`. Read off each conversion's answer, it is the version of the process that converted the file, so a container redeployed while Pipelex runs stamps the PDFs it makes from then on with its new version. Gotenberg names its version on a conversion's answer from 8.39.0 on, so the Gotenberg backend needs **Gotenberg 8.39.0 or later**. A `200` whose answer names no version, which an older Gotenberg or a proxy stripping the header gives, fails the step with `runtime.misconfigured`, a fault of the deployment for its operator to fix, and its PDF is never kept.
- **soffice's** is the line of `soffice --version`'s standard output that starts with `LibreOffice`, so a warning LibreOffice prints first, such as one about `javaldx`, is never taken for it. It is read once and kept for the life of the process.

### How Gotenberg's answers are read

A LibreOffice engine dying in the middle of a conversion answers exactly as a damaged file does, so the Gotenberg backend reads the container's statuses before deciding whose fault a failure is:

| Gotenberg answers | What the backend does |
|---|---|
| `200` with a PDF | Uses it, stamped with its `Gotenberg-Version` header. A `200` that is not a PDF is a fault of the converter, `runtime.unexpected`; one whose answer names no version comes from a Gotenberg older than 8.39.0 or through a proxy stripping the header, `runtime.misconfigured`. Neither is retried. |
| `400`, `422`, `500` or `504` | Posts the file once more at once; a second such answer means the file is unreadable, `input.file_unreadable`. |
| `413` | The file is too large for the converter, `input.too_large`, final. |
| `503` | The conversion ran out of its budget, `input.too_large`, final. |
| `429`, a refused connection, a connection dropped before the budget, or any other status | Says nothing about the file: tried again after 1, 2 and 4 seconds, then `runtime.unavailable`. |
| A connection dropped after the budget, read timeout included | The file outran the converter's budget, `input.too_large`, never retried. |

The budget is `budget_seconds`, which must match the container's own `--api-timeout`, and `timeout_seconds` must exceed it so that the client is still waiting when the budget runs out: a hostile file was measured holding a connection for about six minutes before Gotenberg closed it.

## Which steps convert, and why

Only the steps that hand a document to a model convert: a `PipeExtract` step, and the documents a `PipeLLM` or a `PipeJudge` prompt references. Every other step, and the working memory, see the Office file as it was given.

A step reads an Office file as its PDF when the runtime has a converter and either of these holds:

- **The step asks for page views, and some model that may serve it reads PDFs.** Page views are drawn from a PDF, so a `PipeExtract` step with `page_views = true` reads the PDF even when its model also reads the Office format. The extraction then reads the same PDF, so the page views and the extracted pages always match. A step whose models read no PDF keeps the original and refuses its page views, as it would without a converter, before any conversion is paid for; a model that could not be resolved may read PDFs, so its step converts.
- **A model that may serve the step does not read the file's format, and some model that may serve it reads PDFs.** The models that may serve a step are the one its handle or alias resolves to, or every member of a waterfall. A waterfall whose later member reads only PDFs therefore never receives a Word file, even when its first member reads Word: every member receives the PDF.

Otherwise the step reads the original. A step whose models all read the file's format sends the original, unless it asks for page views. A step whose models read no PDF either sends the original too, with or without page views, since a PDF would not help, and the refusal it would meet without a converter stands. A document of unknown format, such as a URL that declares no type, is left to the model as before.

Which formats a model reads is in each model's spec. The LLMs that read Office files read only `.docx`, `.xlsx` and `.pptx`, so a legacy (`.doc`, `.xls`, `.ppt`) or OpenDocument (`.odt`, `.ods`, `.odp`) file always converts for a `PipeLLM` or `PipeJudge` whose model reads PDFs. For extraction, see [Formats Each Extractor Reads](document-extraction.md#formats-each-extractor-reads).

**Only the model's input changes.** The URI and MIME type the model receives become the PDF's; the prompt's document keeps its place and its `[Document N]` token. The step's output, the run's inputs and every later step still see the Office file, and the PDF stays a derived object, never a value of the run.

**Run setup agrees with the step.** Before a run starts, Pipelex refuses a file input certain to reach a step that cannot read it (see [File formats are checked before the run](../building-methods/concepts/native-concepts.md#file-formats-are-checked-before-the-run)). With a converter, an Office file that such a step would read as its PDF passes, and setup logs `A step will read an Office file as its PDF` with the input, the step, the format and the reason (`page_views` or `model_format`). Setup and the step apply one rule, so a file setup accepts is the file the step converts, and a step reached through a condition, which setup leaves alone, refuses at the step exactly what setup would have refused. Setup only logs the conversions: each step decides again when it runs and converts then, which also covers steps reached through a condition and files the run produced. Without a converter, a refusal that a converter would have avoided says so: its advice ends with "or configure a document converter".

**Dry runs convert nothing.** A dry run draws no model input, so it never calls the converter, and mock inputs are placeholders that setup already skips.

**What it costs.** A conversion takes under a second for an ordinary Office file and several seconds for a very large workbook. A PDF kept from an earlier conversion costs one metadata read and one read of the PDF, whose pages are counted. A step reading a PDF is billed by its model on the PDF's pages, and the trace records the page count that explains it.

## What a conversion drops

A PDF of the printed pages holds what the document would show on paper, which is not everything the file holds. Measured on Word, Excel and PowerPoint test files, a conversion:

- drops comments in a Word document;
- leaves out hidden sheets in a workbook;
- drops a presentation's speaker notes;
- shows a tracked change's deleted and inserted text side by side in the text, as if both were current;
- cuts a sheet wider than a page, and a wide chart, across several printed pages.

Everything else reached the page. LibreOffice also substitutes other fonts for those the converter's machine lacks, so lines may rewrap and slides overflow: give the converter the fonts your documents use, or metric-compatible substitutes such as Carlito for Calibri and Liberation Sans for Arial. When a step must read what a conversion drops, give it a model that reads the Office format itself and ask for no page views, so the original is sent.

## Where the PDF is kept

A PDF is made once and kept, so that the next step, or the next run, reading the same file reuses it.

- **A source in storage** (`pipelex-storage://…`) has its PDF beside it, at `<source key>.pdf` with the source's extension lowercased: the PDF of `org/assets/report.DOCX` is `org/assets/report.docx.pdf`. Pipelex's hosted platform writes the PDFs of its previews at the same key with the same metadata entries, so a file converted for its preview is not converted again for a run, nor the other way round.
- **A source outside storage**, an `http(s)` URL, a local path or a `data:` URL, has no key to stand beside. Its PDF goes under the run's storage scope, named by the SHA-256 of the source's bytes and its format: `<storage scope>/<sha256>.<format>.pdf`. Every step of the run that reads the same file then converts it once, and a purge of the run erases the PDF.

Every PDF is written create-only, with the content type `application/pdf` and the metadata entries `converter-version`, the version of the converter that made it, and `export-options: printed-pages`. When two steps convert the same file at once, the first write wins and both read the stored PDF: the step whose write lost reads the PDF it found there as a kept one, and its trace record gives that PDF's `converter-version` and page count, not those of the conversion it threw away. Should the winner have stored an object that is not a printed-pages PDF, the step fails with `runtime.unexpected`.

A PDF found at its key is reused when its metadata says `export-options: printed-pages`, whatever its `converter-version`; replacing PDFs made by an older converter is not done yet. An object at `<source key>.pdf` whose metadata names another export, or that PDFium cannot open, is not the PDF the step wants, and since it cannot be replaced, the run converts the file and keeps its own PDF under its storage scope instead. The key under the run's storage scope cannot be replaced either, and only the runtime writes there, so a PDF there that does not open fails the step with `runtime.unexpected`, a fault of the storage rather than of the file. A storage provider that keeps no metadata, such as a storage plugin written before metadata existed, answers none for any object, and an object at the PDF's key is then taken for a printed-pages PDF of unknown version, so that such a storage still reuses its PDFs (see [Storage Provider Plugins](../under-the-hood/storage-provider-plugins.md#object-metadata)).

The run's read scope applies to the source as to every file a step reads: a source outside it is refused before anything is converted.

## What the trace records

Each document a step reads as its PDF is recorded on the step's node as a `file_converted` trace event, once per document, written as soon as the step has its PDF and before its model is called. A step that fails afterwards therefore still records the conversion it paid for. The event carries the step's node, the document's input path or prompt variable, the original's format, whether the PDF was `kept` or `made`, the converter's name and version, the PDF's page count and, for a PDF this step made, how long the conversion took. [Execution Graph Tracing](../under-the-hood/execution-graph-tracing.md#trace-events) lists its fields. The execution graph does not draw it.

Each step that reads a PDF also logs `A step reads an Office file as its PDF`, with the step, the input, the format, whether the PDF was kept or made, the converter's version and the page count.

## Errors

A conversion adds no error code: each outcome takes the code the error model already has for it. Every failure names the input the document came from, and the step retries none of them; what is worth retrying, the backend retries before it fails.

| What happened | Code |
|---|---|
| The converter could not read the file: damaged, protected by a password, not what its format says, Gotenberg answering `400`, `422`, `500` or `504` twice, or `soffice` producing no PDF. A PDF beside a source in storage that does not open is not this: it is set aside, and the run converts the file. | `input.file_unreadable`, its `reason` being `conversion_failed` |
| The source is larger than `max_source_bytes`, refused before it is read when it is in storage, and before it is sent otherwise | `input.too_large`, with `limit` and `size` in bytes |
| Gotenberg answered `413` | `input.too_large`, with the file's `size` and no `limit`, since the converter does not say its limit |
| The conversion ran out of time: Gotenberg answered `503`, the connection dropped after the budget, or `soffice` was killed at its timeout | `input.too_large`, with neither `limit` nor `size`, its message saying the input is too large in size or in the time it takes to process; the seconds are in the operator's diagnostics |
| The converter is busy or unreachable after the backend's own retries | `runtime.unavailable`, naming the dependency `document_converter`; an orchestrator retries the step as it retries that code |
| The converter answered a `200` that is not a PDF PDFium opens, the key a run keeps a PDF under holds an object that is not a printed-pages PDF PDFium opens, or a concurrent step won a PDF's key with such an object | `runtime.unexpected` |
| A step needs a conversion in a process that has no converter, or on a host whose content generator does not convert | `runtime.misconfigured`, naming the component `runtime.document_conversion` |
| The configured backend cannot be used at startup | `runtime.misconfigured`, at startup |

Without a converter, an Office file a step cannot read is refused as before, with `input.file_type_unsupported`.

## Distributed execution

On a host runtime such as Temporal, a step's code may run in workflow code, which does no input or output. So the step only decides whether to read the PDF, and finding or making the PDF is a leaf of the content generator, `make_readable_pdf`, which the host dispatches as an activity like every other leaf. The leaf writes the PDF to storage and returns its URI, never its bytes, so a PDF never crosses the host's boundary. A host whose content generator does not implement this leaf fails the step that needs a PDF with `runtime.misconfigured` rather than converting in workflow code, and a deployment with no converter is not affected. The step decides from the converter configured in the process running it, and the leaf converts with the one configured in the process running it, so configure `[runtime.document_conversion]` the same way in every process of the deployment.

## Running the integration tests

The tests that convert real Office files carry the `document_conversion` marker, which every default test run excludes. Run them with:

```bash
make test-document-conversion   # or: make tdc
```

They run once per backend and skip a backend this machine lacks. The `soffice` backend uses the executable that `PIPELEX_TEST_SOFFICE_BINARY` names, or `soffice` on the `PATH`; the Gotenberg backend uses the container at `PIPELEX_TEST_GOTENBERG_URL`:

```bash
docker run --rm -p 3000:3000 gotenberg/gotenberg:9
PIPELEX_TEST_GOTENBERG_URL=http://localhost:3000 make tdc
```

They convert `.docx`, `.xlsx` and `.pptx` test files and check each PDF's page count, then run an extraction with page views on each file and check that a second read reuses the kept PDF. One more test runs a `PipeLLM` step on a Word CV through a model that reads only PDFs; it calls a model, so it runs only live, with `.venv/bin/pytest -m document_conversion --pipe-run-mode live tests/integration/pipelex/tools/document_conversion`.

## Related Documentation

- [Document Conversion Configuration](../configuration/config-technical/document-conversion-config.md) - Every key of `[runtime.document_conversion]`
- [Document Extraction](document-extraction.md) - The extractors and the formats each reads
- [Page views need a PDF](../building-methods/pipes/pipe-operators/PipeExtract.md#page-views-need-a-pdf) - What a `PipeExtract` step asking for page views reads
- [Storage Provider Plugins](../under-the-hood/storage-provider-plugins.md#object-metadata) - The object metadata a kept PDF carries
- [Execution Graph Tracing](../under-the-hood/execution-graph-tracing.md#trace-events) - The `file_converted` trace event
