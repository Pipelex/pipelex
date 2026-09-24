---
status: draft
item: L-260924-577415
---

# Plan: refuse file inputs whose format their consumer cannot read, before the run

The design is [`design.md`](design.md), and its decisions are cited here as D1 to D5. One branch, `fix/File-input-formats`, closes L-260924-577415 and L-260924-600272. Tests come before the implementation in every phase. Run `make agent-check` after every code change. Run `make agent-test` at each checkpoint. Line references are to `a02b77ac7` (v0.63.0).

## Before starting

The design and this plan were written on 2026-09-24, and the work was parked until the following week, with nothing implemented. To resume, run `wt open --for L-260924-577415`, then `ledger claim L-260924-577415 --renew` and `ledger claim L-260924-600272 --renew` from inside the worktree. Then settle the following with Louis before Phase 1.

- **Ratification.** Once the design is approved, flip both documents from `draft` to `active` in the same change.
- **D5 scope.** Decide whether the pre-run consumer check (Phase 4) ships on this branch. It is the largest phase, and Checkpoint B is where the branch could open its pull request without it. The recommendation is to keep it, because "only after the run starts" is exactly what L-260924-577415 reports.
- **Follow-ups owed at ratification.**
  - Add a note on L-260917-0ba8ed carrying D5's deployment invariant: the runner and the worker switch routing profiles in the same deploy.
  - Decide whether to file the input-form accept-list against `mthds` (see the design's follow-ups).
- **Rebase first.** Rebase onto `dev` before Phase 1, and re-check the cited line numbers, which are to v0.63.0.

## Phase 1: the runtime knows each file input's format (D2)

- [ ] **Format keys.** Add the shared function that turns a MIME type into a format key in `pipelex/tools/misc/filetype_utils.py`: every `image/*` type gives `image`, any other identified type gives its extension, and none or `application/octet-stream` gives no key. Unit-test it over PDF, the Office Open XML types, the legacy Office types, image types, `text/html`, `text/markdown`, octet-stream and none.
- [ ] **Storage head read.** Add a concrete `load_head(uri, *, nb_bytes)` to `StorageProviderAbstract` (`pipelex/tools/storage/storage_provider_abstract.py`), which loads the whole object and slices it. Override it with a ranged read in `s3_storage_provider.py` and `gcp_storage_provider.py`. Test the default through the in-memory and local providers, and test the S3 and GCP overrides against mocked clients, asserting the range header they send.
- [ ] **Identification at setup.** Extend the walk in `pipelex/pipeline/input_normalizer.py` so it identifies every `ImageContent` and `DocumentContent` and stamps `mime_type`, carrying the input path for messages:
  - data URLs and local files reuse the bytes they already read;
  - `pipelex-storage://` URIs get a head read, run concurrently with a bound;
  - http(s) URIs are not fetched;
  - the sniffed type wins, and the declared type stands only when the sniff fails.

  Identification runs whether or not relocation is enabled, and is skipped for mock inputs. Rewire `prepare_pipe_job` (`pipelex/pipeline/execution_seams.py:286-288`) accordingly. Tests cover:
  - a storage `.docx` with no `mime_type`, which gets stamped;
  - `data:image/png;base64,<a PDF>`, which is corrected to `application/pdf`;
  - an unidentifiable `data:` text URL, which keeps its declared type, where today it raises `FileTypeError`;
  - an http(s) URL, which is untouched and never fetched;
  - list items and nested structure fields;
  - relocation disabled, where identification still runs.
- [ ] **Images keep their type into the prompt.** Pass the image's `mime_type` into `PromptImageFactory.make_prompt_image` (`pipelex/kernel/llm_prompt_content.py:232`), the way documents already get theirs.

## Phase 2: an `Image` holds an image (D3)

- [ ] **The error family.** Add `PipelineInputFormatError`, a caller-facing subclass of `PipelineInputContentError`, and its child `PipelineInputNotAnImageError`, in `pipelex/pipeline/exceptions.py`. Both carry a `CHANGE_INPUT` user action. Test that the message survives strict disclosure (`to_dict(STRICT)`).
- [ ] **The setup check.** During the Phase 1 walk, refuse an `ImageContent` whose identified format key is not `image`. Tests cover:
  - a PDF given to an `Image` input, refused and naming the input;
  - a concept refining `Image`;
  - a PDF as the third item of an image list, named `photos[2]`;
  - an image nested in a structure;
  - an unidentifiable image such as an SVG, which is not refused.
- [ ] **The mid-run line.** In `_check_vision_support` (`pipelex/cogt/llm/llm_worker_abstract.py:419-429`), raise `PromptImageFormatError` for a prompt image whose known format key is not `image`. Test it with an image produced mid-run whose bytes are a PDF.
- [ ] **The API answer.** Through `pipeline_run_setup`, a PDF in an `Image` input is refused before any pipe runs, with the input domain and HTTP 422 from `error_domain_to_http_status`.

### Checkpoint A

Record here the phases completed, the decisions taken on the way, the open questions, and the state of the code, so that a fresh session can pick the work up.

- [ ] `make agent-check`
- [ ] `make agent-test`
- [ ] `/rev`

## Phase 3: consumers check the format against what their model reads (D4)

- [ ] **Model spec vocabulary.** In `pipelex/cogt/model_backends/model_spec.py`, add a readable-formats property for extractors, the intersection of `inputs` with `pdf`, `docx`, `pptx`, `xlsx`, `html` and `image`. Extend `supported_document_types` with `xlsx` and `html`. Unit-test both.
- [ ] **ExtractInput carries the format.** Add `mime_type` and the source input's name to `ExtractInput` (`pipelex/cogt/extract/extract_input.py`), and fill them in `PipeExtract._live_run_operator_pipe` (`pipelex/pipe_operators/extract/pipe_extract.py:122-141`) from the stuff's content.
- [ ] **The extract check.** Add `ExtractInputFormatError`, in the content category, in `pipelex/cogt/exceptions.py`. In `ExtractWorkerAbstract._check_can_perform_job` (`pipelex/cogt/extract/extract_worker_abstract.py:53-67`), refuse a known format key that the model does not read. Skip the check for a web-page model given an http(s) URL. Tests cover:
  - a `.docx` given to a model reading `pdf` and `image`, refused with a message naming the input, the model and the readable formats;
  - the same file given to a model declaring `docx`, which passes;
  - an unknown format, which passes;
  - a web-page model given a URL, which passes;
  - the error domain, which is input.
- [ ] **The LLM document check.** Add `PromptDocumentFormatError`, in the content category. In `_check_document_support` (`llm_worker_abstract.py:431-448`), raise it for a known format the model does not read, and keep `LLMCapabilityError` for a model that reads no documents at all. Update the existing tests that assert `LLMCapabilityError` for the format case.
- [ ] **Local declarations.** Prove that docling extracts a `.docx`, a `.pptx`, a `.xlsx` and an `.html` file with an integration test. Only then declare `docx`, `pptx`, `xlsx` and `html` on `docling-extract-text`, in both `.pipelex/inference/backends/internal.toml` and `pipelex/kit/configs/inference/backends/internal.toml` (`make check-config-sync`). Leave `pypdfium2-extract-pdf` and Mistral OCR as they are.
- [ ] **Existing fixtures.** `tests/cases/documents.py` puts `CV-ELIAS-THORNE.docx` in `DOCUMENT_FILE_PATHS`, and `tests/integration/pipelex/cogt/test_extract.py` runs every document on every extractor that reads PDF. Split the cases by format so that a model not declaring `docx` expects `ExtractInputFormatError` and a model declaring it expects pages.

### Checkpoint B

Record here the phases completed, the decisions taken on the way, the open questions, and the state of the code, so that a fresh session can pick the work up.

- [ ] `make agent-check`
- [ ] `make agent-test`
- [ ] `/rev`

## Phase 4: the pre-run consumer check (D5)

- [ ] **The walk.** Write `pipelex/pipeline/file_input_consumers.py`. From an entry pipe it returns, for each file-bearing input slot, the consumers it reaches, each with the pipe, the resolved model, the formats that model reads, and whether the consumer is certain or conditional. Follow the traversal of `PipeSequence.analyze_taint` (`pipelex/pipe_controllers/sequence/pipe_sequence.py:176-298`), and reuse its liftable-step verdicts instead of re-deriving them. Tests, one per rule:
  - a sequence step consuming the input;
  - a slot overwritten before the consumer, which is not followed;
  - a batch step mapping `transcripts` to `transcript`;
  - a standalone `PipeBatch`;
  - parallel branches;
  - a condition branch, which is conditional;
  - a liftable step, which is conditional;
  - a nested sequence;
  - `PipeFunc` and `PipeCompose`, which are opaque;
  - an unresolved cross-package reference, which is opaque;
  - a `PipeLLM` document reference by dotted path;
  - a waterfall where one member reads the format and another does not.
- [ ] **The check.** Add `PipelineInputFormatUnsupportedError` to the Phase 2 family. In `prepare_pipe_job`, after identification, intersect each input's format key with its certain consumers and raise one error listing every violation. Test the first proof-lab scenario end to end through `pipeline_run_setup`: three `.docx` transcripts batched into a `PipeExtract` on a model reading `pdf` and `image` are refused before any pipe runs, and each transcript is named. Test too that a consumer behind a condition lets the run start, and that it then fails in the operator with `ExtractInputFormatError`.
- [ ] **Local reproduction.** Run a method with a `.docx` into a PDF-only extract model through `.venv/bin/pipelex run`, and record the error it prints in this plan.

## Phase 5: documentation, error pages, changelog

- [ ] **Concept docs.** In `docs/building-methods/concepts/native-concepts.md`, say that `Document` carries PDF, Office and web-page content, that which formats work depends on the consuming model, that an `Image` must hold an image file, and that both are checked before the run.
- [ ] **Extraction docs.** In `docs/features/document-extraction.md`, add the formats each extractor reads, and say that a format the model does not read is refused before the run.
- [ ] **Model spec docs.** Document the `inputs` format keys where the backend TOML format is documented, under `docs/configuration/`.
- [ ] **Error pages.** Run `make gep` and `make gei` for the new error classes, and review the generated diffs.
- [ ] **Changelog.** Add one condensed entry under `[Unreleased]`: runs whose file inputs cannot be read by their consumers are refused at start with an input error, and the LLM document-format refusal moves from a configuration error to an input error, which is a breaking change of `error_type` for that case.

### Checkpoint C: pre-PR

- [ ] `make agent-check`
- [ ] `make agent-test`
- [ ] `make test-ts-gates` only if `pipelex/codegen/emitters/` was touched, which is not planned.
- [ ] `/rev`
- [ ] Open the pull request `fix/File-input-formats · L-260924-577415 — docx extract fails mid-run`, against `dev`, with `Closes L-260924-577415` and `Closes L-260924-600272` in its body.

## Delivery, outside this branch

- **Release.** The `pipelex` release, through the release play.
- **pipelex-server.** Move the exact `pipelex` pin in `pipelex-server`, re-lock, bump the runner and the worker, run `make deploy-plan`, then build and deploy to dev.
- **Acceptance on dev.** Replay both proof-lab scenarios. The Word transcripts must answer 422 at `/start`, naming each transcript and PDF as the format that works. The PDF in `referral_letter` must answer 422 at `/start`, naming the input.
- **Follow-ups.** The remote-config declaration for manifold and the cutover invariant, as listed in the design.
