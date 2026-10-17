---
title: "Error Model"
description: "How Pipelex classifies, carries, and reports errors — the ErrorReport schema, inference error categories, error domains, the layer model, worker classification, and how classification survives a distributed worker boundary."
---

# Error Model

In Pipelex, an error is **data**, not a control-flow accident. Every failure is classified once — at the layer that knows the most about it — and that classification travels intact to every consumer: the human reading a Rich panel, the agent parsing JSON, a distributed worker's retry engine, and the HTTP adapter picking a status code.

This page covers the contract that makes that possible: the `ErrorReport` schema, the classification enums, how inference workers classify SDK exceptions, how classification survives every wrapping layer, and how it survives serialization across a distributed worker boundary.

---

## Design Principle

Three rules hold across the codebase, and everything else builds on them.

**Single-rooted hierarchy.** Every custom exception inherits from `PipelexError` (`pipelex/base_exceptions.py`). There is one root, so one `to_error_report()` contract covers the whole tree.

**Classify at the source, never lose it.** The layer that catches a third-party exception knows the most about it. It classifies there. Every layer above is a *wrapper* — it adds context (pipe code, stack) but inherits the classification rather than re-deriving or discarding it.

**No broad catches in business logic.** `except Exception` is allowed only at CLI entry points and async task roots. Ruff rule `BLE001` enforces this — an unexpected exception crashes loudly instead of being silently swallowed.

!!! info "Why classify, instead of just propagating the exception?"
    A raw `openai.RateLimitError` tells a Python `except` clause what to catch, but it does not tell a distributed worker's retry engine whether to retry, the HTTP adapter which status to emit, or an agent whether the failure is the user's fault. Classification turns an exception into a decision input that every consumer can act on uniformly.

---

## The Layer Model

An error rises through a series of layers. Each layer has exactly one job.

| Layer | Role | What it does with errors |
|-------|------|--------------------------|
| **5 — CLI entry points** | `pipelex` / `pipelex-agent` commands | Catch, format for human (Rich) / agent (JSON·MD) / HTTP |
| **4 — CLI factories** | `cli_factory.py`, `agent_cli_factory.py` | Catch setup errors, route to handlers |
| **3 — Pipeline runner** | `PipelexMTHDSProtocol.execute()` | Catch + wrap as `PipelineExecutionError`, which reports the located root fault |
| **2 — Pipe router / operators** | `PipeRouter`, pipe operators | Catch + locate every failure as a `PipeRouterError` (`pipe_code`, `pipe_stack`); a foreign exception first becomes a `PipelexUnexpectedError` |
| **1 — Workers / SDK calls** | `pipelex/providers/*/` | **Catch the SDK exception → classify → raise `CogtError`** |
| **0 — Third-party SDKs** | OpenAI, Anthropic, Google, … | Raise raw, untyped provider exceptions |

