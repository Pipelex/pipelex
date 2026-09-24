---
status: draft
item: L-260924-577415
---

# File inputs whose format their consumer cannot read are refused before the run

This design fixes two bugs on one branch. L-260924-577415: a Word transcript given to a `Document` input fails at the method's first `PipeExtract` on the hosted plane, a few seconds into the run, with the extract backend's refusal. L-260924-600272: a PDF given to an `Image` input fails at the first `PipeLLM` that looks at it, with a provider error that carries no error domain. They share one cause. The runtime never establishes what format a file input actually is, so nothing compares that format with what will consume it until a provider refuses the bytes, mid-run, in its own words.

The investigation was done at `a02b77ac7` (v0.63.0). File and line references below are to that tree.

## What happens today

**The hosted path for a Word document.** The MCP tool `mthds_prepare_inputs` (pipelex-mcp, through the SDK's `prepareInputs`) uploads the file and rewrites the input to `{"url": "pipelex-storage://…/<uuid>.docx"}` with no `mime_type`. The platform's run gate checks the URI's scheme and organisation, and the runner starts the run. At run setup, `normalize_data_urls_to_storage` leaves a `pipelex-storage://` URI untouched (`pipeline/input_normalizer.py:285-287`), so the `DocumentContent` still has `mime_type=None` when the run starts. `PipeExtract` passes only the URL into `ExtractInput` (`pipe_operators/extract/pipe_extract.py:122-141`). The extract worker's capability check accepts any document when the model declares `pdf` or `web_page`, whatever the file is (`cogt/extract/extract_worker_abstract.py:53-67`). `GatewayExtractWorker` then loads the bytes, sniffs them correctly as `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, builds the data URL and sends it through Portkey (config `pc-pipele-982905`) to the relay. The relay accepts only PDF, JPEG and PNG (`pipelex-relay/pipelex_relay/api/routes/openai_routes.py:43-48`) and answers "Could not parse the provided data URL". The runtime classifies that 400 as a content error, so the run fails with `ExtractJobFailureError` in the input domain, in the relay's words.

**Azure is not the refuser.** Azure Document Intelligence's `prebuilt-layout` at api-version `2024-11-30` reads DOCX, PPTX, XLSX and HTML as well as PDF and images. Manifold, the gateway replacing the relay, already forwards all of them (`pipelex-manifold/src/providers/azure-document-intelligence/core.ts:187-199`, the `wider-input-types` entry in `harness/parity.ts`). Manifold's spike proved it with the runtime's own extract tests on a `.docx` fixture. The relay will not be widened: L-260824-25253a records that nobody should invest in it and that the earlier widening request was withdrawn. Manifold is not deployed yet. Its cutover is sprint L-260917-24ace1, and the runtime backend and profile it needs is L-260917-0ba8ed.

**The PDF in an `Image` slot.** Preparation uploads it the same way. `PromptImageFactory.make_prompt_image` is built from the URL alone and drops the content's `mime_type` (`kernel/llm_prompt_content.py:232`). `_check_vision_support` counts images and checks that the model has vision, but never looks at a format (`cogt/llm/llm_worker_abstract.py:419-429`). The provider factory sniffs `application/pdf` and sends it as an image, and the provider refuses it. `PromptImageFormatError` exists, in the content category, and nothing raises it (`cogt/exceptions.py:379`).

**What the runtime already has.** The file-type sniffer (`tools/misc/filetype_utils.py`, over `filetype`, which reads only the first 8192 bytes) recognises PDF, the Office Open XML formats, the legacy Office formats and images. The LLM path already compares a document's type with the model's declared `supported_document_types` (`llm_worker_abstract.py:431-448`), but it skips a document whose type is unknown, which is every `pipelex-storage://` document on the hosted plane. Model specs declare what they read in `inputs`, which is a free list of strings (`cogt/model_backends/model_spec.py`). Run setup, `prepare_pipe_job` (`pipeline/execution_seams.py:159-322`), runs in the runner process before any orchestrator is involved, so it may do IO, and an input-domain error raised there reaches the caller as a 422 on `/start`. The platform relays a runner 4xx at `/start` as a 422 carrying the runner's reason (`pipelex-server/platform/src/pipelex_platform/routers/v1/execution.py`, `_start_failure`).

## Decisions

### D1. No conversion to PDF

The ledger item offered two ways out: convert Word and PowerPoint documents to PDF before extraction, or refuse them before the run. We refuse, and we do not convert.

Conversion would fix a limitation that belongs to the relay, which is being retired, and not to the model, which reads these formats natively. It would need LibreOffice (or an equivalent) in the runner and worker images: a large native dependency that parses untrusted Office files inside the hosted plane. It would silently change what the model sees, because a converted layout is LibreOffice's rendering and not the author's, and it would change the page count the extraction is billed on. Once the hosted plane extracts through manifold and the remote config declares the formats Azure reads, a Word document extracts with no runtime change at all. Until then, the honest outcome on the hosted plane is a refusal before the run that names the formats that work.

### D2. A file input's format is established once, at run setup

At run setup, after the inputs are shaped and relocated to storage, every `ImageContent` and `DocumentContent` in the working memory, including list items and fields nested in structured content, gets a `mime_type` that describes its bytes. The walk is the normalizer's existing walk, and it also carries each file's path in the inputs (`transcripts[2]`, `case.attachment`) for error messages.

- **The sniffed type wins.** A data URL's bytes are already decoded and a local file is already read, so the sniff costs nothing there. A `pipelex-storage://` URI gets a head read of the first 8192 bytes, which is exactly what the sniffer reads. When the sniff identifies the bytes, its MIME type replaces any declared one, because the bytes are the truth: `data:image/png;base64,<a PDF>` becomes `application/pdf`.
- **When the sniff cannot identify the bytes**, which is the case for plain text, Markdown, CSV, JSON and HTML, the declared MIME type stands. A missing declaration and the generic `application/octet-stream` both mean unknown.
- **An http(s) input is not fetched before the run.** Setup stays free of outbound requests to caller-chosen hosts, which matters while the fetch path's SSRF guard is still open (L-260823-6e13cf). Its format stays whatever the caller declared. This is a known residual, covered by D4's operator check once the bytes are loaded.
- **Identification runs whether or not relocation to storage is enabled**, and is skipped only for mock inputs. Today an unidentifiable `data:` URL raises `FileTypeError`, which has no domain and answers 500. The same change makes that case fall back to the declared type.
- **The head read is a new storage-provider method.** `StorageProviderAbstract` gains a concrete `load_head(uri, *, nb_bytes)` whose default loads the whole object and slices it, so an external storage plugin keeps working unchanged. The S3 and GCP providers override it with a ranged read. File inputs are identified concurrently, with a bound, so a list of documents does not cost a round-trip each in sequence.

The stamped `mime_type` then rides the working memory into the run, including across the Temporal payload, and the operators read it instead of guessing again. `PromptImageFactory` receives the image's `mime_type` the way documents already receive theirs.

### D3. An `Image` holds an image

A file in an `Image` slot whose identified format is not an image is refused at run setup, whatever will consume it. This check does not depend on any model: an `Image` holding a PDF is wrong for every consumer. It is enforced on the content class, so it covers every concept that refines `Image` and every nested or listed image. It fires only on a positive identification. An image the sniffer cannot identify, such as an SVG, is left to its consumer.

`Document` gets no such check. The native concept covers PDF, the Office formats and web pages, and whether a given document is readable depends on who reads it, which is D4 and D5.

A second line holds mid-run for images the run produces itself: the LLM worker refuses a prompt image whose format is not an image with `PromptImageFormatError`, which is in the content category and so in the input domain.

### D4. Models declare the formats they read, and consumers check against the declaration

**The vocabulary.** A file's format key derives from its MIME type through one function shared by every check. Every `image/*` type maps to `image`. Any other type maps to its extension, for example `pdf`, `docx`, `pptx`, `xlsx`, `doc` or `html`. An unknown type has no key. A model spec's `inputs` names the formats it reads with the same keys. The keys that already exist keep their meaning: `pdf`, `image` and `web_page` for extractors, and `images`, `pdf`, `docx` and `pptx` for LLMs. Extractors may now also declare `docx`, `pptx`, `xlsx` and `html`. The vision flag stays spelled `images`: renaming it would need a new remote-config version, which buys nothing here.

**The extract check.** `ExtractInput` carries the file's `mime_type` and the name of the input it came from. `ExtractWorkerAbstract._check_can_perform_job` refuses a document or image whose format key is known and not among the model's readable formats. The refusal is a new `ExtractInputFormatError`, in the content category and so in the input domain. Its message names the input, the format received, the model, and the formats the model reads. A model that reads `web_page` and receives an http(s) URL is not format-checked, because it fetches the page itself. An unknown format is not refused, and the provider decides.

**The LLM document check.** A document whose format the model does not read becomes a new `PromptDocumentFormatError`, also in the content category. Today this case raises `LLMCapabilityError`, which is a configuration error and answers 500. `LLMCapabilityError` stays for a model that reads no documents at all, which is the author's choice of model and not the caller's input.

**Why the input domain.** The model is fixed by the method and was valid for the formats it declares. The file changes from run to run, and the person who can act is the one supplying it. The message still names the author's remedy, choosing a model that reads the format, for the case where the person running the method is also its author.

**Declarations in this repository.** `docling-extract-text` declares `docx`, `pptx`, `xlsx` and `html`, because docling's converter reads them and the worker already writes the file with its real extension. It will be proven by a test before it is declared. `pypdfium2-extract-pdf` stays `pdf` only. Mistral OCR stays `pdf` and `image` until a live test proves more. The remote config is another repository and a follow-up (see below).

### D5. The pre-run consumer check

D4 fails the right way, but still mid-run, after earlier steps may have spent tokens. The ledger item's title is precisely that the failure comes only after the run starts. So at run setup, after D2 and D3, the runtime walks the entry pipe statically to find which operators will consume each file input, and refuses the run when an input is certain to reach a consumer that cannot read its format.

**The walk** starts from the entry pipe's file-bearing input slots and follows them by name. This is the same traversal the absence-taint analysis does (`PipeSequence.analyze_taint`, `pipeline/controller_taint.py`), and it resolves sub-pipes through the hub in the same way.

- **Sequence.** Steps are visited in order. A slot that an earlier step's output overwrites stops being followed. A step's batch parameters map the list slot to its item slot for the sub-pipe.
- **Parallel.** Every branch is visited.
- **Batch.** The list slot maps to the item slot, and the branch pipe is visited.
- **Condition.** Every branch is visited, but whatever is found below a condition is conditional.
- **Liftable steps.** A step that the absence-taint analysis marks as liftable, because it may be skipped when an optional slot is absent, is conditional too.
- **Opaque pipes.** A `PipeFunc`, a `PipeCompose`, a search pipe or an unresolved cross-package reference consumes nothing as far as this walk knows, so the walk never guesses.
- **Consumers.** `PipeExtract` consumes its single input, and its readable formats come from the model its extract choice resolves to. `PipeLLM` consumes the documents its prompt references by variable path, and its readable formats are the resolved model's `supported_document_types`. A waterfall of models reads a format when any member reads it.

**The rule.** The check refuses only when a consumer is certain: reached with no conditional hop, and resolved to a model that does not read the file's known format. A consumer reached through a condition or a liftable step is left to D4's operator check, so a valid run is never refused ahead of time. All violations are collected and reported together, each naming the input path, the format received, the pipe, the model and the formats that model reads.

**What it costs.** The walk depends only on the library and the model deck, never on the input values, so its result is a per-slot table of consumers that could later be computed at validation time and published. That is the follow-up on the input-form descriptor below. At run setup it costs a walk over the pipe tree and one deck resolution per consumer.

**One deployment invariant.** The check resolves models with the deck of the process that runs the setup, which on the hosted plane is the runner and not the worker. The two must switch routing profiles together. If the runner still resolved the extract model to the relay while the worker had moved to manifold, a Word document that the worker would extract would be refused at `/start`. The manifold cutover item must carry this.

## Errors

- **`PipelineInputFormatError`** is a new caller-facing subclass of `PipelineInputContentError`, and so in the input domain, with a `CHANGE_INPUT` user action. It has two children:
  - `PipelineInputNotAnImageError` implements D3. Example: "Input `referral_letter` is an Image, but the file is a PDF document (`application/pdf`). Give an image file such as PNG, JPEG or WebP."
  - `PipelineInputFormatUnsupportedError` implements D5. Example: "Input `transcripts[0]` is a Word document (`.docx`). Pipe `extract_transcript` extracts it with `azure-document-intelligence`, which reads PDF and images. Give a PDF, or use an extract model that reads Word documents."

  Their messages carry only facts the caller supplied or the method declares, so they survive strict disclosure.
- **`ExtractInputFormatError`** is new, and `PromptImageFormatError` (existing) and `PromptDocumentFormatError` (new) join it at the operator level. All three are in the content category, and so in the input domain.
- Each new class gets its generated error page and identity entry (`make gep`, `make gei`), because consumers outside this repository branch on `error_type`.

## Deliberately left out

- **Converting Office files** (D1).
- **Identifying the format of an http(s) input before the run** (D2). The operator check covers it once the bytes are loaded, and a web-page model never needs it.
- **Per-subtype image support**, such as a WebP sent to an extractor that reads only JPEG and PNG. The `image` key is a family. Nothing observed needs finer declarations yet.
- **Consumers the walk treats as opaque.** A file that passes through a `PipeFunc` or a `PipeCompose` into another slot is not followed.
- **The relay.** It is not changed (L-260824-25253a).
- **Explaining a failed run to its user.** That is L-260923-a65976 in pipelex-mcp. This design makes these failures happen at `/start`, where the caller already receives the reason synchronously.

## Follow-ups in other repositories

- **pipelex-remote-config.** The manifold section's `[azure-document-intelligence]` declares `docx`, `pptx`, `xlsx` and `html` beside `pdf` and `image`, since manifold forwards them and Azure reads them. The gateway section keeps `pdf` and `image`, because that is true of the relay. Older runtimes ignore keys they do not know. The declaration takes effect when the hosted plane extracts through manifold.
- **The manifold cutover (L-260917-0ba8ed).** It carries D5's deployment invariant: the runner and the worker switch routing profiles in the same deploy.
- **The input-form descriptor (mthds standard, to be decided).** The descriptor could publish, per file input, the formats its certain consumers read. `mthds_prepare_inputs` could then refuse before uploading, and a form could set its file picker's `accept`. The descriptor's `DocumentItem` currently says "no accept-list". This is a change to the standard, owned by `mthds`, and it is only worth filing if this design is ratified.

## How the fix reaches the hosted plane

The branch changes only `pipelex`. The run-setup check runs inside `pipeline_run_setup`, so `pipelex-api` needs no code change, and its existing mapping answers the new input-domain errors with 422. After a `pipelex` release, `pipelex-server` moves its exact pin, re-locks, bumps the runner and the worker, and builds and deploys both. The acceptance on the dev plane replays the proof lab's two scenarios: the Word transcripts are refused at `/start` with the message above, and the PDF in the `Image` slot is refused at `/start` naming `referral_letter`.
