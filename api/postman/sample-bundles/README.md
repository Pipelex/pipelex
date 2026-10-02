# Postman sample bundles

The `.mthds` bodies behind the test requests in the **Pipelex FastAPI** Postman collection (the `Validate` and `Pipeline` folders). Keeping them here as files — rather than only embedded in Postman — makes them reviewable, diffable, and editable. The collection requests carry a copy of each body inline; if you edit a file here, re-push it with the `postman-bundle` skill (or by hand) to keep the request in sync.

Each verdict below was confirmed against a live `POST /v1/validate`.

## Valid

| File | `/validate` verdict | Notes |
|---|---|---|
| `hello_greeting.mthds` | valid · **runnable** | Trivial one-pipe `PipeLLM` (text → text). Cheap to actually run. |
| `cv_job_match.mthds` | valid · **runnable** | The workhorse used across the `Pipeline` examples (structured `MatchAnalysis` output). |
| `fashion_moodboard.mthds` | valid · **runnable** | Real demo bundle (search → LLM → image gen). Validates free; executing it is expensive. |
| `batch_candidate_screening.mthds` | valid · **runnable** | Real demo bundle (inline structures; PDF `Document` inputs needed to actually run). |
| `draft_with_signature.mthds` | valid · **NOT runnable** | One step is a forward-declared `PipeSignature` → `is_runnable:false`, `pending_signatures` lists it. Running it raises `PipeSignatureNotExecutableError`. |
| `invalid/missing_main_pipe.mthds` | valid (no `main_pipe`) | Kept here for reference: a bundle with **no `main_pipe` still validates** (`graph_spec:null`). It is *not* an invalid case. |

## Invalid — one distinct error type each

| File | `validation_errors[].error_type` / category | What it shows |
|---|---|---|
| `invalid/syntax_error.mthds` | TOML parse error | Malformed bundle text — fails before blueprint validation. |
| `invalid/missing_pipe_ref.mthds` | dependency pipe not found | A `PipeSequence` step references a pipe that is never defined. |
| `invalid/unknown_concept.mthds` | concept reference unresolved | A pipe `output` names a concept that is never declared and is not native. |
| `invalid/prompt_input_mismatch.mthds` | `missing_input_variable` (blueprint_validation) | The prompt uses `$city`, which is not a declared input. |
| `invalid/bad_pipe_type.mthds` | `union_tag_invalid` | `type = "PipeWizardry"` — not a real pipe type. |

## Inputs

`*.inputs.json` files hold the run inputs for the runnable bundles (`hello_greeting`, `cv_job_match`, `draft_with_signature`). `/validate` ignores inputs; they are used by the `Pipeline` (execute/start) requests.