Classification happens once, at **Layer 1**. Layers 2–5 are wrappers: they attach context as they catch and re-raise, but the registry code chosen at Layer 1, and the `error_category`, `model` and `provider` beside it, reach Layer 5 unchanged (see [Cause-Chain Enrichment](#cause-chain-enrichment)). The worker's classification picks the code, and the code decides the domain, the retry verdict and the HTTP status, so a single Layer-1 decision settles all three.

---

## ErrorReport — the Serialization Schema

`ErrorReport` (`pipelex/base_exceptions.py`) is the single source of truth for error serialization. It is a frozen Pydantic model with `extra="forbid"`.

| Field | Type | Meaning |
|-------|------|---------|
| `code` | `str` | The registry code the error resolved to, a core code of the MTHDS standard or a Pipelex code: see [Error codes](#error-codes-and-the-pipelex-error-registry) |
| `error_type` | `str` | The exception class name |
| `message` | `str` | Human-readable message |
| `title` | `str` | The code's title — the RFC 7807 `title`, the same for every occurrence of the code |
| `type_uri` | `str` | The code's documentation page — the RFC 7807 `type`: `https://mthds.ai/errors/<code>` for a core code, `https://docs.pipelex.com/errors/<code>` for a Pipelex code |
| `error_category` | `str \| None` | `InferenceErrorCategory` value (inference errors only), the runtime's own classification that picked the code |
| `error_domain` | `str \| None` | `ErrorDomain` value — `input` / `config` / `runtime`, read from the domain the registry gives the code (see [ErrorDomain](#errordomain)) |
| `retryable` | `bool \| None` | Whether repeating the operation can succeed: `true` only when the code's retry verdict is `yes`, `false` for `no` and for `outcome_unknown` |
| `user_action` | `UserAction \| None` | Typed advice — `kind` + free-form `detail` |
| `model` | `str \| None` | Model handle, when the failure is attributable to one |
| `provider` | `str \| None` | Backend name, when attributable |
| `provider_metadata` | `ProviderErrorMetadata \| None` | SDK metadata — status code, request id, `retry_after` |
| `validation_errors` | `list[ValidationErrorItem] \| None` | Structured per-error diagnostics on a bundle-validation failure (`ValidateBundleError` only) |

`PipelexError.to_error_report()` is the entry point. `to_dict()` serializes, dropping `None` fields; `from_dict()` is its strict inverse.

### The identity, and why renaming an error class or changing its code is a wire break

`code` and `error_type` are the two identity fields on every report. `title` and `type_uri` follow from the code, so no class declares them.

`error_type` is `type(self).__name__`, the Python class name with no indirection, and consumers outside this repo `switch` on that string until the problem document moves the class name to the operator's diagnostics. Renaming an error class therefore breaks them *silently*: their build stays green and the branch simply stops matching, falling through to a generic error path. Changing the code a class declares breaks them the same way, and changes what every reader is told to do.

The guard against both is a committed snapshot of every class's name and code declaration at `tests/data/errors/error_identity.txt`, regenerated with `make generate-error-identity` (alias `make gei`) and gated by `tests/unit/pipelex/errors/test_error_identity_snapshot.py`. A rename or a change of code cannot land without producing a reviewable diff on that file at the moment it is made — which is also the moment to plan the matching consumer updates. The same command rewrites the static redirects of the retired per-class error pages, described below.

### Error codes and the Pipelex error registry

The MTHDS standard names every error a runner or a client can meet with a code, `input.missing` or `model.unavailable`, and publishes them as its core error registry: one entry per code, declaring its title, the domain whose actor must act, its retry verdict, its steps, its typed parameters and its HTTP status. A problem's `type` is the code's page, `https://mthds.ai/errors/<code>` for a core code. What the standard leaves to implementations, billing, organizations, the hosted catalog, Pipelex's storage, its configuration and plugins and the components it ships, Pipelex names with codes of its own under the `pipelex` extension prefix, which the core registry registers to Pipelex: `pipelex.billing.credit_exhausted`, `pipelex.config.variable_missing`.

The Pipelex codes are authored in one public file, `pipelex/errors/registry/pipelex-error-registry.yaml`, in the standard's registry format. Everything else is generated from it with `make generate-error-registry` (alias `make ger`): the JSON snapshot `pipelex-error-registry.json` beside it, which the package ships, every release publishes as an asset, and `load_pipelex_error_registry()` (`pipelex/errors/registry/registry_document.py`) reads; the typed Python of the codes, `pipelex/errors/registry/pipelex_codes.py`, with a `PipelexErrorCode` member and a closed parameters model per code; and one page per code under `docs/errors/`, which is where a Pipelex code's type URI, `https://docs.pipelex.com/errors/<code>`, leads. [The Error Registry](../contribute/error-registry.md) describes the format's checks and the workflow.

#### Every error declares its code

Every `PipelexError` subclass declares, in its own class body, the code it raises (`pipelex/errors/error_code_declaration.py`):

- **A code**, a `CoreCode` from the `mthds` package or a `PipelexErrorCode`: every instance raises it.
- **A set**, `ErrorCodeSet(default=..., others=(...))`: the raise site that knows which applies chooses it with `with_error_code(code)`, and an instance whose raise site chose none carries the default. Two cases that need different verdicts are two codes, so a class whose raise sites need different readings declares a set, never a domain or a verdict of its own.
- **Its cause's code**, `InheritsCause(fallback=..., others=(...))`: a wrapper that adds no fact deciding the code takes its cause's, and carries its fallback when no error below it carries one. A raise site that knows the code itself may still choose the fallback or one of the `others`.
- **An abstract base**, `ABSTRACT_ERROR`: a class never raised directly.

```python
class PipeRunInputsError(PipeRunError):
    error_code = ErrorCodeSet(default=CoreCode.PIPE_INPUT_UNRESOLVED, others=(CoreCode.INPUT_MISSING,))


raise PipeRunInputsError(msg).with_error_code(CoreCode.INPUT_MISSING)
```

`PipelexError.resolve_error_code()` walks the `__cause__` chain: it stops at the first error that carries a code by itself, the code its raise site chose or its class's, descends through every error that takes its cause's code, and stops at a cause that is not a Pipelex error. When no error on the way carries one, the error reports the code the deepest error implies (`implied_error_code`, which an inference error built with a category alone names, see below), else the fallback of the deepest wrapper, and `runtime.unexpected`, whose step is `report`, when none names one. It is one walk, guarded against a cyclic chain, and no error's code starts a walk of its own. So a wrapper that adds the fact deciding the code keeps its own over a coded cause, as `pipe.function_raised` does over any coded error raised inside the method's function (the in-process executor raises what the function raised as `PipeFuncRaisedError`, so a failure of the executor itself keeps its own code; an out-of-process executor must mark the function's failure the same way, with a Pipelex error carrying `pipe.function_raised`, since an exception that is not a Pipelex error, such as a transport failure, proves nothing about the function and reads `runtime.unexpected`), and a wrapper that adds nothing passes its cause's code through.

`ErrorReport.make_for_code()` builds every report from its code: the title, the documentation page, the domain and the retry verdict are the code's, read from the registries' generated tables (`pipelex/errors/error_codes.py`), so classifying an error is a pure lookup with no file read, safe inside a Temporal workflow's sandbox.

Four checks keep the declarations honest, in `tests/unit/pipelex/errors/test_error_code_gate.py`: every subclass declares a code in its own body, every declared code is registered, no subclass declares what its code decides (`error_domain`, `retryable`, a title or a type URI), and no raise constructs an abstract base. A fifth reads every `SomeError(...).with_error_code(Enum.MEMBER)` chain in the package and the runner, and fails on a code the class does not declare. A closed plugin declares at boot the public codes its errors raise, and a code neither registry holds refuses the boot.

#### Raises outside the root

An exception class outside the root carries no code, so a reader that meets one gets nothing better than the catch-all. Our own code therefore raises coded classes wherever a reader can see the raise, and `tests/unit/pipelex/errors/test_foreign_raises.py` catches a new foreign raise: `pipelex/errors/foreign_raises.py` reads every module of the package and the runner and allows by their shape the raises that are right (a builtin inside a pydantic validator, `NotImplementedError` in an abstract method, the data-model dunders Python and Jinja read, the framework carriers a library expects by type, and developer tooling), and every other foreign raise must be listed with its disposition in `tests/data/errors/foreign_raises.txt`: an invariant raised only on a bug of ours, which a boundary reports as `runtime.unexpected`, a builtin in a helper only validators call, a private class caught where it is defined, a carrier the scan cannot tell by its name (the import system's `ImportError`, the standard's method tree refusal its callers translate), developer tooling outside the exempt directories, or a builtin of a module that must import nothing of Pipelex and that its every caller catches. The check fails on an unlisted foreign raise and on a listed one that is gone.

#### The retired per-class pages

Before every error carried a code, each class had a page at `errors/<kebab-class-name>/`, which its class-derived type URI named. Those pages are retired. `mkdocs.yml`'s `redirect_maps` holds a static redirect for each, generated by `make generate-error-identity` (`pipelex/errors/retired_error_pages.py`), so a client following an old type URI, a non-browser one included, lands on the page of the class's code: the default of a set, the fallback of a class that takes its cause's code, or the error codes' index for a class that is abstract or gone. The site's `404.html` still sends any other single-segment error path to the index.

### `validation_errors` — structured bundle-validation diagnostics

A bundle-validation failure (`ValidateBundleError`) aggregates per-error data across stages and projects it onto `validation_errors` as a list of typed `ValidationErrorItem`s, so the structured error report an HTTP API surfaces carries machine-mappable diagnostics (not just a single `detail` string). Each item's `category` is one of the **closed** `ValidationErrorCategory` set:

- `blueprint_validation` — interpreter / blueprint-validation faults. A blueprint-stage `PipeValidationError` raised *inside* a pydantic model validator (e.g. the PipeBatch `input_item_name` == `input_list_name` collision, or the SubPipe `batch_over` == `batch_as` collision — both `batch_item_name_collision`) is wrapped by pydantic as a `value_error`; the blueprint categorizer unwraps it (`ctx["error"]`) so the item keeps its structured `error_type` and `pipe_code` / `domain_code` locators. The item stays in `blueprint_validation` (not `pipe_validation`) because the fault genuinely surfaced at the parse boundary, before any pipe was instantiated — only the `error_type` is recovered, not the stage. This category also serves as the **last-resort residual**: a parse-level failure (an empty blueprint, a bundle-elaborator failure) is raised with only a message and no categorized data, so when *nothing else* produced an item the builder projects that message as one `blueprint_validation` item (no `error_type`, no `source` — the bundle could not become a blueprint at all). A TOML syntax error is its own item of this category, with no `error_type`, carrying the `source` and the 1-based `line` and `column` the parser stopped at.
- `pipe_factory` — pipe-factory failures (e.g. a missing concept).
- `pipe_validation` — pipe/concept validation (missing input variable, type mismatch).
- `dry_run` — one item per pipe whose dry run failed, with the `error_type` `DryRunError`, the pipe's bare `pipe_code`, its `domain_code` and, when the library knows it, its `source`.

**Every error is an item, and none hides another.** Every pydantic error the parser meets becomes its own item: categorized when the blueprint categorizer knows it, and otherwise an uncategorized `blueprint_validation` item with no `error_type`, carrying its `source`, the `pipe_code` its location names and its `field_path`, the bundle-root path of the failing field with pydantic's own elements left out (`pipe.summarize.promtp`, not `pipe.summarize.PipeLLM.promtp`). A misspelled field beside an undeclared prompt variable therefore gives two items, where the typo used to vanish until the variable was fixed. The only error left out is the union-branch noise of a concept declared as `ConceptBlueprint | str`, whose table branch already reports the fault. The same holds inside every message `format_pydantic_validation_error` builds: the kinds it lists get their own heading, and every other kind is rendered under "Other validation errors", whatever else is present.

**A dry-run failure is one located item per failing pipe.** The dry-run sweep (`BundleValidator` in `pipelex/pipeline/bundle_validator.py`) runs each pipe through its own in-process router, which notes the first pipe each failure leaves: the innermost pipe that failed. A controller that failed because a pipe it runs failed is therefore reported at that pipe, and once, even when both were swept; validating the controller alone still reports the inner pipe. A pipe listed in `allowed_to_fail_pipes` is never where a failure is reported: a failure met there is reported at the innermost pipe around it that is not allowed to fail, the one whose failure is unexpected. When the bundle is validated from submitted content beside a host's library directories, as the hosted validator does, the item carries that pipe's `source` only when the pipe belongs to that content: a pipe loaded from the host's own library directories is named by its code and domain, never by its file on the host. A bundle validated from a file on the caller's own disk names every pipe's file, a sibling file of the same method included, and so does submitted content validated beside directories that are the caller's own (`library_dirs_are_callers`). The sweep raises one `DryRunError` whose `failures` hold one `DryRunFailureErrorData` per failing pipe, and the cascade turns each into its own `dry_run` item. The item's message names the pipe and carries the failure's own text only when the failure's root fault, the one a run failure reports (the innermost `PipelexError` on its cause chain, the walk stopping at the first exception that is not one, and of two errors of the same class the outer one, which restates the inner with a remedy), authored that text as caller-facing copy, and otherwise the fault's title, because the verdict is kept verbatim under STRICT disclosure and would otherwise carry a configuration or storage failure's internals to a hosted caller. A failure the runtime has not classified as the caller's therefore reads `Pipe '<code>' failed its dry run: <title>`, the fault's title in place of its message. The sweep reports every failing pipe this way, whatever raised the failure.

The **structured-info invariant is total**: every invalid verdict carries a non-empty `validation_errors[]`, never a bare message. The builder emits the categorized items and the `dry_run` items, then the `blueprint_validation` fallback only when nothing else produced an item.

Besides `category` and `message`, each item carries whatever identity fields its stage produced — `error_type`, `pipe_code`, `concept_code`, `domain_code`, `field_path`, `field_name`, `variable_names`, `missing_concept_code`, `declared_concepts` (on an `unresolved_concept` item, the bare codes of the concepts the validated bundle declares in the domain the reference was looked up in, native concepts excluded, and never those a library loaded before it, which may be a host's own), the TOML position `line` and `column`, the unknown-model locators `model_reference`, `model_type` and `suggestions`, the template-check locators `template_file` and `template_location` (on a `template_check_warning`, which rides `warnings`), and a `source` (the declaring file path, or the per-content source the in-memory load path was given) that hands a consumer the owning file for cross-file diagnostic placement. When the error has a deterministic remedy, the item also carries a [`suggested_fix`](#suggested_fix-structured-deterministic-fixes).

**A verdict names no path on the host.** An item and the verdict's message are kept verbatim under STRICT disclosure, so neither names where the host keeps a file. A bundle of a package the method depends on by address is named by the package's address and the bundle's path inside the package, such as `github.com/acme/harbour-methods/tides/notices/tide_notices.mthds`, never by the directory the host installed the package in: that is the `source` of an item located inside the dependency and the file a duplicate declaration inside it names, on every surface, a local one included. When submitted content is validated or run, the library directories loaded beside it are the host's (installed libraries, the defaults, `PIPELEXPATH`) unless the caller says they are its own, so the verdict names none of their files: an item located in one carries no `source`, nor a `field_path` naming it, and is found by its `pipe_code` and `domain_code`, a warning found at a pipe of theirs carries no `template_file` (the sweep withholds it, `BundleValidator`'s `source_pipe_refs`), and a message that named one, named the template file a `PipeDocGen` step of theirs names (one whose template the engine's check refuses in the dry run of a caller's pipe that runs it), or named the module a Python file of theirs was imported as (two `@pipe_func` functions of the same name, for instance), reads `<host library file>` in its place (`withholding_host_library_files` in `pipelex/pipeline/validate_bundle_translation.py`). A name only counts standing on its own, never inside a longer one, and neither a source the caller submitted nor a template file its own content names is ever withheld. A method of those directories that refuses to load is not an item at all: it is the deployment's configuration failing to validate, so `reporting_host_library_faults` in the same module raises it as a `HostLibraryLoadRefusalError`, carrying `pipelex.config.invalid`, which an API answers with a 500 and whose message, the host library's own text, STRICT disclosure withholds. A step can only name its template file relative to its bundle, so no message about one names a path on the host. A bundle validated from a file on the caller's own disk, and content validated or run against library directories that are the caller's (`library_dirs_are_callers`, an option of `validate_bundle`, of the in-process validator and of the local runtime `PipelexMTHDSProtocol`, whose `validate` and `execute` both read it), keep the full path of every file, since there the directories are the caller's own. `pipelex fix bundle --diff` leaves a dependency's address-named source as it is.

**Every refusal of the bundle is a verdict.** A validator answers either a verdict — valid, or invalid with located items — or *no verdict could be produced*, which is reserved for a failure of the tool or its environment. So a refusal raised while loading or validating a bundle becomes an item, never a no-verdict fault. After its class-specific arms, the shared cascade (`translate_to_validate_bundle_error` in `pipelex/pipeline/validate_bundle_translation.py`) turns any other `PipelexError` whose code is the caller's to fix, in the `input` or the `method` domain, which a report reads as `input`, into a verdict with one item: `pipe_validation`, with the `pipe_code`, `domain_code` and `source`, when the library load located it on the pipe it was building, and `blueprint_validation` otherwise. That item carries no `error_type`, since a refusal with a closed code has an arm of its own. It keeps the refusal's message only when the refusal authored that message as caller-facing copy, and otherwise names the refusal's title, because the verdict as a whole is kept verbatim under STRICT disclosure. The location comes from the load loop in `LibraryManager.load_from_crate`, the one place that holds a pipe's code, domain and file when building it fails: it raises such a refusal again as a `PipeLoadRefusalError` naming the pipe and the file, `from` the original. A fault whose code an operator or the runtime must fix, a `LibraryError` among them (a library invariant of ours reads `runtime.unexpected`), a `SecurityError`, a `PipeNotFoundError` (which has its own not-found handler) and anything that is not a `PipelexError` still propagate as no verdict, and so does a missing document engine, `pipelex.docgen.engine_unavailable`, which the deployment has to install. The rule therefore reaches exactly the refusals whose code is the caller's. The pipe factories' refusals are: `PipeLLMFactoryError`, `PipeComposeFactoryError`, `PipeExtractFactoryError`, `PipeConditionFactoryError` and `PipeParallelFactoryError` are raised only while a pipe is built, about its own blueprint, so each declares a `method` code, `method.template_invalid` or `method.schema_violation`, and is caller-facing, and a `PipeExtract` whose input is neither an image nor a document validates to one item on that pipe, saying which input to redeclare. `PipeImgGenFactoryError` is not among them: it is raised while an image-generation pipe runs, not while it is built.

**The unknown model is the worked example.** A pipe whose model field names a handle, an alias, a preset or a waterfall the model deck does not define is refused when the pipe is built: the operator's deck check raises `ModelChoiceNotFoundError`, and the operator raises it again as a `PipeOperatorModelChoiceError` located on the pipe and on the field, to which the load adds the file. Every pipe type that names a model (`PipeLLM`, `PipeStructure`, `PipeImgGen`, `PipeExtract`, `PipeSearch`) does this through the same `PipeOperator.locating_model_choice` wrapper, so each gives the same item: `category: pipe_validation`, `error_type: unknown_model`, the `pipe_code`, `domain_code` and `source`, the `field_name` and a `field_path` of `pipe.<code>.model` (`pipe.<code>.model_to_structure` for a `PipeLLM`'s structuring model), the `model_reference` exactly as written, the `model_type` (`llm`, `text_extractor`, `img_gen` or `search`), and the deck's `suggestions` of the same kind, each spelled as a reference the field accepts. The suggestions stay in the item's `message` too, for consumers that keep only the message. When the deck offers exactly one suggestion, the item carries an `unsafe` `rename-model` fix, a `remap_value` of the field from the reference as written to that suggestion. It is unsafe because the suggestion is a fuzzy match over the deck's names, which can be a different model altogether, so `pipelex fix bundle` never applies it on its own; an author or an agent applies it deliberately. An inline setting table (`model = { model = "…", temperature = 0.2 }`) is not looked up in the deck, so it is not refused here. A default the deck names itself, which a `PipeJudge` naming no model resolves as its method loads, is not the method's: the wrapper lets its `ModelDeckChoiceUnresolvedError` through unchanged, the deployment's fault and no verdict item. On a run the same refusal stops the bundle before any pipe runs, as the same `unknown_model` item (see the next paragraph).

**A run refuses an invalid bundle with the same verdict.** A run loads its bundle before any pipe runs, and the run path's `acquire_library` performs that load inside the same `translate_to_validate_bundle_error`, so a bundle the load refuses raises the `ValidateBundleError` with exactly the items validating it gives, before any inference is spent. `ValidateBundleError` carries `method.invalid` and is caller-facing, so a hosted run route answers it as a 422 whose `validation_errors` STRICT disclosure keeps, where each refusal used to reach the host in its raw class: a misspelled concept as a `ConceptLibraryError` answered 500, a wiring mismatch as a `PipeValidationError` answered by the catch-all 500, a TOML fault as a 422 with no items, and a check firing inside a pipe's pydantic validator as a `runtime` `PipeExecutionError` reading "Input validation failed". The translation's own exceptions hold on this path too: an unknown entry pipe still raises its `PipeNotFoundError`, and a fault of the tool or its environment still propagates as itself. Two things differ from the validate path, both about whose files are loaded. The run path threads no source of its own onto its contents, so their items carry no `source`, even on a local run of a bundle file. A package the bundle depends on by address is loaded from the host's install directory within the same translation, as it is on the in-memory validate path, and a refusal inside it names the package by its address, never that directory. And the library directories load translated only when they are the caller's own, as on a local CLI run (`library_dirs_are_callers`); a host's directories (installed libraries, a temporary directory of shipped Python) load untranslated, because a fault there is not the caller's to fix: a refusal there is the `HostLibraryLoadRefusalError` described above, `pipelex.config.invalid`. The local `pipelex run` renders the verdict with the grouped panel `pipelex validate` prints, and `pipelex-agent run` copies its `validation_errors` into the error envelope.

**Signatures are never an error.** An unimplemented `PipeSignature` reached during validation is a *runnability fact*, not a validation failure: the validator no longer raises on it. The assembled library's outstanding signatures ride the validation report's `pending_signatures`, and `is_runnable = not pending_signatures`. `allow_signatures` is a sweep-mechanics flag only (whether signature pipes are mock-run and listed in `validated_pipes`) — it does not change the verdict, so strict ≡ lenient in the report body. The "is this a failure?" decision moves to the consumer: the CLI exits non-zero on `not is_runnable` unless `--allow-signatures`; the HTTP caller reads `is_runnable`. (The **execute/run** path is different: running a stub still raises `PipeSignatureNotExecutableError`.)

**Host-wiring guards are programmer errors, not content verdicts.** `validate_bundle`'s "provide exactly one of `mthds_contents` / `mthds_file_path`" guard and `resolve_crate_from_contents`'s `mthds_sources`-length-mismatch guard raise `PipelexUnexpectedError` (→ 500, redacted under STRICT), not `ValidateBundleError` — a caller wiring bug must not be reported as if the submitted bundle were invalid. The empty-`mthds_contents` guard stays caller-facing (it can legitimately reflect an end user submitting no bundles).

`ValidationErrorItem` and the builder are the single source of truth across surfaces: `build_validation_error_items()` (`pipelex/pipeline/validation_errors.py`) is reached through `ValidateBundleError.validation_error_items()`, which `ValidateBundleError.to_error_report()` (the API path), the agent CLI's `extract_validation_errors()` (the CLI JSON envelope) and `pipelex fix` all call, so the structured shapes cannot drift. `pipelex-agent validate pipe` and `validate --all` dry-run through the same cascade, so a failing dry run there is the same invalid verdict with the same items as on `validate bundle`. The item lives in `pipelex/base_exceptions.py` alongside `ErrorReport` — not next to the source error-data models — because `ErrorReport` references it as a typed field and the root exceptions module must not import the `pipelex.core` error modules.

#### The `error_type` registry — the closed vocabulary of faults

An item's `error_type` names the fault it reports, and that vocabulary is closed: `pipelex/validation_error_types.py` holds it in full, enumerated as `VALIDATION_ERROR_TYPES`. A consumer that needs to know which faults the language surface can report — a coverage gate, a test corpus, a client mapping errors onto its own UI — reads that registry instead of collecting strings from whichever diagnostics it happens to have seen.

The registry is the union of the enums validation already reports through, never a second list beside them — "reports through", not "raises", because the advisory members ride `warnings` and are never raised as an exception at all: `PipeValidationErrorType` and `PipeFactoryErrorType` are the two stage vocabularies, `ValidationResidualErrorType` names the one residual channel with no stage enum of its own, `HintLintErrorType` carries the intent-hint lints (which attach to concepts and structure fields too, so the pipe enum is the wrong home for them), and `TemplateCheckErrorType` carries the warnings a `PipeDocGen` step's template check finds during the dry run (the engine reads the template file and reports in its own words, which is not the pipe's validation). A member added to any of them is in the registry the moment it is declared. `ValidationErrorItem.error_type` is typed against their union, so an unregistered string cannot be constructed or parsed onto an item — which is what makes the enumeration *closed* rather than merely documented, and what publishes the vocabulary into the OpenAPI schema `pipelex-api` serves for `/validate`.

Two spellings live in that one vocabulary, deliberately. The stage enums are snake_case codes (`missing_input_variable`); the dry-run items' code is `DryRunError`, the name of the exception that produced them, because a dry-run failure is raised as an error object rather than classified into a code. Normalizing it would be a wire break across every consumer that pins the string, and it would buy nothing — the enumeration is closed either way.

Membership means a value is *reachable on the wire*, not that it is a useful thing to exercise. Several members are advisory-only — `optional_force_redundant`, `input_presence_vacuous`, the three `hint_*` lints and `template_check_warning` — riding `warnings` and never an invalid verdict, and the two `unknown_*` fallbacks fire on states no author can ask for. A consumer building coverage over the registry excludes those on its own side with a stated reason, rather than pruning them from the runtime truth here — which is what the [MTHDS Test Corpus](../contribute/mthds-test-corpus.md) vocabulary generator already does, excluding each with its reason as it generates the `error.*` namespace from this registry.

`validation_errors` is one of the fields kept under STRICT disclosure (it is in `_STRICT_KEPT_FIELDS`): the items describe the caller's *own* submitted bundle, not server internals, so redacting them would gut the hosted path's diagnostics.

```python
report = exc.to_error_report()
report.to_dict()  # {"error_type": "LLMCompletionError", "message": "...", ...}
ErrorReport.from_dict(d)  # strict inverse — raises ValidationError on a malformed dict
report.http_status  # 422 / 429 / 500 — for HTTP adapters
```

!!! warning "`ErrorReport` is `extra="forbid"`"
    `from_dict()` rejects unknown keys, so it is the strict inverse of `to_dict()`. A report dict that crosses a serialization boundary and fails validation on the way back is an internal contract bug — the writer and the reader share the schema within one deploy. A cross-boundary recovery helper that rebuilds a report (e.g. a distributed-worker bridge) is expected to catch that `ValidationError` and synthesize a fallback report so failure-webhook delivery stays intact while keeping the contract bug visible; any other caller of `from_dict()` should treat the validation failure as a bug to fix.

### `suggested_fix` — structured deterministic fixes

When a validation error has a deterministic remedy, its `ValidationErrorItem` carries a `suggested_fix` — a `SuggestedFix` (`pipelex/suggested_fix.py`, deliberately stdlib+pydantic-only so `pipelex.base_exceptions` can import it without a cycle; naming is brand-neutral, fixes are a language-level concept):

- `fix_code` — the kebab-case rule id (e.g. `match-sequence-output`). The planner's `KNOWN_FIX_CODES` set is the validation set for user-facing rule filters (`--select` / `--ignore`); an unknown code is rejected loudly, never lenient-ignored, because a typo'd filter selects *behavior*.
- `description` — human-readable statement of the change.
- `safety` — `safe` fixes may be auto-applied; `unsafe` ones need a person's or an agent's confirmation, and `pipelex fix bundle` never applies them. Every prose rendering labels an unsafe fix `💡 Suggested fix (unsafe, confirm before applying):` where a safe one reads `💡 Suggested fix:`, through the one `suggested_fix_label` in `pipelex/pipeline/validation_render.py`.
- `source` — the file the ops target, when known (multi-file libraries). An applier must only apply ops to the file they target.
- `ops[]` — the fix itself, as **semantic TOML patch ops** addressed by table path (`FixOpKind`: `set_key`, `ensure_table`, `delete_key`, `delete_table`, `rename_table_key`, `move_key`, `remap_value`; each op's `table_path` follows the same conventions as the items' `field_path`). The ops are the machine contract; any rendered diff or `💡 Suggested fix:` line is presentation.

    The op vocabulary is a **discriminated union on `kind`**: one model per kind, each declaring exactly the fields its own semantics need and forbidding the rest, so `{"kind": "delete_key", …, "new_key": "x"}` is a parse error rather than a stray field the applier silently ignores. Two aliases are published from the same union — `FixOp`, every kind, which is what `ops[]` is typed as, and `MigrationOp`, the structural kinds only (`delete_key`, `delete_table`, `rename_table_key`, `move_key`, `remap_value`), which is what a configuration [migration ledger](../migration-ledger.md) is parsed against. The narrow alias is what keeps a materializing op — one that writes a value the file did not have — out of a ledger that is replayed over every user file on every run.

The **fix planner** (`pipelex/pipeline/fixes/planner.py`) translates enriched typed error data into `SuggestedFix` payloads — pure functions keyed strictly on `error_type` + structured fields, never on message strings. Each rule fires only when its enrichment is present (set only at the raise sites that know the correct value), so the same error type raised elsewhere without enrichment is structurally suppressed. The planner runs inside `build_validation_error_items()`, so every consumer of the validation report — CLI, API, MCP — sees fixes with zero extra plumbing.

Applying fixes is the runtime's job too: the **applier** (`pipelex/fix_ops/applier.py`) mutates a tomlkit DOM in place per op (guarded — an op whose target table is absent is skipped and reported, never raised) and then reflows the whole file to canonical MTHDS style, and the **convergence loop** (`pipelex/pipeline/fixes/fix_loop.py`) runs validate → apply SAFE fixes → re-validate to a fixed point, reporting non-convergence loudly. The user-facing surface is [`pipelex fix bundle`](../tools/cli/fix.md).

On the hosted API the same payload rides the wire verbatim as `validation_errors[].suggested_fix`; how it appears in HTTP error responses is documented on the API side, in the API server's [Error Responses](../api-server/error-responses.md#suggested-fixes) page.

---

## Classification Enums

Two `StrEnum`s sit beside the code. Neither decides anything a reader branches on any more: the code does.

### InferenceErrorCategory

Defined in `pipelex/cogt/exceptions.py`. It stays inside the runtime as the classification that **picks a provider failure's code**: the worker's classification (`pipelex/cogt/inference/error_classify.py`) reads the provider's answer, assigns a category and a code together, and the rendered error carries both. The category also still drives one decision the code cannot carry: whether the Temporal activity may repeat a provider call within the run, through `is_retryable` and `find_inference_error_category_in_chain`. A call whose outcome is unknown (`AMBIGUOUS`) must never be repeated within the run, though its code, `provider.outcome_unknown`, says a new run may succeed.

| Category | Meaning | Repeated within the run | Typical codes |
|----------|---------|-------------------------|---------------|
| `TRANSIENT` | A brief, self-correcting failure | ✅ | `provider.rate_limited`, `provider.unavailable`, `provider.timeout`, `provider.failed` |
| `CONFIGURATION` | The setup is wrong | ❌ | `provider.credential_refused`, `model.unavailable`, `pipelex.config.*` |
| `CONTENT` | The input or prompt is wrong | ❌ | `model.content_refused`, `model.context_exceeded`, `input.file_type_unsupported` |
| `CAPACITY` | Account quota / billing exhausted | ❌ | `provider.quota_exhausted` |
| `AMBIGUOUS` | Outcome unknown — may have committed | ❌ | `provider.outcome_unknown` |
| `UNKNOWN` | Could not classify | ❌ | `runtime.unexpected` |

The category and the code are checked against each other. A classification whose category repeats the call within the run must pick a code whose verdict invites a retry, so `ClassificationResult` and a plugin's service error vocabulary both refuse a `TRANSIENT` entry naming a code such as `runtime.unexpected`. An error a worker or a plugin builds by hand with a category and no code reports its category's code, `InferenceErrorCategory.default_error_code`, when its class declares that code and nothing down its cause chain names one: `TRANSIENT` reads `provider.unavailable`, `CONFIGURATION` `runtime.misconfigured`, `CAPACITY` `provider.quota_exhausted` and `AMBIGUOUS` `provider.outcome_unknown`, while `CONTENT` and `UNKNOWN` name no code, since a content failure may be the caller's material or a request the runtime built, and such an error keeps its class's fallback. A local `OSError` on a local extractor is the machine's, not the input's and not a provider's, so it is `UNKNOWN` with a contact-support next step and `runtime.unexpected`, and it is not repeated within the run.

!!! info "`AMBIGUOUS` vs `UNKNOWN`"
    `AMBIGUOUS` means the *error type is known* but the operation may or may not have committed — a blind retry is unsafe for a non-idempotent call. `UNKNOWN` means classification itself failed. Both are non-retryable, for different reasons.

### ErrorDomain

Defined in `pipelex/base_exceptions.py`. A report's `error_domain` is read from the domain the registry gives its code, through `ErrorDomain.from_problem_domain()`, and drives the HTTP status until the problem document carries the code's own status and five-valued domain:

| Code's domain | `error_domain` | HTTP status | Who acts |
|---------------|----------------|-------------|----------|
| `input` | `INPUT` | **422** | The caller, by changing the request or its inputs |
| `method` | `INPUT` | **422** | The method's author, by changing the method |
| `account` | `CONFIG` | **500** | The account's owner |
| `operator` | `CONFIG` | **500** | Whoever runs the runtime |
| `runtime` | `RUNTIME` | **500** | Nobody beforehand: wait, retry or report |

`error_domain_to_http_status()` is the pure mapping table — it maps an unset or unrecognized domain to 500 as well. `ErrorReport.http_status` layers one rule on top: a provider 429 (`provider_metadata.status_code == 429`) takes precedence over the domain, so the API can emit a `Retry-After` header.

No class declares a domain: a class whose raise sites need two readings declares two codes, and the raise site chooses.

#### Classified where it is raised

The code says who must act. Whether the error's *message* may be shown to the caller is a separate fact: `_authors_caller_facing_message = True` on a class whose message is copy written for the caller, which STRICT disclosure then keeps instead of replacing it with `An internal error occurred.`. A few classes are raised both with messages that describe only the caller's own method or inputs and with messages that do not, so they cannot state it. For those, the site that raises the error and knows calls `as_caller_fault()` on it, which marks this one message caller-facing and may pass a next step; the domain stays the code's, which the raise site chooses with `with_error_code()` when the class declares a set.

```python
raise (
    PipeRunInputsError(message=msg, run_mode=run_mode, pipe_code=pipe_code)
    .with_error_code(CoreCode.INPUT_MISSING)
    .as_caller_fault(
        user_action=UserAction(kind=UserActionKind.CHANGE_INPUT, detail="Provide the missing required inputs of 'flow': topic."),
    )
)
```

The raise site vouches for the message: it names only the caller's own method and data (pipe codes, concept codes, variable names, the values the caller sent), never a path on the host, a secret or the text of a foreign exception. A plain wrapper raised from the error takes its code when it declares none of its own, but never its caller-facing flag, since the wrapper's message is its own; the located wrappers of a run failure report their root fault, so they carry both.

| Raise site | Error | Why its message is the caller's |
|------------|-------|------------------------------|
| A `PipeParallel` combining its branch results into its output | `StuffFactoryError` | The method sets which branch feeds which field, what each branch produces and whether it produces a list. A branch whose multiplicity differs from its field's is restated by a second `StuffFactoryError` raised from the combine's, whose next step names the multiplicity to change, and which the run reports as its root fault |
| A pipe checking that its required inputs are present | `PipeRunInputsError` | The request, or an earlier step of the method, left the input out |
| A `PipeCondition` whose expression renders nothing, whose outcome is `fail`, whose chosen pipe misses inputs, or, in a dry run, whose expression does not parse, whose outcomes name no pipe or whose every outcome is `fail` | `PipeRunError` | The method writes the expression and the outcomes, and the run's data it renders is the caller's; the messages name only the pipes and the input names, never the expression's text or the value it rendered, either of which may be a host library's |
| A model lookup for a reference the deck neither defines nor names in any of its own entries | `ModelNotFoundError` | Only an inline model setting of the method can have named it, so the next step is a `CHANGE_MODEL` action naming the reference as the method wrote it and the type of model the lookup needs; a reference the deck names but cannot serve stays `config` and redacted, with no next step of its own |

Some failures carry their code with a message that stays redacted under STRICT on purpose, each with a sentence at its raise site saying why: a model output that does not fit its structure, which depends on what the model produced; a `PipeFunc` crash, whose exception text can carry anything the process holds; an input resource the pipe cannot use, whose message names the path as resolved on the host; a template that fails to render, where the same failure can come from the template or from the data; and a working-memory miss, since a step naming a variable nothing produces is refused when the bundle loads.

---

## Worker Classification

Layer 0 → Layer 1. Every inference worker under `pipelex/providers/*/` catches its SDK's typed exceptions and re-raises a categorized `CogtError`.

### The Uniform Shape — Extract / Classify / Render

Every inference worker's SDK-exception handler collapses to a three-step pipeline: **Extract** turns the SDK exception into a provider-blind `ProviderErrorMetadata`, **Classify** maps that metadata to a category + user-action, and **Render** picks the `CogtError` subclass to raise.

```python
except (APIError, APIConnectionError, APITimeoutError) as exc:
    metadata = extract_openai_metadata(exc)
    classification = classify_inference_error(metadata)
    raise render_inference_error(
        metadata=metadata,
        classification=classification,
        family=InferenceErrorFamily.LLM,
        model_desc=self.inference_model.desc,
        model_handle=self.inference_model.name,
    ) from exc
```

The three steps live in three modules. Only the per-provider Extract functions stay plugin-local; Classify and Render are single shared functions.

| Module | Step | What it owns |
|--------|------|--------------|
| `pipelex/cogt/inference/error_classification.py` | Extract | `ProviderErrorMetadata`, `SDKErrorEnvelope`, `UserAction`, `UserActionKind`, the `extract_*_metadata` functions and the parsers they share (`parse_retry_after_seconds`, `error_code_from_body_code_first`), plus pure discriminators (`is_quota_exhaustion`, `is_content_policy_violation`, `is_network_error`, `is_model_not_allowed`) exposed as `@property` on the metadata |
| `pipelex/cogt/inference/error_classify.py` | Classify | `classify_inference_error()` — provider-blind mapping from `ProviderErrorMetadata` → `ClassificationResult(category, user_action_kind, is_model_not_found, service_error_code, is_model_not_allowed)`, consulting the booted plugins' service error vocabulary ahead of the status ladder |
| `pipelex/cogt/inference/error_render.py` | Render | `render_inference_error()` — picks the `CogtError` subclass from `InferenceErrorFamily` plus `is_model_not_found` (e.g. `LLMModelNotFoundError` vs `LLMCompletionError`) |

Provider-specific nuance is normalized away in Extract (e.g. Google's `code` becomes `status_code`; AWS Bedrock error codes are mapped to HTTP statuses), so Classify has no provider branching. HTTP status drives classification; status-less errors dispatch on the SDK exception type name. The `tests/unit/pipelex/cogt/inference/test_provider_classification_parity.py` meta-test walks every `ProviderName` against the extract-fn registry so adding a new provider without wiring it fails fast.

### ProviderErrorMetadata and UserAction

Every raised inference error carries structured SDK metadata and typed advice.

```python
class ProviderErrorMetadata(BaseModel):
    provider: str
    sdk_exception_type: str
    status_code: int | None = None
    request_id: str | None = None
    retry_after_seconds: float | None = None
    provider_error_code: str | None = None
    body: Any | None = Field(default=None, exclude=True)  # may carry secrets
```

!!! warning "`body` is excluded from serialization"
    The raw provider response `body` can carry account ids, billing details, or credential fragments. It is held in-process but `exclude`d from every serialized form — CLI JSON, agent output, and any serialized worker payload.

`UserAction` pairs a discrete `UserActionKind` (`WAIT_AND_RETRY`, `CHECK_BILLING`, `CHECK_CREDENTIALS`, `CHANGE_INPUT`, `CHANGE_MODEL`, `CONTACT_SUPPORT`, `UNKNOWN`) with a free-form `detail` string — so the CLI can render consistent guidance while keeping provider-specific text.

The `detail` is read on a failed run's report, once every automatic retry is spent, so it says what the reader can do next and never promises another attempt by the system: the `WAIT_AND_RETRY` advice says to wait, at least the provider's `Retry-After` delay when it gave one, then run it again.

### Service Error Codes

Not every failure on an inference call comes from a provider. A gateway or a hosted inference service may refuse a request itself, before a model ever sees it, under error codes of its own, and those refusals arrive on statuses the ladder reads as a provider rejecting the prompt. The plugin that speaks to such a service contributes the codes it emits through `PluginRegistrar.add_service_error_codes`, each with its category, its action and its advice, and `classify_inference_error` consults that vocabulary ahead of the status ladder. The seam is described in [Service Error Codes](service-error-codes.md).

### A Model the Integration Does Not Allow

One refusal outside any service's own namespace is classified by the runtime itself: `model_not_allowed_error`, Portkey's answer, at 412, when an integration serves the model but does not allow it for this caller, because the model is off the integration's allow-list or archived. Portkey's cloud emits it for a user's own workspace behind the `portkey` backend, and so does any gateway built on Portkey's middleware; the refusal means the same thing and calls for the same move from any of them, so it is matched on the code alone (`MODEL_NOT_ALLOWED_ERROR_CODE`). It carries its code in `error.type` with `error.code` null, and every Extract hop recovers it from there.

| Code | HTTP | Category / action | What the caller is told |
|------|------|-------------------|-------------------------|
| `model_not_allowed_error` | 412 | `CONFIGURATION` / `CHANGE_MODEL` | the gateway does not allow the model, named by its handle, for this account — pick another; if the pipe named it, leaving the pipe's model unset uses the default |

- **It is not a model-not-found.** The model exists and an integration serves it, only not for this caller, so `ClassificationResult.is_model_not_allowed` is set and `is_model_not_found` is not: the error stays on the family's generic failure class and carries the distinction in its advice. The ladder's generic 4xx arm would have given it the right category and advice sending the caller to edit their inputs.
- **Its advice names the model.** The refusal's message names only the backend's wire id (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`), which the method's author never wrote, so the advice names the model handle the deck resolved the pipe's model to. Both of its hints are conditional, because the Render step cannot tell the cases apart: leaving the pipe's model unset helps only when the pipe named the refused model rather than falling back to it as the default, and a model deck that lists a model the allow-list refuses is the operator's to settle on a hosted gateway and the user's own on a Portkey workspace of theirs.
- **It answers 500 on an HTTP surface.** It carries `model.unavailable`, a code in the operator's domain, which reads `ErrorDomain.CONFIG` and which `error_domain_to_http_status` renders as 500: it lands in server-error alerting, and its verdict tells a client not to retry, since an outer retry earns an identical refusal.

### The `instructor` Unwrap

On structured-generation paths, `instructor` raises an `InstructorRetryException` from the exception that ended its retry loop. The loop re-asks only a response that fails the schema, so that exception is either the raw SDK exception of a call that failed in transport, or, once the re-ask budget is spent, the last parse failure. `extract_underlying_sdk_exception()` recovers it from the wrapper's cause, not from `failed_attempts`, which lists only parse failures and would name an earlier one when a re-ask then fails in transport. The recovered exception routes through the same per-provider categorization as the plain-text path. Once the re-ask budget is spent, the recovered exception is the last `pydantic.ValidationError`, which `_STATUSLESS_BY_TYPE_NAME` classifies as `CONTENT` / `CHANGE_INPUT` with `model.output_schema_mismatch`, so it answers 422. A recovered exception the classifier does not recognize lands in `UNKNOWN`.

### Model and Provider Attribution

Inference-failure leaf errors (`LLMCompletionError`, `ImgGenGenerationError`, …) are raised deep inside a plugin and do not know which model handle invoked them. Each worker family fills that in at its public-method chokepoint:

```python
def fill_model_and_provider(self, model_handle: str | None, *, backend_name: str | None) -> None:
    """Fill model_handle / backend_name from the worker, only when still unset."""
```

---

## Cause-Chain Enrichment

A wrapper exception — `PipeRunError` → `PipeRouterError` → `PipelineExecutionError` — carries no `error_category` of its own. Its code comes from `resolve_error_code()`, which already walked the `__cause__` chain (see [Every error declares its code](#every-error-declares-its-code)); `to_error_report()` then enriches the report's diagnostic fields from the chain, so the inference classification survives every wrapping layer.

```python
def _enrich_error_report_from_cause(self, report: ErrorReport) -> ErrorReport:
    cause = self.__cause__
    if not isinstance(cause, PipelexError):
        return report
    cause_report = cause.to_error_report()
    return report.model_copy(
        update={
            "error_category": report.error_category or cause_report.error_category,
            "user_action": report.user_action or cause_report.user_action,
            # ... model, provider, provider_metadata ...
        }
    )
```

A wrapper keeps its own `error_type` and `message`, and its code with everything the code decides, but inherits every diagnostic field it does not set itself. The two wrappers of a run failure go further, and report their root fault instead of themselves: see [Run Failures: the Root Fault, Located](#run-failures-the-root-fault-located).

!!! warning "Overrides must call the enrichment helper"
    A `to_error_report()` override on a subclass **must** end with `self._enrich_error_report_from_cause(report)`. Otherwise that subclass becomes a black hole that drops the cause's classification. A cyclic-`__cause__` guard ensures a malformed chain can never turn error reporting into a `RecursionError`.

---

## Run Failures: the Root Fault, Located

When a pipe fails during a run, the error a surface receives sits under several wrappers: the pipe router's `PipeRouterError`, maybe a runtime bridge's `PipelexBridgeDispatchError`, and the runner's `PipelineExecutionError`. None of them is what went wrong, and a report reading `PipelineExecutionError` with a bridge's sentence for a message tells the reader nothing. So the two located wrappers, `PipeRouterError` and `PipelineExecutionError`, which take their cause's code, report the **root fault** and only add where it happened (`pipelex/pipe_run/located_failure.py`). The root fault is the error whose code the failure resolves to: the first `PipelexError` down the cause chain that declares a code of its own, the walk `resolve_error_code()` makes, so a wrapper that adds the fact deciding the code (a PipeFunc's `pipe.function_raised` over a coded error its function raised) is the root fault over its cause, and the innermost `PipelexError` when none declares one. The walk stops at the first exception that is not a `PipelexError`, whose stand-in is then the fault.

**Locating.** `PipeRouterProtocol.run()` catches every failure of the pipe it runs and re-raises it as a `PipeRouterError` chained to it, with the pipe's code and a snapshot of its stack taken where it failed. A failure that already carries a `PipeRouterError` rises untouched through the routers of the controllers above, so the innermost location is the one reported. An exception that is not a `PipelexError` first becomes a `PipelexUnexpectedError` whose message names its class (`KeyError: 'boom'`); it is never caller-facing, and a dry run that sorts its own failures from programming bugs (the bundle validator's sweep, the validate surfaces' graph step) finds the foreign exception behind it with `find_foreign_fault()` and lets it propagate rather than report it as the bundle's failure. A host router whose transport raises its own failures overrides the `_as_pipelex_failure()` hook, and returns `None` for a control-flow exception such as a cancellation, which then propagates as it is. For a transport failure carrying a recovered report, the far side packs the root fault's own report, never a located one: when it packs that report alone, the hook returns a `PipelexError` carrying it and the router locates it at the pipe it ran; when it packs the location it found as well, the hook returns a `PipeRouterError` rebuilt over that report with `make_located()`, which the router raises untouched, so the report reads exactly as the local run's. The runner wraps any failure of the run into a `PipelineExecutionError` with `make_for_run_failure()`, which takes the location from the innermost `PipeRouterError` on the chain (`find_failure_location()`), never from the live stack, which has unwound by then.

**The report.** Both wrappers build the same report from the same root fault (`find_root_fault()`):

| Field | Taken from |
|-------|------------|
| `code`, `error_type`, and what the code decides: `title`, `type_uri`, `error_domain`, `retryable` | The root fault |
| `message` | The root fault's own message, prefixed with the failing pipe and its path |
| `caller_facing_message`, `validation_errors`, `migration` | The root fault |
| `error_category`, `model`, `provider`, `provider_metadata` | The cause-chain enrichment |
| `user_action` | The cause-chain enrichment or, when nothing on the chain advises an action, a fallback naming the failing pipe |

The message reads `Pipe 'summarize' failed (two_steps → summarize): Model handle 'x' was not found in the model deck.` for a nested pipe, and `Pipe 'flow' failed: …` for the entry pipe. Pipe codes are the caller's own names, so the located message is caller-facing exactly when the root fault's message is, and STRICT disclosure keeps it exactly then. `ErrorReport` has no location field, so the location rides the message; `PipeRouterError` and `PipelineExecutionError` carry it structurally as `pipe_code` and `pipe_stack`.

**A recovered report is taken as it is.** A distributed submitter receives a report that was already located on the worker. When it raises that report inside a `PipelexError` whose `to_error_report()` returns it, and no `PipeRouterError` sits on the submitter's own chain, the runner's `PipelineExecutionError` reports it verbatim: its `pipe_code` is the entry pipe, its `pipe_stack` is empty, and the message is not located a second time. A located report must never reach a router this way, since the router would locate it again: that is why a host router's transport packs the root fault's own report. A bridge's own sentence (`Pipe execution failed in DIRECT mode …`) appears in neither the report nor the message, so a run gives the same report whether it ran in process, through the in-process orchestrator or on a remote worker.

**Where the remedy goes.** A root fault's message states the fact and nothing else, because it reaches every surface, a hosted run's stored error included. Advice that only a local reader can act on belongs to the local CLI: `pipelex run` renders the model panel of a `PipeOperatorModelAvailabilityError` found anywhere on the chain, and the panel's tip is where the local model deck remedy lives.

---

## Crossing a Distributed Worker Boundary

The error model is built to survive serialization. Because `ErrorReport` round-trips through `to_dict()` / `from_dict()`, a failure that happens on a remote worker can reach the submitting process with its full classification intact — not just a message string.

The runtime itself stays transport-agnostic: the machinery that carries an error across a worker boundary ships in the **host-runtime plugin** for each distributed backend, not in core. A backend plugin is responsible for three things.

**Packing.** Convert a `PipelexError` into the transport's failure type and stash `to_error_report().to_dict()` in its details payload, so worker and submitter code keep the code and the full classification rather than a bare message. The same step derives the transport's retry decision from `InferenceErrorCategory.is_retryable`, which tells a provider call that may be repeated within the run from one whose outcome is unknown.

**Recovering.** On the submitter side, walk the returned failure, pull the packed dict, and rebuild the `ErrorReport`. Recovery is **total**: when no report dict is found — a non-Pipelex exception, a worker crash, a timeout — the plugin synthesizes a fallback report so the recovery path always has structured classification to surface.

**A fail-safe floor.** Ensure a domain error that escapes the conversion path fails the unit of work *terminally* rather than hanging. In a durable-execution system the default for an unconverted exception might be to retry forever, so "convert all the errors we know about" is not enough — the floor must hold for the errors, and the code paths, that nobody enumerated.

**Net effect:** a pipe failing on a remote worker reaches the CLI and HTTP adapters with the *same* `code` / `error_category` / `retryable` / `model` / `provider` / `user_action` as the identical failure run locally — and a failure that escapes conversion fails loud and bounded instead of hanging.

See [Runtime Bridge & Transport](./runtime-bridge-and-transport.md) for the boundary these converters span; the per-backend converters themselves live in the host-runtime plugins.

---

## Security Refusals and the Security Event

A refusal a security rule makes is a failed run and a security event. The run fails under a code of the `security.` family of the core registry, or of Pipelex's own `pipelex.security.` family, and that code's domain says who caused the refusal: `security.input_url_refused` and `security.input_path_refused` are the caller's, `security.method_url_refused`, `security.method_path_refused`, `security.template_refused`, `security.schema_refused` and `security.integrity_mismatch` are the method's, and `security.provider_url_refused` is the runtime's, a URL a model's answer named. A refusal is coded where it is raised, as every error is, and every wrapper above it takes its cause's code, so the failure a host receives reports the security code however many boundaries it crossed. A `SecurityError` is never absorbed into a verdict or a domain answer on the way. One refusal is coded otherwise on purpose: the sandbox refusing one of Pipelex's own templates is our bug, `runtime.unexpected`, and so it is no security refusal and logs no event.

Beside the failure, the deployment logs one **security event**, so that whoever runs it learns that someone tried to reach what a rule forbids. It is a structured log record of its own kind, routable without reading its text: it is logged at warning level on its own logger, `pipelex.errors.security_event`, with the fixed message `A security rule refused a request`, and its `event.name` field is `pipelex.security.refusal`. It goes through the deployment's log sinks like any other record, so a hosted deployment routes it to its alerts and an on-premises one receives it in its own sinks, and nothing leaves the deployment because of it. Its fields name the refusal and never its content:

| Field | What it carries |
|-------|-----------------|
| `event.name` | `pipelex.security.refusal` |
| `error.code` | The refusal's code, such as `security.method_url_refused` |
| `error.domain` | The code's domain, who caused it: `input`, `method` or `runtime` |
| `error.type` | The class of the error that carries the code, such as `SsrfBlockedError` |
| `security.target` | The kind of thing refused, which the code decides: `url`, `path`, `template`, `schema`, `dependency`, `object_key` or `result_location` |
| `security.target_class` | The class of destination refused, when the raise site knows it: `loopback`, `private`, `link_local`, `metadata` (a cloud metadata endpoint), `scheme` (a scheme the run does not read, a `file://` URL or a path on the server's disk among them) or `foreign_storage_key` (a storage key outside the run's read scope) |
| `pipeline_run_id`, `request_id` | The run and the request, when there are some |
| `run.extras.<key>` | Each of the run's opaque extras, one field per key, which the hosted plane fills with the organization |

Never the URL, the path, the template, the schema, a prompt or an input value, nor the error's message, which may quote any of them, and never a traceback: the failure itself is reported where it is handled, as any other failure is. The runtime does not know organizations, so the event names one only through the run's extras, which it carries without reading.

The class of destination is stated where the refusal is decided, with `PipelexError.with_security_target_class()`. The SSRF guard classifies the host it refused, or the first disallowed address a name resolved to, through `classify_disallowed_host` in `pipelex/tools/network/host_rules.py`, and a read the run's read scope refuses takes its class from its reason, a storage key of another tenant or a scheme the run does not read. A refusal that states no class, such as a schema or a template refusal, has no `security.target_class`.

**Where it is logged.** `pipelex/errors/security_event.py` holds the event, and three boundaries call it, each with what it knows of the run:

- the direct-mode run, `PipeRun`, for a refusal any of its pipes raised, with the run's identity, its extras included;
- the runner, `PipelexMTHDSProtocol.execute`, for a refusal before the run exists, at the input seam or while the method loads, with the runner's extras, and for a run failure the direct-mode run never saw, one a remote orchestrator reported or one raised around the pipes;
- the API server's handler of every `PipelexError`, for a refusal answered before any run, with the extras the request body carried.

A refusal is reported once per process, however many of these boundaries it crosses: the event marks the errors of the chain it reported, and a boundary that receives the same failure again, wrapped, finds the mark and logs nothing. A host whose transport rebuilds a failure from a worker's report, where the worker already logged the event, marks the rebuilt error with `mark_security_event_emitted()`; a host that decides a refusal itself, such as a gateway's refusal of a private address or a tenant-boundary refusal of its own, logs the same record with `log_security_event()`. A program embedding the kernel without the runner (see [The Pipelex Kernel](./pipelex-kernel.md)) calls `emit_security_event()` on the refusals it receives.

---

## Interfaces

### CLI

The agent CLI (`pipelex-agent`) emits a structured error to **stderr**, markdown by default and JSON with `--error-format json`. When `--error-format` is omitted it **inherits the value of `--format`** (the success-output flag) — so `--format json` still flips both as it did before the split. Both exit with code 1.

| Command | Error output |
|---------|--------------|
| `run`, `validate`, `init`, `models`, `check-model`, `doctor` | Markdown (default) or JSON via `--error-format` (or via `--format`, which `--error-format` inherits) |
| `inputs` | JSON only |
| `fmt`, `lint` | Native `plxt` output (subprocess passthrough); falls back to JSON only when the `plxt` binary itself is missing |

The human CLI (`pipelex`) renders a Rich error panel — red banner, structured fields, the `user_action` tip, doc/Discord links — through the shared `display_error_panel()` helper in `pipelex/cli/error_handlers.py`.

#### Validate exit-code policy (0 / 1 / 2)

The `validate` surface — both the bare `pipelex validate {bundle,method,pipe}` group and the agent CLI's `pipelex-agent validate` — exits with **three** codes that mirror the hosted `/validate` 200-verdict-vs-non-2xx-no-verdict split:

| Exit | Class | Condition |
|------|-------|-----------|
| `0` | valid | `is_valid` — including valid-but-not-runnable **with** `--allow-signatures` |
| `1` | negative verdict | a produced "no": an invalid bundle (`ValidateBundleError`), or valid-but-not-runnable **without** `--allow-signatures` (a strict signature breach) |
| `2` | no verdict | the CLI could not produce a verdict — bad args, an unresolvable target (no `.mthds` in a directory, a missing file, an unknown/ambiguous pipe code), or a setup/internal error during validate |

**The verdict lives in the structured `is_valid` field, not the exit code.** The exit code is a convenience signal for naive shell/CI/Makefile use (`set -e`, `cmd && next`, `if cmd; then`); machine consumers (hooks, the Codex hook, runners) MUST read `is_valid` (and `error_domain`) from the JSON for their block/warn decisions rather than branching on the exit code. Decoupling the verdict from the exit code is what keeps any future exit-code change non-breaking. The 1-vs-2 split is also additive for flat consumers: both stay non-zero, so anything that only tests zero-vs-non-zero is unaffected.

Implementation: the agent CLI threads `exit_code` through `agent_error(...)` (`agent_output.py`, default 1); the validate commands pass `exit_code=2` at every no-verdict site and keep the default 1 on the `ValidateBundleError` arm and the signature gate. The bare CLI sets the code directly via `typer.Exit(...)` in `cli/commands/validate/*` and via the `exit_code` parameter on `handle_model_availability_error` in `cli/error_handlers.py`. Every refusal of the bundle is a negative verdict on both CLIs: `validate bundle` and `validate method` validate through the shared cascade, and `validate pipe` and `validate --all` load their libraries through it too, so an unknown model or any other load-time refusal exits 1 with the invalid-bundle output rather than a traceback or the no-verdict exit 2. The bare `validate pipe` and `validate --all` also run their dry run through it, so a pipe whose dry run fails is rendered like any other invalid bundle; the agent CLI answers that failure with its `DryRunError` envelope, `is_valid: false` and exit 1. Shared boot handlers (`make_pipelex_for_cli`'s telemetry-config and model-deck-preset paths) stay exit 1 — they are shared across `run`/`build`/`validate` and out of the validate-policy scope.

### API

`pipelex` is a library — there is no API server in the package. Downstream HTTP repos consume the `ErrorReport`:

- `error_domain_to_http_status(error_domain)` — pure domain → status table.
- `ErrorReport.http_status` — full property, layering the provider-429 passthrough on top.

A downstream FastAPI exception handler calls `ErrorReport.http_status` and is a trivial adapter — it must not redefine the mapping.

### Inputs and Outputs

**Inputs.** `to_error_report()` takes a live `PipelexError`. `ErrorReport.from_dict()` takes a `to_dict()` payload — strictly, raising `ValidationError` on drift. (A distributed-worker bridge adds a cross-boundary recovery helper that walks a returned failure's `__cause__` chain and rebuilds the report; it lives in the host-runtime plugin, not core.)

**Outputs.** `to_error_report()` returns an `ErrorReport`; `to_dict()` returns a `None`-free `dict`. Side effects: telemetry events emitted on pipeline failure at Layer 3; the agent CLI writes to stderr and raises `typer.Exit(...)` — code 1 by default, or the validate surface's 0/1/2 policy (see [Validate exit-code policy](#validate-exit-code-policy-0-1-2)).

---

## Architecture

```mermaid
flowchart TB
    SDK["Layer 0 — SDK exception<br/>(openai.RateLimitError)"]
    W["Layer 1 — Worker classifies<br/>is_quota_exhaustion_*() → CogtError<br/>+ InferenceErrorCategory + ProviderErrorMetadata"]
    WRAP["Layers 2-3 — Wrappers<br/>PipeRouterError → PipelineExecutionError<br/>(locate the root fault)"]
    REPORT["ErrorReport<br/>via to_error_report() + cause-chain enrichment"]

    SDK -->|"raise ... from exc"| W
    W -->|"raise ... from exc"| WRAP
    WRAP --> REPORT

    REPORT --> RICH["Human CLI<br/>Rich panel"]
    REPORT --> AGENT["Agent CLI<br/>JSON / Markdown"]
    REPORT --> HTTP["HTTP adapters<br/>.http_status"]

    W -.->|"pack on worker"| TEMP["Distributed worker bridge (plugin)<br/>report packed into transport details"]
    TEMP -.->|"recover on submitter"| REPORT

    classDef src fill:#fff3e0,stroke:#e65100,color:#000
    classDef cls fill:#e8eaf6,stroke:#3949ab,color:#000
    classDef out fill:#e8f5e9,stroke:#2e7d32,color:#000
    class SDK src
    class W,WRAP,REPORT,TEMP cls
    class RICH,AGENT,HTTP out
```

---

## Implementation

### Class Hierarchy

`PipelexError` is the single root, and every subclass declares its code (see [Every error declares its code](#every-error-declares-its-code)). `CogtError` is the inference branch: an abstract base whose subclasses declare the codes the classification picks from, and which overrides `to_error_report()` to add `error_category`, `provider_metadata`, and the `model_handle` / `backend_name` it reads from the instance.

```
Exception
└── PipelexError                  base_exceptions.py — error_code, with_error_code(), resolve_error_code(), to_error_report()
    ├── PipelexUnexpectedError     → runtime.unexpected
    ├── PipelexConfigError         → one of pipelex.config.invalid, .syntax, .file_missing
    ├── PipelexSetupError          → inherits its cause's code, else runtime.misconfigured
    ├── SecurityError              base_exceptions.py — abstract; the policy refusals never absorbed into a domain answer
    │   ├── UriReadRefusedError / SsrfBlockedError   → security.input_url_refused, .method_url_refused (and .provider_url_refused)
    │   ├── UnsafeSchemaError                        → security.schema_refused
    │   └── Jinja2TemplateSecurityError              → security.template_refused, else runtime.unexpected on Pipelex's own template
    ├── CogtError                  cogt/exceptions.py — abstract; error_category, provider_metadata
    │   ├── LLMCompletionError      ← a set the worker's classification picks from
    │   ├── ImgGenGenerationError   ← a set the worker's classification picks from
    │   └── ... (see worker classification) ...
    ├── PipelineExecutionError      pipeline/exceptions.py — reports its located root fault and its code
    └── ... (one exceptions.py per package) ...
```

`SecurityError` is the base class of the policy refusals that are never absorbed into a domain answer: `UriReadRefusedError` (a read outside the run's scope), `SsrfBlockedError` (an outbound request the SSRF guard blocks), `UnsafeSchemaError` (a schema carrying Python code-generation extensions) and `Jinja2TemplateSecurityError` (a template the sandbox refuses at render time). The handlers that turn a refusal of the caller's input into a verdict, the bundle-validation cascade and the library load, let a `SecurityError` through as it is, and a host that treats this family alike, a durable-execution plugin marking it non-retryable for instance, names that base class. Not every refusal belongs to it: the template sandbox's render-budget refusal, `Jinja2TemplateBudgetError`, is a `ToolError` coded `pipe.template_budget_exceeded`, and `TemplateUrlRefusedError` derives from `PipelexError` directly, so each is handled by its code like any other refusal.

### Factory-time vs Runtime

| When | What carries metadata | How |
|------|----------------------|-----|
| **Class definition** | `error_code` (a code, a set, its cause's, or abstract), `error_category` defaults, `user_action` defaults | Class-level attributes — one source of truth per exception type |
| **Raise time** | The code chosen from the class's set, per-instance `error_category`, `user_action`, `provider_metadata` | `with_error_code()` and constructor args — set by the raise site or the worker that classified the failure |
| **Report time** | The resolved code and everything it decides; `model`, `provider`, cause-chain fields | `resolve_error_code()` and `ErrorReport.make_for_code()`; `fill_model_and_provider()` at the worker chokepoint; `_enrich_error_report_from_cause()` on `to_error_report()` |

The "outcome" exceptions (`LLMCompletionError`, `ImgGenGenerationError`, `ExtractJobFailureError`, `SearchJobFailureError`) intentionally carry **no** class-level `error_category` — their category and their code are genuinely per-instance, decided by the worker.

---

## Reference

### Quick-Ref

```python
# Produce a report from any PipelexError
report = exc.to_error_report()  # enriched from the __cause__ chain
payload = report.to_dict()  # None-free dict for serialization


# Declare a class's code, and choose one of its set where it is raised
class SomeError(PipelexError):
    error_code = ErrorCodeSet(default=CoreCode.INPUT_INVALID, others=(CoreCode.INPUT_MISSING,))


raise SomeError(msg).with_error_code(CoreCode.INPUT_MISSING).as_caller_fault(user_action=user_action)  # caller-facing

# Consume a report
report.code  # "input.missing" — the code decides everything below
report.http_status  # 422 / 429 / 500
report.user_action_detail()  # free-form advice text, or None
report.error_category  # "transient" / "capacity" / ...

# Round-trip across a boundary
ErrorReport.from_dict(payload)  # strict inverse of to_dict()

# Retry decision
InferenceErrorCategory.TRANSIENT.is_retryable  # True — only TRANSIENT
```

### File → Purpose

| File | Purpose |
|------|---------|
| `pipelex/base_exceptions.py` | `PipelexError`, `ErrorReport`, `ErrorDomain`, `ValidationErrorItem`, `error_domain_to_http_status()` |
| `pipelex/errors/error_code_declaration.py` | What a class declares: a code, `ErrorCodeSet`, `InheritsCause`, `ABSTRACT_ERROR` |
| `pipelex/errors/error_codes.py` | `ErrorCode`, `error_code_spec()`: what the registries declare about each code, as generated tables |
| `pipelex/errors/foreign_raises.py` | The scan behind the foreign-raise check |
| `pipelex/errors/security_event.py` | The security event: `emit_security_event()`, `emit_security_event_for_run()`, `log_security_event()`, `mark_security_event_emitted()`, and the kind of target each security code refuses |
| `pipelex/errors/security_target.py` | `SecurityTargetKind` and `SecurityTargetClass`, the vocabulary of what a security refusal refused |
| `pipelex/errors/retired_error_pages.py` | The static redirects of the retired per-class error pages |
| `pipelex/errors/registry/pipelex-error-registry.yaml` | The Pipelex error registry, the single source of the `pipelex.` codes; its snapshot, its typed codes (`pipelex_codes.py`) and its pages are generated from it |
| `pipelex/errors/registry/registry_document.py` | The typed model of an MTHDS error registry, and `load_pipelex_error_registry()` |
| `pipelex/pipeline/validation_errors.py` | `build_validation_error_items()` — shared CLI/API structured bundle-validation builder |
| `pipelex/validation_error_types.py` | The closed `error_type` registry — `VALIDATION_ERROR_TYPES`, `PipeValidationErrorType`, `PipeFactoryErrorType`, `ValidationResidualErrorType`, `HintLintErrorType` |
| `pipelex/cogt/exceptions.py` | `CogtError`, `InferenceErrorCategory` |
| `pipelex/cogt/inference/error_classification.py` | Extract — `ProviderErrorMetadata`, `SDKErrorEnvelope`, `UserAction`, `UserActionKind`, per-provider `extract_*_metadata` functions, pure discriminators |
| `pipelex/cogt/inference/error_classify.py` | Classify — `classify_inference_error()`, `ClassificationResult` |
| `pipelex/cogt/inference/error_render.py` | Render — `render_inference_error()`, `InferenceErrorFamily` |
| `pipelex/cogt/inference/provider_name.py` | `ProviderName` enum keying the extract-fn registry |
| `pipelex/providers/*/` | Per-provider inference workers — Layer 0 → 1 classification |
| `pipelex/pipeline/exceptions.py` | `PipelineExecutionError`, `PipeExecutionError` |
| `pipelex/cli/error_handlers.py` | Human CLI Rich panels — `display_error_panel()` |
| `pipelex/cli/agent_cli/commands/agent_output.py` | Agent CLI JSON / markdown delivery |

### Behavior Summary

| Scenario | Behavior |
|----------|----------|
| Rate limit hit | `TRANSIENT` → repeated within the run; `provider.rate_limited`, retryable; transport retry honors `Retry-After` (a provider 429 answers 429 whatever the domain) |
| Quota / billing exhausted | `CAPACITY` → not repeated; `UserAction(CHECK_BILLING)`; `provider.quota_exhausted` → HTTP 500 |
| Bad API key | `CONFIGURATION` → not repeated; `provider.credential_refused`, the operator's → HTTP 500 |
| Model or deployment not found (provider HTTP 404) | Raises a dedicated `*ModelNotFoundError` sibling (`LLMModelNotFoundError`, `ImgGenModelNotFoundError`, `ExtractModelNotFoundError`, `SearchModelNotFoundError`) carrying `model.unavailable`, since a method cannot name a provider's raw model id; operator re-raises `PipeOperatorModelAvailabilityError` |
| Model reference unknown to the deck (a method naming `gpt-5.1`, a mistyped `@alias` or `$preset`) | `ModelChoiceNotFoundError` → `CONFIGURATION` category, but the code `model.unknown`, the method's → **HTTP 422**, and caller-facing under STRICT: the message names the reference and its "Did you mean" suggestions, which are all a caller needs to fix the method. A handle the deck serves only as another type of model is `model.capability_unsupported` |
| The deck's own default or override names a model it does not define | `ModelDeckChoiceUnresolvedError`, naming the deck setting: `pipelex.config.invalid`, the deployment's → HTTP 500, redacted, never the caller's `model.unknown`; a bad override is refused when the deck is built |
| Content-policy violation | `CONTENT` → not repeated; `UserAction(CHANGE_INPUT)`; `model.content_refused` → **HTTP 422** |
| Malformed prompt image / bad prompt parameter | `CONTENT` class-level (`PromptImageFormatError`, `LLMPromptParameterError`, …), each with its own code (`input.file_type_unsupported`, `pipe.prompt_empty`, …) |
| Any other provider **HTTP 400** | `CONTENT` / `CHANGE_INPUT`, but `runtime.unexpected` → HTTP 500: a 400 nothing recognises is most likely a request of ours the provider could not take, and only a content-policy signal makes it the caller's `model.content_refused` |
| Local file extractor raises a builtin (docling, pypdfium2) | `FileNotFoundError` → `input.reference_not_found`, `ValueError` / `RuntimeError` → `input.file_unreadable`, both `CONTENT` → **HTTP 422**; `OSError` → `UNKNOWN`, `runtime.unexpected` (see `_LOCAL_EXTRACT_BY_TYPE_NAME`) |
| A text completion stops at its output limit or context window (`length`, `max_tokens`, `MAX_TOKENS`, an `incomplete` Responses answer at `max_output_tokens`, `model_context_window_exceeded`, `model_length`), with partial or empty text | Every LLM worker reads the stop before returning text and raises `LLMCompletionTruncatedError` → `CONTENT` / `CHANGE_INPUT`, not repeated: `model.output_truncated` at the output limit, which the method's `max_tokens` sets, and `model.context_exceeded` at the context window, both the method's → **HTTP 422**, caller-facing under STRICT. The message names the model, the pipe, the stop value, the output tokens used and the `max_tokens` sent, never the partial text. The error's `truncation_limit` tells the output limit from the context window (`model_context_window_exceeded`, `model_length`), and so does its next step: a higher `max_tokens` or a shorter input for the first, a shorter input, a lower reasoning effort or a larger model for the second, never a higher `max_tokens`. A gateway in non-strict mode passing each provider's own value through the completions shape is read the same way, since the classifier reads the union of the provider vocabularies |
| A text completion refused or stopped by a safety filter (`content_filter`, `refusal`, `content_filtered`, `guardrail_intervened`, Gemini's `SAFETY` and its kin), or a Gemini prompt blocked before any candidate (its `prompt_feedback.block_reason`, whatever its value) | `LLMCompletionRefusedError` → `CONTENT` / `CHANGE_INPUT`, not repeated; `model.content_refused` → **HTTP 422**, caller-facing under STRICT |
| A stop value no provider vocabulary lists | Logged at warning level with the model and the value, and taken as normal: the text is returned. An `incomplete` Responses answer whose reason is missing or unknown is the exception: logged at warning level and taken as a truncation, since the status alone says the text is unfinished |
| An Anthropic structured generation whose `max_tokens` its structured-output timeout lowers | Sent with the lowered limit; logged at warning level when the pipe set the limit, at debug level when it is the model's default; an error the lowered limit can explain, a structured output that failed validation or came back incomplete once the re-asks are spent, or a timeout, keeps its class and category and ends with a sentence saying the limit was lowered and to what; a rate limit, an authentication failure, an overload, a server error or a lost connection carries no such sentence |
| LLM returns schema-mismatched JSON | `instructor` re-asks; if exhausted → the last `pydantic.ValidationError` → `CONTENT` / `CHANGE_INPUT`, `model.output_schema_mismatch` → **HTTP 422** |
| The gateway does not allow the model for this account (`model_not_allowed_error`, HTTP 412) | `CONFIGURATION` / `CHANGE_MODEL`, never repeated; the advice names the model handle; `model.unavailable` → HTTP 500 |
| Connection dropped mid-request | `AMBIGUOUS` → not repeated (outcome unknown); `provider.outcome_unknown`, whose next step says to check the account, since the lost call may have been billed |
| A step names, in an inline model setting, a model the deck neither defines nor names | `ModelNotFoundError`, which the lookup raises with `model.unknown` as the caller's: **HTTP 422**, caller-facing under STRICT, with a `CHANGE_MODEL` next step naming the model as the method wrote it and the type of model the step needs. A model the deck itself names but does not serve (a preset or alias on a backend that is not enabled) keeps the class's `model.unavailable` → HTTP 500, redacted |
| A `PipeParallel` cannot combine its branch results, or a pipe starts without a required input | The caller's own method or request: `pipe.output_multiplicity`, or `input.missing` at the entry pipe and `pipe.input_unresolved` below it → **HTTP 422**, caller-facing under STRICT, with a `CHANGE_INPUT` next step |
| Unknown or ambiguous entry `pipe_code` (a CLI argument, a run request's field, the `--pipe` / `pipe_ref` slice selector of bundle validation) | `EntryPipeNotFoundError` / `EntryPipeAmbiguousError` → `UserAction(CHANGE_INPUT)`; `request.pipe_not_found`, `request.pipe_unspecified` or `request.pipe_ambiguous` → **HTTP 422**, and caller-facing under STRICT. The in-body lookups (`get_optional_pipe` / `get_required_pipe`) keep raising `PipeNotFoundError` / `PipeLibraryError`, whose codes are the method's: a ref written inside a bundle is not the caller's input |
| A template naming a filter or a test that does not exist, found only when it renders | `Jinja2TemplateInvalidError` at the pipe, naming the filter or test and none of the template: `method.template_invalid` → **HTTP 422**, caller-facing under STRICT, for a method's `PipeCondition` expression, `PipeLLM` prompt or `PipeDocGen` template, and `runtime.unexpected` for one of Pipelex's own templates |
| A URL or a storage key refused by the SSRF guard or the run's read scope | A `security.*` code saying whose the URL was: `security.input_url_refused` for one of the run's inputs, the default when the guard cannot tell, `security.method_url_refused` for one the method names and for a read refused inside a step, whose inputs were authorized when they were normalized, both → **HTTP 422**, and `security.provider_url_refused` for one in a model's generated answer, the runtime's → HTTP 500; a traversal in a storage key the caller supplied is `security.input_path_refused`, which `PipelineInputContentError` takes from its cause |
| Any refusal coded in the `security.` or `pipelex.security.` family | The run fails under that code, and the deployment logs one security event on `pipelex.errors.security_event`, naming the code, its domain, the kind and class of target refused, the run, the request and the run's extras, never the target or any content; a refusal crossing several boundaries is logged once |
| A method of the host's own library directories refuses to load | `HostLibraryLoadRefusalError`, `pipelex.config.invalid` → HTTP 500, its message withheld under STRICT; the same refusal in the caller's own content stays the caller's verdict |
| Wrapper exception (no own category) | Takes its cause's code, and its classification via enrichment |
| A pipe fails during a run | `PipeRouterError` → `PipelineExecutionError`, both reporting the root fault's `code` and `error_type` and its own message prefixed with `Pipe '<code>' failed (<path>): `; the classification comes from the chain |
| A pipe raises a non-Pipelex exception | Located as a `PipelexUnexpectedError` whose message names the original class; redacted under STRICT |
| Failure on a distributed worker | `ErrorReport` recovered from the transport's serialized details — same classification as local |
| Worker exception with no `ErrorReport` | Synthesized fallback report — `runtime.unexpected` |

---

## Next Steps

- [Pipe Routing & Execution](./pipe-routing-and-execution.md) — the layer model errors rise through
- [Runtime Bridge & Transport](./runtime-bridge-and-transport.md) — the process boundary the error bridge spans (the per-backend error converters live in the host-runtime plugins)
- [Inference Configuration](../configuration/config-technical/inference-config.md) — `transport_max_retries` and the Tier 1 retry policy
- [Agent CLI](../tools/cli/agent-cli.md) — the JSON / markdown error contract
