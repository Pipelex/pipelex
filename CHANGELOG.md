# Changelog

## [Unreleased]

This cycle reworks **cost reporting** so it survives distributed execution and stops leaking. Cost now rides on the run result instead of a side buffer: a multi-worker Temporal run aggregates usage from every worker into a single end-of-run report, the success-path registry leak is gone by removal, and a new `--costs` switch decouples cost collection from `--graph`. It also extracts the **framework-agnostic runtime bridge** so any host runtime — not just Mistral Workflows — can embed Pipelex through one boundary.

### Added

- **`--costs` / `--no-costs` (default on).** `pipelex run pipe|method|bundle` gains a dedicated cost switch that emits usage tracing events and renders the end-of-run cost report. It rides the shared trace-event transport independently of `--graph`, so `--no-graph --costs` reports cost without building a graph and `--graph --no-costs` builds a graph with no cost report. It replaces the removed `--cost-report` (see Changed).

- **Distributed cost reporting.** In Temporal mode, usage emitted from inference activities running on separate worker processes is now aggregated into a single cost report at the submitter. Usage is assembled from the trace-event stream onto `PipeOutput` in both direct and Temporal execution, so a cross-worker run reports its true total — previously cross-worker usage was emitted but never rendered into a report.

- **`tokens_usages` on `PipeOutput`.** New `tokens_usages: list[AnyTokensUsage] | None` and `usage_assembly_error: str | None` fields, mirroring `graph_spec` / `graph_assembly_error`. Cost is now part of the run result and is exposed automatically wherever a `PipeOutput` is returned, including the Pipelex API response. Render it with `CostRegistry.generate_report(tokens_usages=...)`.

- **`--mock-inference`.** A LIVE run that fakes AI calls at the inference leaf with reportable synthetic usage: operators dispatch real activities (exercising the true distributed path) but no tokens are billed, so distributed cost reporting can be validated cheaply and deterministically. Mutually exclusive with `--dry-run`. It covers the LLM leaf; image-generation / extract / search under `--mock-inference` fail loud with `MockInferenceUnsupportedError` (pointing at `--dry-run`) rather than silently calling the real provider.

- **Cost report in the agent CLI JSON.** `pipelex-agent run ... --with-memory` attaches a best-effort structured `cost_report` (`{total_cost, by_model}`, real USD) to its JSON envelope when the run did reportable work and summary aggregation succeeds — treat it as optional (absent for dry runs, `--no-costs`, the API-runner path, or an aggregation failure). The agent surface stays JSON-only — no Rich table on stderr; compact mode is unchanged.

### Changed

- **Mistral Workflows integration extracted into a dedicated package.** The optional `pipelex[mistralai-workflows]` extra and the `pipelex.plugins.mistralai_workflows.*` modules have been removed from `pipelex`. The Mistral Workflows integration now ships separately as its own package — coming soon; install and import details will follow once it publishes. The framework-agnostic runtime-bridge core (boundary types, `run_pipe_via_bridge`, `PipelexExecutionMode`, `ensure_pipelex_booted`) has been promoted from `pipelex.plugins.mistralai_workflows.*` to `pipelex.runtime_bridge.*` so any host runtime — not just Mistral Workflows — can embed Pipelex. No behavior changes; activities, boundary types, and execution modes are identical.

- **`--cost-report` removed, folded into `--costs`.** Breaking: `--cost-report/--no-cost-report` is gone from `run pipe|method|bundle`. Use `--costs` (default on) instead.

- **Cost reporting is event-sourced; the submitter-side `UsageRegistry` is removed.** The cost report is rendered from `PipeOutput.tokens_usages`, not from an in-process registry. `ReportingProtocol` (and `ReportingNoOp`) no longer expose `open_registry` / `close_registry` / `generate_report` / `inject_tokens_usages`, and the `UsageRegistry` model is gone. Embedders that rendered cost via `get_report_delegate().generate_report()` must render from the returned `pipe_output.tokens_usages` instead.

- **`is_log_costs_to_console` now defaults `true`.** With `--costs` on, the CLI prints the cost table at end of run by default (parity with `--graph` producing visible output). Per-inference-job console logging is removed — the report renders once at the end, not per call. Library embedders who don't want console output set it `false`.

- **Dry runs never emit a cost report; free-model runs still do.** Suppression keys on whether the run did reportable work (any tokens or any cost), not on total cost alone: a dry run (zero tokens, zero cost) is suppressed, while a real run on a free / zero-price model (e.g. Ollama) still reports its token usage with a zero total.

- **Temporal `act_assemble_graph` renamed to `act_assemble_tracing`.** It now assembles both the graph (`GraphSpec`) and usage (`tokens_usages`) from a single trace-event read, gated per concern by the run's `--graph` / `--costs` flags.

### Fixed

- **Docs deploy crashed on a fresh runner with `InferenceSetupRequiredError`.** `pipelex-dev generate-error-pages` (a prerequisite of every `docs-*` make target) bootstrapped Pipelex with `needs_inference=True`, so on a CI runner with the gateway enabled but no on-disk service config it hit the first-run inference-setup gate and exited non-zero — breaking the `Deploy docs` workflow on `main`. The command only introspects `PipelexError` subclasses to write markdown and never calls inference, so it now bootstraps with `needs_inference=False`.

- **`UsageRegistry` success-path leak.** The per-run cost registry was opened during run setup but closed only on the failure path, so every successful run leaked its registry — and in a long-lived process (e.g. the Pipelex API) reusing a `pipeline_run_id` could collide on the orphaned registry. The registry is removed entirely, so the leak is structurally impossible.

- **Temporal silent-hang fail-safe.** A pipelex domain error raised *inline* in workflow code — never dispatched through an activity — was neither an `ActivityError` nor an `ApplicationError`, so Temporal treated it as a workflow-task failure and retried it indefinitely: a silent, resource-burning hang that only surfaced (as a generic timeout) after the workflow execution timeout. `WfPipeRouter` and `WfPipeRun` now end their boundary handling with a `PipelexError` catch-all that converts a genuine inline error to a terminal, classified failure (the parent also still fires the FAILED webhook), and the worker registers `PipelexError` in `workflow_failure_exception_types` as a backstop so any uncaught domain error fails the workflow terminally instead of hanging. Scoped to domain errors only — transient Temporal/infra errors keep their (correct) task-retry behavior.

- **`PipeSearch` on Temporal no longer hangs.** Web search was the only inference operator that ran its leaf inline instead of through the `ContentGenerator` seam, so it had no Temporal activity. Run through the Temporal path, a search step executed its real HTTP call inside the workflow event loop, and on failure raised a raw `SearchJobFailureError` (neither an `ActivityError` nor a `WorkflowExecutionError`) that Temporal treated as a workflow-task failure and retried forever — the submitter hung instead of getting a result. Even on success it was replay-unsafe (the search re-ran on every workflow replay). `PipeSearch` now dispatches its leaf through new `act_search_gen_sourced_answer` / `act_search_gen_structured` activities like every other operator: results are recorded in workflow history (replay-safe) and failures cross the workflow boundary as a terminal `WorkflowExecutionError` carrying the structured `ErrorReport` — identical classification to the local path. A `runner-search` worker scope and per-activity routing entries are available for split deployments.

- **Bundle validation no longer leaks nested controller sub-pipes to Temporal.** With Temporal enabled, the in-process dry-run sweep (`BundleValidator`) ran the top-level pipe in-process but dispatched every *nested* controller sub-pipe through the hub-default router — the Temporal router — turning a no-cost dry run into real top-level workflow dispatches. A standalone `PipeBatch` / `PipeParallel` swept directly fanned out N concurrent same-id top-level dispatches and collided (`WorkflowAlreadyStartedError`), surfacing as **HTTP 422** on the runner's `/validate` route; other shapes silently round-tripped Temporal. The sweep now scopes its in-process router for the whole sweep (mirroring the DIRECT-mode runtime bridge), so nested controllers resolve the in-process router and validation stays fully in-process regardless of the configured backend.

## [v0.31.0] - 2026-06-04

This release hardens Pipelex at its edges. The headliners: a full **error-handling overhaul** that gives every error a stable, RFC 7807-shaped identity and carries it all the way out to webhooks and external surfaces; **lenient validation with pipe signatures**, so you can sketch and dry-run a whole pipeline top-down before a single pipe is implemented; and a first, **experimental cut of CSV tabular support** for reading and writing typed lists straight from `.csv`.

### Added

- **Stable error identity (RFC 7807).** Every `PipelexError` now exposes `title()` and a stable `type_uri()` — a real, dereferenceable `https://docs.pipelex.com/latest/errors/<error>/` URL — and every `ErrorReport` carries both as populated fields, so consumers read `report.title` / `report.type_uri` directly instead of humanizing class names. `ErrorReport.to_problem_document()` renders an `application/problem+json` document with no web-framework dependency, and a new `DisclosureMode` (`VERBOSE` / `STRICT`) controls how much leaks onto external surfaces: `STRICT` drops provider/model attribution and redacts any message that wasn't authored to be caller-facing, keeping only the stable identifiers.

- **Structured error payloads on failure webhooks.** When a run fails, the delivery webhook now includes an `error` object — the full `ErrorReport` as a dict — so receivers can rehydrate it with `ErrorReport.from_dict(...)`, render an RFC 7807 response, or route on `error_domain` / `retryable`. Applies to both Temporal and direct execution. A `WebhookTarget.payload` that collides with a Pipelex-reserved key (`pipeline_run_id`, `status`, `result_url`, `error`) is now rejected at construction.

- **Per-class error reference pages.** Every `PipelexError` subclass now has a generated reference page under `docs/errors/`, surfaced in the docs site as "Error Reference" — so a `type_uri` dereferences straight to a populated page. Regenerate with the new `pipelex-dev generate-error-pages` command (`make generate-error-pages`, alias `make gep`); pages a maintainer claims with a `<!-- pipelex:authored -->` marker are preserved across runs.

- **`request_id` on `JobMetadata`.** An optional caller-supplied request id, threaded through every activity / workflow / submitter hop and into the Temporal log context. Set it at dispatch with `pipeline_run_setup(..., request_id="...")` and read it back off `job_metadata.request_id`.

- **`PipeSignature` — contract-only pipes for top-down design.** A new pipe type (`type = "PipeSignature"`) declares a pipe's `inputs`, `output`, and `description` with no implementation, so an author or agent can sketch a complete pipeline before committing to the operator that will eventually do the work. At dry-run time a signature mints a mock output matching its declared type and multiplicity; at runtime it raises `PipeSignatureNotExecutableError`. The optional `signature_for` field hints which pipe type the stub stands in for. See [Signature Pipes](https://docs.pipelex.com/latest/building-methods/pipes/signature-pipes/).

- **Lenient validation with `--allow-signatures`.** `pipelex validate pipe|bundle` and every `pipelex-agent validate` subcommand take `--allow-signatures` (default off) to dry-run a pipeline that still contains `PipeSignature` stubs. Strict by default: without the flag, validation refuses any pipeline whose dependency graph reaches a signature and raises `SignaturesNotAllowedError`, reporting every reachable stub plus the controller chain that leads to it — so you know exactly which pipes are still placeholders.

- **CSV tabular support (experimental).** Read a `.csv` straight into a typed `ListContent[YourConcept]`: point an `inputs.json` reference at a `.csv` whose column headers match the concept's field names, and each row becomes an instance, with cells coerced via Pydantic (`birth_year` → `int`, ISO dates → `date`; an empty cell becomes `None`, so the field must be optional). Write a flat-list output back out with the new `--save-csv <path>` flag on `pipelex run pipe|bundle|method`. v1 is deliberately narrow — local file paths only (remote URLs with a tabular suffix are rejected), the row concept must be flat (scalar fields only; a nested/list/concept-typed field is rejected with a clear error naming it), and `.xlsx` is recognized but routed to a "needs `pipelex[tabular]`" message (the Excel backend isn't built yet). See the [CSV Input & Output guide](https://docs.pipelex.com/latest/building-methods/pipes/csv-input-and-output/).

- **`--traceback` CLI flag for full stack traces.** By default CLI commands print a friendly one-line error; `--traceback` also prints the Rich-rendered stack trace before it. It's position-agnostic — `pipelex run --traceback pipe ...` and `pipelex run pipe ... --traceback` both work.

- **Test tooling for hanging runs.** New `make agent-test-debug` (alias `make atd`) runs the suite with upfront stale-process cleanup, an outer wall-clock timeout, and live per-test logging — for when `make agent-test` hangs or fails opaquely. Paired with a debugging playbook at `docs/agents/debugging-hanging-pytest-runs.md`.

### Changed

- **`ErrorReport` is now a frozen Pydantic `BaseModel`** (was a frozen Pydantic dataclass) — still immutable and still round-trips through `to_dict()` / `from_dict()`, but an attempted mutation now raises `pydantic.ValidationError` instead of `dataclasses.FrozenInstanceError`. Relatedly, **`recover_error_report()` is now total**: it always returns an `ErrorReport`, synthesizing one from the new `UnrecoverableWorkflowFailureError` (surfacing the deepest worker-side cause) when a Temporal failure carries no embedded report — callers no longer branch on `None`.

- **Dry-run and validation consolidated into `BundleValidator`.** The standalone `dry_run_pipe` / `dry_run_pipes` functions and the modules `pipelex/pipe_run/dry_run.py`, `dry_run_with_graph.py`, and `dry_pipe_router.py` are gone; their work now lives in `BundleValidator`, and `validate_bundle` / `BundleValidator` gained the `allow_signatures: bool = False` flag (strict by default). Validation ordering and outputs are unchanged — only the import surface moved. Callers importing from `pipelex.pipe_run.dry_run` must switch to `BundleValidator`.

- **`validated_pipes` now identifies every pipe by its qualified `pipe_ref` (`domain.code`).** Previously `validate pipe` reported the bare code while `validate bundle` / `validate all` reported the namespaced ref, so the same pipe could appear under two identities depending on which command produced it. Every validate surface now emits the qualified ref, which can't collide across domains. Consumers that parsed `pipe_code` expecting the bare form (e.g. the MTHDS skills) must match on the namespaced ref.

- **Gemini deck refresh.** Google shut down `gemini-3-pro-preview`, so the `gemini-3.0-pro` handle is removed across the `google`, `portkey`, and `openrouter` backends (and the test-profile collections) — use `gemini-3.1-pro` (→ `gemini-3.1-pro-preview`) instead, now registered on `portkey` too for parity with `google`. The `gemini-3.0-flash-preview` handle is renamed to `gemini-3.0-flash`. The Pipelex Gateway lists models from its own remote config, so drop `gemini-3.0-pro` there separately.

- **Filesystem path helpers moved to `pathlib.Path`.** Helpers in `pipelex.tools.misc.file_utils` and `pipelex.tools.misc.json_utils` (`save_text_to_path`, `load_json_from_path`, `load_binary`, `copy_file`, `ensure_directory_exists`, `get_incremental_file_path`, and the rest) now take and return `Path` instead of `str`; path handling is `Path`-based throughout `pipelex/`, converting to/from `str` only at boundaries. Callers passing bare strings must wrap them with `Path(...)`.

- **Safer Temporal defaults.** `[temporal.search_attributes]` now ships `enabled = false` (opt in per env) so a local boot can't fail on the unregistered-attribute check, and the default `[temporal.queue_options.temporal_task_queue]` block is removed to avoid leaving an orphan overlay when a queue is renamed.

- **`teardown_current_library()` renamed to `clear_current_library()`** in `pipelex.hub`, pairing it cleanly with `set_current_library()`.

- **Dev tooling: `pyright` bumped `1.1.408 → 1.1.410`** (drove two behavior-neutral internal adjustments).

### Fixed

- **The generated MTHDS schema now requires `type` on every pipe.** In the schema consumed by `plxt` lint and the VS Code Taplo LSP, each pipe blueprint variant declared `type` with a literal default — so it was optional, and because the Draft-4 export drops the union discriminator, a pipe table written without `type` matched several `oneOf` branches at once and was rejected with an ambiguous multi-match (worse, a type-less table carrying fields unique to one variant validated silently). `type` is now required on every variant, so a type-less pipe table fails with a clear "missing type" and a typed table resolves to exactly one variant. The patched set derives from `PipeBlueprintUnion`, so new pipe types are covered automatically. Regenerate with `pipelex-dev generate-mthds-schema`.

- **`InputStuffSpecsFactoryError` was shadowed by a duplicate class definition.** `input_stuff_specs_factory.py` declared a local class with the same name as the canonical one in `exceptions.py`, leaving two distinct class objects in play so an `except` on one would miss the other. Consolidated to the single canonical class.

### Security

- **urllib3 floor `>=2.7.0`** to patch two high-severity issues: CVE-2026-44431 (GHSA-qccp-gfcp-xxvc) forwards sensitive headers across origins on proxied low-level redirects, and CVE-2026-44432 (GHSA-mf9v-mfxr-j63j) bypasses the decompression-bomb safeguards in parts of the streaming API. Floor added to the runtime `dependencies`.
- **pymdown-extensions floor `>=10.21.3`** to patch CVE-2026-46338 (GHSA-62q4-447f-wv8h, medium): a regression in `pymdownx.snippets` reintroduced the sibling-prefix path-traversal bypass despite `restrict_base_path`. Docs-only; floor added to the `docs` extra.
- **idna floor `>=3.15`** (lockfile resolves to 3.18) to patch CVE-2026-45409 (GHSA-65pc-fj4g-8rjx, medium): specially crafted inputs to `idna.encode()` could bypass the CVE-2024-3651 fix. Floor added to the runtime `dependencies`.
- **Proactive floor bumps in the same hardening pass**, past known-vulnerable releases: pillow `>=12.1.1`, protobuf `>=6.33.5`, python-dotenv `>=1.2.2`, requests `>=2.33.0` (runtime); aiohttp `>=3.12.14` (`temporal` extra); Pygments `>=2.20.0` (`docs` extra).

## [v0.30.3] - 2026-05-28

### Added

- **`claude-4.8-opus` model** added to the `anthropic` and `bedrock` backends. Adaptive thinking mode, supports text / images / pdf in and structured outputs, `max_prompt_images = 100`, `max_tokens = 128000`, costs `{ input = 5.0, output = 25.0 }` per million tokens. Carries the `temperature_unsupported` constraint like `claude-4.7-opus`. Also available via the Pipelex Gateway.

## [v0.30.2] - 2026-05-26

### Changed

- **`pipelex-agent` markdown error envelope no longer includes the `## Error source` stack-frame section.** Markdown is the agent / human-facing channel; internal frames like `LibraryError @ pipelex/libraries/library.py:140` are noise for an LLM trying to fix a `.mthds` file and forced every consumer (e.g. the `mthds-plugins` validate hook) to strip them. The `error_source` field remains in the JSON envelope (`--error-format json`) untouched for programmatic consumers — same shape, same cause-chain ordering — so any tooling that parses JSON keeps the full diagnostic surface. The `## Details` section (which carries `error_domain` and other structured fields) is unchanged. No change to error categorization, `error_domain` values, message wording, or stdout/stderr routing.

## [v0.30.1] - 2026-05-26

### Fixed

- **`pipelex-agent` now silences every Python logger on stderr regardless of user TOML.** The agent CLI is machine-consumed: stdout is reserved for the structured success envelope (JSON / markdown) and stderr for the structured error envelope. Free-floating `log.*` calls — a `log.debug` from `telemetry_factory.py`, a `log.warning` from `validation_error_categorizer.py`, or an INFO/WARNING line from any third-party dep (`anthropic`, `httpx`, `botocore`, `openai`, anything a transitive dep configures) — would corrupt the stderr channel for downstream parsers (`mthds-js`'s `PipelexRunner` doing `JSON.parse(stderr)` on the validate hook). Two layers, defense-in-depth:
  - **Layer 1 — pin pipelex's own logs off via config.** `make_pipelex_for_agent_cli` injects `config_overrides` into `Pipelex.make()` that pin `default_log_level = OFF` and `package_log_levels.pipelex = OFF` from the very first `log.configure` call. A user setting `[pipelex.log_config.package_log_levels] pipelex = "DEBUG"` in `~/.pipelex/pipelex.toml` can no longer leak its own DEBUG/INFO/WARNING lines.
  - **Layer 2 — process-global cutoff that covers every logger.** New `silence_logging_for_agent_cli()` calls `logging.disable(sys.maxsize)` — a process-global threshold checked inside `Logger.isEnabledFor` BEFORE any per-logger level. No record gets created for any logger at any level (including custom levels above `CRITICAL`), regardless of which package emits or what level the user configured. Wired into the Typer `app_callback` so every subcommand — including `init` and `accept-gateway-terms`, which bypass `make_pipelex_for_agent_cli` — silences logging before any command body runs; idempotent per-call invocations remain inside `make_pipelex_for_agent_cli` and `agent_doctor_cmd` as belt-and-braces for direct library callers.

  A new e2e regression test pins the contract by setting `anthropic`, `httpx`, `botocore`, `openai` to `DEBUG` in the user TOML and asserting both stdout and stderr stay clean.

### Changed

- **`pipelex-agent` no longer accepts `--log-level`.** Log suppression is unconditional by design — there is no verbosity setting on the agent CLI. The `log_level` parameter is removed from `make_pipelex_for_agent_cli()` and `apply_agent_cli_output_discipline()`, and the corresponding `ctx.obj["log_level"]` plumbing is gone from every caller. For verbose debugging, use the human `pipelex` CLI, which honors the user's TOML log config.

- **`pipelex/cli/commands/doctor_cmd.py::setup_doctor_runtime` now `deep_update`s `log_config_overrides` into the loaded config** (was a flat-merge that silently replaced nested dicts like `package_log_levels`). With the flat merge, pinning `package_log_levels.pipelex = OFF` for the agent doctor path would have wiped out all the third-party package levels (`anthropic`, `asyncio`, `botocore`, ...) shipped in the default config. The deep merge preserves them.

- **Removed `ctx: typer.Context` from 8 agent CLI commands that no longer used it.** `validate/{pipe,bundle,method}_cmd.py`, `inputs/{pipe,bundle,method}_cmd.py`, `models_cmd.py`, `check_model_cmd.py` had `ctx.obj["log_level"]` as their only ctx usage; with `--log-level` gone, the parameter became dead weight. The `run/` commands keep `ctx` because they still read `ctx.obj["runner"]`. Test callers (and the now-unused `agent_ctx` conftest fixture) updated to match.

## [v0.30.0] - 2026-05-25

### Fixed

- **`console_log_target` package default is now `stderr` (was `stdout`).** Logs now stay off the data channel by default, matching the intent of PR #452 ("default to stderr for outputs happening before initialization"). Downstream tooling that parses `pipelex` / `pipelex-agent` stdout as JSON (e.g. `mthds-js`'s `PipelexRunner`) is no longer at risk of stdout pollution from package-level logs — the bug was latent for stock installs because the agent-CLI JSON paths happen not to log at INFO+, but surfaced for anyone who raised `package_log_levels.pipelex` to DEBUG or added a setup-time log on the command path. The same flip is applied to the kit template (`pipelex/kit/configs/pipelex.toml`) that `pipelex init` copies to `~/.pipelex/`. **Note:** `console_print_target` is intentionally left at `stdout` — the main `pipelex` CLI emits human-facing tables (`show backends`, `show models`, `which`, `doctor`) via that channel, and downstream piping (`pipelex show backends > out.txt`) must keep working.

- **`pipelex-agent` now pins both console targets to `stderr` regardless of user config.** `make_pipelex_for_agent_cli` injects `config_overrides` into `Pipelex.make()` that force `console_log_target = "stderr"` and `console_print_target = "stderr"` from the very first log/print fired during init, so a user override of either knob in `~/.pipelex/pipelex.toml` can no longer leak diagnostics onto the agent CLI's JSON data channel. Defense-in-depth post-init calls to `log.redirect_to_stderr()` and `get_pipelex_hub().set_console_print_target(STDERR)` remain. A new adversarial E2E test (`tests/e2e/agent_cli/test_stdout_is_clean_json.py::test_models_json_stdout_resists_user_targets_override_to_stdout`) pins the contract by overriding both targets to `stdout` and `package_log_levels.pipelex` to `DEBUG` and asserting `json.loads(stdout)` still parses.

## [v0.29.1] - 2026-05-21

### Fixed

- **`pipelex run` now prints the aggregated cost table when `[pipelex.reporting_config].is_log_costs_to_console = true`, with `--cost-report/--no-cost-report` to override per invocation.** The `cost-tracking.md` and `reporting-config.md` docs both promised a summary cost table at the end of a CLI run, but `pipelex/cli/commands/run/_run_core.py` never called `get_report_delegate().generate_report()` — the flag only triggered `log.verbose(...)` lines per inference job, which the default `INFO` log level swallows, so the table never appeared. The CLI now calls `generate_report()` after a successful run when either `is_log_costs_to_console` or `is_generate_cost_report_file_enabled` is true, so the Rich table (one row per model, plus a totals row) prints right before the "✓ Pipeline execution completed successfully" recap — and the CSV export branch finally fires too. The new `--cost-report/--no-cost-report` tri-state flag (default unset → use config) lets you force the cost table on for a single invocation (`--cost-report`) or skip reporting entirely — no Rich table **and** no CSV file (`--no-cost-report`) — without touching `.pipelex/pipelex.toml`. Applies to `pipelex run bundle`, `pipelex run pipe`, and `pipelex run method`; works in dry-run mode as well (synthetic usage rows).

## [v0.29.0] - 2026-05-20

### Added

- **`gemini-3.5-flash` model** added to the `google` backend. Adaptive thinking mode, supports text / images / pdf in and structured outputs, `max_prompt_images = 3000`, costs `{ input = 1.5, output = 9.0 }` per million tokens.

- **New `PipeStructure` operator** that turns text into a structured concept via a single LLM call. Takes one `Text`-compatible input (or a domain concept that `refines = "Text"`), produces any structured output with the usual multiplicity options (`Foo`, `Foo[]`, `Foo[N]`). Useful whenever the source text comes from a PDF extraction, a search result, an upstream pipe, or any non-LLM origin. Documented at [building-methods/pipes/pipe-operators/PipeStructure.md](building-methods/pipes/pipe-operators/PipeStructure.md).

- **Custom search attributes on the Temporal namespace, with a strict prerequisite at worker boot.** Pipelex sets five custom Keyword search attributes on every workflow start — `PipeCode`, `PipelineRunId`, `SessionId`, `UserId`, `DomainCode` — so the Temporal dashboard can filter, group, and audit workflows by their actual semantic identity rather than by opaque workflow ids. A real Temporal cluster rejects every `StartWorkflowExecution` RPC that references an unregistered attribute, so the check at worker boot is a hard fail (raises `SearchAttributeRegistrationError`) on a reachable namespace — the previous "warn and continue" framing was dishonest because workflows would then fail at every dispatch with a much less actionable error. The exception message embeds both the `pipelex setup-temporal-namespace` invocation and the equivalent raw `temporal operator search-attribute create` command. `RPCError` (control-plane unreachable) stays a soft fail; the in-process test server is registered up front by the integration conftest. Documented at [distributed-execution/cluster-setup.md](distributed-execution/cluster-setup.md).

- **`[temporal.search_attributes]` config block** — master `enabled` toggle and an `attributes` subset selector for the five built-ins. `enabled = false` skips both the worker-boot registration check and the per-workflow attribute attachment (use this when the namespace policy is owned by a third party who will not register attributes). The validator rejects unknown attribute names so typos like `"PipelineRunID"` surface at config load instead of silently producing no attribute. The Pydantic model lives in `pipelex/temporal/config_temporal.py` so the validator can reference `BUILTIN_SEARCH_ATTRIBUTES` without pulling `temporalio` into the config-load path.

- **`pipelex setup-temporal-namespace` CLI command** — wraps `OperatorService.AddSearchAttributes` against the configured server profile so operators don't need a separate `temporal` / `tcld` install for the common case. Reads the same `[temporal.search_attributes].attributes` list and `[temporal.temporal_config]` block the worker uses, so the names registered here can never drift from the names the worker will dispatch with. `--dry-run` prints the equivalent raw `temporal operator search-attribute create` command without executing. `--server <profile>` targets a non-default server profile. On Temporal Cloud namespaces where the worker API key lacks `OperatorService.AddSearchAttributes` permission, the command catches `RPCError(PERMISSION_DENIED)` and prints the fallback runbook (raw `temporal` CLI command, `tcld` for Cloud, Cloud UI link).

- **Per-workflow static summary and details in the Temporal dashboard.** Every top-level workflow start now sets `static_summary` (200-byte Markdown like `translate_doc — Translate a document from English to French`) and `static_details` (Markdown table of pipe code, domain, pipeline run id, user, session, optional library crate, optional inputs). Every `workflow.execute_activity(...)` call sets a per-call `summary=` carrying the call-specific meaning (`LLM text · pipe=translate_doc · model=gpt-4o`, `Img gen N× · pipe=cover · model=fal-flux-dev · n=3`, etc.). The formatting policy lives in the new `pipelex/temporal/tprl/observability.py` module.

- **Documented `render_js` and `include_raw_html` on `PipeExtract`.** Both fields were already shipping on `PipeExtractBlueprint`; only docs were missing. `render_js = true` asks the extraction backend to render JavaScript before fetching web-page content; `include_raw_html = true` populates each extracted `Page`'s `raw_html` field with the fetched HTML. Added to [building-methods/pipes/pipe-operators/PipeExtract.md](building-methods/pipes/pipe-operators/PipeExtract.md).

- **Documented `XHIGH` value on `ReasoningEffort`.** The enum already shipped seven levels; the `under-the-hood/reasoning-controls.md` table listed only six. `XHIGH` sits between `HIGH` and `MAX` and maps to provider-specific xhigh values where supported.

- **Bounded fan-out concurrency for `PipeBatch`.** A `PipeBatch` over many items no longer spawns every branch — every coroutine, every deep-copied working memory, every inference call — at once. Branches now run in bounded chunks driven by the new `[pipelex.pipeline_execution_config]` setting `max_concurrency` (default `8`; set to the literal `"unbounded"` for unbounded fan-out, the previous behavior). This is the resilience-without-Temporal pillar: it keeps a large workload (one pipe over thousands of documents) from overwhelming asyncio, memory, and provider rate limits. Results still preserve input order, and a branch failure still propagates (first error by input index wins). When a batch fans out over a large number of items, an advisory log line points at the Temporal track as the durable, rate-limited path. `PipeParallel`, which fans over a fixed pipe-defined branch set, is unchanged.

- **Authoritative `error_domain` → HTTP-status mapping.** `pipelex/base_exceptions.py` now owns the mapping that downstream HTTP APIs (`pipelex-relay`, `pipelex-back-office`) need to render an `ErrorReport` as an HTTP response: `error_domain_to_http_status()` (the pure domain table — `INPUT` → 422, `CONFIG`/`RUNTIME`/unknown → 500) and the `ErrorReport.http_status` property, which adds a provider-429 passthrough so the API can emit a `Retry-After` header from `provider_metadata.retry_after_seconds`. The library stays HTTP-agnostic — no web-framework dependency, just the mapping table; downstream FastAPI handlers call the helper instead of reinventing the contract.

- **Category-aware error boundary on Temporal activities.** Every in-scope Temporal activity is now decorated with `@convert_pipelex_errors` (new module `pipelex/temporal/tprl/activity_error_boundary.py`), which converts a `PipelexError` raised inside the activity into a `TemporalError` at the activity boundary. This packs the structured `ErrorReport` into `ApplicationError.details` and derives `non_retryable` from the error's `InferenceErrorCategory` — so the workflow-side `TemporalError.from_app_error` keeps `error_category`, `user_action`, `model` and `provider` instead of landing in its `error_report is None` fallback, and a non-retryable `CogtError` (`CONFIGURATION`, `CONTENT`, `CAPACITY`) is no longer retried. Resilience for inference failures lives entirely on the Temporal track — direct (non-Temporal) execution makes a single pipeline-level attempt. `act_assemble_graph` is deliberately left unwired — it is best-effort observability that swallows every failure and degrades to `None`. As part of this, `TemporalError._log_critical` / `_log_error` now select `activity_log` vs `workflow_log` based on `activity.in_activity()`, since `workflow.logger` raises `_NotInWorkflowEventLoopError` outside a workflow event loop.

- **`AMBIGUOUS` inference-error category for outcome-uncertain failures.** New `InferenceErrorCategory.AMBIGUOUS` for failures where the error type is known but the outcome is not — the operation may or may not have committed (e.g. a connection dropped mid-request). It is non-retryable, like `CONFIGURATION` / `CONTENT` / `CAPACITY`, but semantically distinct from `UNKNOWN`, which means the error could not be classified at all. The `azure_rest` image-generation worker now raises `AMBIGUOUS` for mid-request transport failures — `ReadError` / `WriteError` / `RemoteProtocolError` and `ReadTimeout` / `WriteTimeout` — so Temporal does not auto-retry a non-idempotent, billable image submit whose outcome is unknown; pre-request failures (`ConnectError` / `ConnectTimeout` / `PoolTimeout`) stay `TRANSIENT` and retryable.

- **Explicit, uniform Tier 1 transport retry across every inference worker.** A new `[cogt]` setting `transport_max_retries` (default `2`) is now wired explicitly into every inference SDK client factory — Anthropic, OpenAI / Azure OpenAI, the Portkey-backed gateway clients, Mistral, and Google — instead of each factory silently inheriting whatever retry posture its SDK happens to default to. The two SDK families that default to *no* transport retry are brought up to the same floor: the Mistral client gets a bounded-backoff `RetryConfig` (`retry_connection_errors=True`) and the Google GenAI client gets `HttpOptions(retry_options=...)`. The genuinely SDK-less path — the `azure_rest` image-generation worker, which talks to Azure over raw `httpx` — gets a `tenacity`-based transport-retry wrapper (new module `pipelex/cogt/inference/transport_retry.py`) that retries connection failures and transient HTTP statuses (408/409/429/5xx) and honors `Retry-After`. When no `Retry-After` header is present, the fallback backoff uses full jitter (`wait_random_exponential`) so a burst of failures retried together does not re-fire in lockstep. On a non-idempotent submit-style POST it narrows the retry to failures that prove the server did no billable work — a request that was never delivered, or a 408/429 rejection — withholding an ambiguous 5xx, a 409 conflict, and a post-delivery timeout such as a `ReadTimeout`. Transport retry is now a deliberate, configured, uniform policy rather than a per-provider accident. This is "Tier 1" of the retry model — direct (non-Temporal) execution still makes a single pipeline-level attempt on top of this transport floor; durable resilience remains the Temporal track. (The `portkey-ai` SDK does not expose a retry knob — it carries its own internal retry — so the gateway's `AsyncPortkey` client is left as-is; only its underlying OpenAI clients are wired.)

- **Offline mode for Pipelex Gateway setup and dry-run.** When the gateway is enabled but the remote config service is temporarily unreachable, Pipelex now falls back to a previously primed on-disk cache (`~/.pipelex/cache/remote_config.json`, schema-versioned) instead of failing setup outright. Dry-run, validation, and `pipelex-agent run bundle --dry-run` complete normally; only the actual inference call still needs the network at runtime. The cache is primed on every successful fetch and on `pipelex init` while online. When the gateway is disabled (BYOK), no remote fetch is attempted at all — setup is fully offline. A new `RemoteConfigStaleWarning` (`UserWarning`) is emitted whenever stale cache is in use; the agent CLI surfaces it on the JSON envelope as `warnings: [{"type": "RemoteConfigStale", ...}]`. Telemetry is suppressed (no-op) when running on a cached config so stale model identities don't pollute metrics. The doc/fixture generators (`pipelex-dev update-gateway-models`, `preprocess_test_models_cmd`) refuse the cache fallback via a new `require_fresh=True` flag, so committed reference docs and test fixtures never bake in stale data.

- **`GatewayUnknownModelError` (`pipelex.cogt.exceptions`).** Raised at setup time when the active model deck references a gateway model handle that isn't present in the (fresh or cached) gateway specs. Carries the model name and the config source (`RemoteConfigSource.FRESH` | `CACHED`); the message branches on source so a cached-source failure suggests `pipelex init` while online and a fresh-source failure points at deck/typo fixes. Wired through both the Rich CLI (`handle_gateway_unknown_model_error` in `error_handlers.py`) and the agent CLI (`AGENT_ERROR_HINTS` / `AGENT_ERROR_DOMAINS`).

- **`RemoteConfigUnavailableError` (`pipelex.system.pipelex_service.exceptions`).** User-facing offline-mode error: raised only when the network fetch fails AND no usable cached fallback exists. The message names the cache file path and the two remediation paths (run `pipelex init` while online to prime the cache; or disable `pipelex_gateway` in `backends.toml` for permanent BYOK operation). Distinct from the internal `RemoteConfigFetchError`, which is kept as the retry-layer exception.

- **`PIPELEX_REMOTE_CONFIG_URL` environment variable.** Overrides the default remote-config URL. Useful for staging/testing environments; defaults to the production URL when unset.

### Changed

- **Inference error handling refactored to Extract / Classify / Render (internal).** Every inference worker's SDK-exception block now collapses to `metadata = extract_*_metadata(exc); classification = classify_inference_error(metadata); raise render_*_error(...) from exc`. New modules: `pipelex/cogt/inference/error_classify.py` (single shared `classify_inference_error()` returning `ClassificationResult(category, user_action_kind, is_model_not_found)`), `pipelex/cogt/inference/error_render.py` (single shared `render_llm_error` / `render_img_gen_error` / `render_extract_error` / `render_search_error`, picking the `CogtError` subclass from an `InferenceErrorFamily` tag plus the `is_model_not_found` flag), and `pipelex/cogt/inference/provider_name.py` (the `ProviderName` enum keying the extract-fn registry). `ProviderErrorMetadata` gains a `message` field plus `is_quota_exhaustion` / `is_content_policy_violation` / `is_network_error` `@property` accessors; the per-provider `extract_*_metadata` functions are now the only plugin-local piece — Classify and Render live once. Mistral and the gateway-search worker specialize HTTP 404 to `ExtractModelNotFoundError` / `SearchModelNotFoundError`; Azure img-gen keeps two worker-specific `AMBIGUOUS` branches for mid-request transport failures. Removed: the per-provider `*_error_classification.py` modules and their tests, `AnthropicCredentialsError`, `GatewayFactory.classify_error_category` / `make_user_action_from_portkey_error` / `make_error_summary_from_portkey_error`, and every inline `_classify_*_error` / `_raise_categorized_*` worker method. New unit-test `tests/unit/pipelex/cogt/inference/test_provider_classification_parity.py` walks every `ProviderName` against the extract-fn registry + worker-family map, so an unwired new provider fails fast. No user-facing API change — the structured `ErrorReport` contract is unchanged. Documented at [under-the-hood/error-model.md](under-the-hood/error-model.md).

- **`instructor`'s structured-output retry no longer re-runs completions on transport errors.** Passed a bare `int`, `instructor`'s `max_retries` builds a retry loop whose predicate retries *any* exception — so the structured-output path (`PipeLLM` / `PipeStructure`) was re-running the whole completion on transport / API errors, a second retry loop nested on top of the SDK client's own transport retry. Each `instructor` call site now passes a `tenacity.AsyncRetrying` (built by the new `pipelex/cogt/llm/instructor_retry.py` helper) whose retry predicate matches only validation failures (`pydantic.ValidationError`, `json.JSONDecodeError`, and `instructor`'s own validation-error types). A transport error now propagates immediately as the raw SDK exception for the worker's `except` clause to classify — transport retry is the SDK client floor (Tier 1) alone, and `instructor`'s retry is confined to genuine schema re-ask. As part of this the Google and Mistral structured-generation workers gained an `httpx.TransportError` `except` clause: those SDKs let raw connection / timeout errors propagate outside their own exception hierarchies, so with `instructor` no longer wrapping them they must be caught and classified directly. The Mistral structured path also now gets schema re-ask at all — it previously passed no `max_retries`.

- **Inference schema-retry setting moved and renamed: `[cogt.llm_config.llm_job_config] max_retries` → `[cogt.llm_config] schema_reask_max_attempts` (breaking).** The setting is `instructor`'s schema re-ask budget for structured-output validation failures. The old name `max_retries` gave no hint of that scope and collided conceptually with the new top-level `cogt.transport_max_retries` — which counts retries *beyond* the initial attempt, whereas this one is a *total* attempt count (`stop_after_attempt`). The new name makes both the scope (schema re-ask) and the unit (attempts, not retries) explicit. The single-key `[cogt.llm_config.llm_job_config]` sub-table is also dropped — the setting now sits directly under `[cogt.llm_config]`. Projects that override this key in their own `pipelex.toml` must move and rename it.

- **Agent CLI `run` / `validate` / `init` default to markdown output, with independent success/error format options (breaking).** These commands previously always emitted JSON; they now accept `--format markdown|json` and default to markdown, matching `models` / `check-model` / `doctor`. A second flag `--error-format markdown|json` controls error reporting on stderr independently from success output — it defaults to the value of `--format`, so `--format json` still flips both, but the two can now be set separately (e.g. `--format markdown --error-format json` for human-readable success with machine-parseable errors). Internally, only the error format is carried in a `ContextVar`; the success format is threaded explicitly to `agent_success_formatted()`. The `inputs` / `concept` / `pipe` / `fmt` / `lint` / `accept-gateway-terms` commands are unaffected (always JSON / raw passthrough).

- **`pipelex-agent validate bundle` graph-format option renamed `--format` → `--graph-format` (breaking).** The `--format`/`-f` flag that selected the graph renderer (`mermaidflow` / `reactflow` / `both`) is now `--graph-format`/`-f`, freeing `--format` to be the uniform markdown/json output-format flag across every agent-CLI command.

- **Top-level Workflow ID shape change (breaking).** Workflow IDs go from `{env}{session5}-{rand5}-{ClassName}` (e.g. `EdgdJ-HR5fd-TemporalPipeRun-pipe-router`) to `{env_prefix}{pipeline_run_id}` (e.g. `ut-3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c`). The session-id and random-id components and the calling class name are gone; identity flows entirely from Pipelex's existing `JobMetadata.pipeline_run_id`. Operational tooling that grepped for the old shape must update.

- **Pipeline run chain semantics shift (breaking, behavioral).** Because the Workflow ID is now derived from `pipeline_run_id`, callers that pass a stable `pipeline_run_id` to `PipelineFactory.make_pipeline(pipeline_run_id=...)` and re-execute now land on the same Temporal Workflow Execution Chain (with a fresh `run_id` per execution under the SDK-default `ALLOW_DUPLICATE` reuse policy). The previous behavior produced a fresh workflow_id per execution by accident, via the truncated session id and random shortuuid components — not by design. This is now documented behavior, not a bug.

- **Child Workflow ID separator (breaking).** Child workflow ids use `_` as the separator (never `/`), so an id can be reused verbatim as an S3 key or file name without creating spurious path segments. Examples: the fixed-role `wf_pipe_router` child of `wf_pipe_run` is `{parent}_pipe-router`; a dynamic sub-pipe spawned by a router is `{parent}_{pipe_code}-{8-hex-chars}` (the 8 hex chars come from `workflow.uuid4()` for replay-safety). Operational tooling parsing the nested-id format must update.

- **Activity ID change (breaking).** Pipelex no longer customizes `activity_id`. The Temporal Python SDK auto-assigns deterministic sequential integers (`"1"`, `"2"`, …) per workflow run, which guarantees per-`(workflow_id, run_id)` uniqueness by construction and is replay-safe (assigned by history position). Per-call meaning that previously lived in `activity_id` now lives in the per-activity `summary=`. Anything that filtered or grouped Event History by the old semantic strings (`"craft-text"`, `"craft-object-direct"`, `"jinja2-text"`, `"extract-pages"`, etc.) must read the per-activity `summary` or the Activity Type instead.

- **`wfid` parameter removed (breaking).** The `wfid: str | None = None` parameter is dropped from `PipeRunProtocol`, `PipeRouterProtocol`, `ContentGeneratorProtocol`, and every implementation (`PipeRun`, `PipeRouter`, `DryPipeRouter`, `TemporalPipeRun`, `TemporalPipeRouter`, `ContentGenerator`, `ContentGeneratorDry`, `ContentGeneratorInWorkflow`). The parameter was a legacy artifact — `wfid` originally seeded child workflow ids, was later co-opted as a default `activity_id`, and had no production callers. Identity now flows entirely via `JobMetadata.pipeline_run_id`; observability is auto-derived from `pipe_code` / `domain_code`. No deprecation cycle; per Pipelex's no-backward-compat policy, callers update at once.

- **`ContentGeneratorInWorkflow` LRU + replay short-circuit deleted.** The worker-singleton `_seen_activity_ids: OrderedDict[(workflow_id, run_id), set[str]]` cache, the `_MAX_SEEN_RUNS` bound, and `_record_activity_id` (with its `workflow.unsafe.is_replaying()` short-circuit) are gone. They existed solely to defend against the duplicate-activity-id failure mode that no longer exists now that Pipelex does not customize `activity_id`. Future contributors: do not reintroduce worker-singleton state on the activity-dispatch path — the determinism guarantee is the SDK assigning ids by history position.

- **`structuring_method = "preliminary_text"` on `PipeLLM` works again, via build-time elaboration.** When `PipelexInterpreter` parses a `.mthds` file with a `PipeLLM` carrying `structuring_method = "preliminary_text"`, the new `BundleElaborator` rewrites it before any pipe runs into a `PipeSequence` of two synthetic pipes: a `PipeLLM` producing `Text` (step 1, inheriting the original prompt + inputs + model) and a `PipeStructure` producing the original output (step 2, optionally using `model_to_structure`). The synthetic codes are tracked in a `PipelexBundleBlueprint.elaboration_metadata` side-table (excluded from serialization). Output multiplicity is preserved: step 1 always emits a single `Text`; step 2 emits `Foo`, `Foo[]`, or `Foo[N]` according to the original output. Two LLM calls are issued per invocation. The user-facing pipe code is unchanged, so callers, `main_pipe`, and the run API keep working as before. Mechanism documented at [under-the-hood/build-time-elaboration.md](under-the-hood/build-time-elaboration.md).

- **`PipeLLM` runtime no longer knows about `structuring_method`.** The field is now a pure build-time directive. The runtime `PipeLLM` class no longer carries `structuring_method`, the validator that rejected mismatched output concepts has moved to `PipeLLMBlueprint` (where it fires at parse time), and the `NotImplementedError` previously raised at runtime when `preliminary_text` was selected is gone — the elaborator handles it. `PipeLLMSpec` exposes `structuring_method` so AI agents authoring via specs can still opt in.

- **`StructuringMethod` enum import path moved.** The enum is now defined in `pipelex.pipe_operators.llm.pipe_llm_blueprint` (it lives next to the blueprint that consumes it) instead of `pipelex.pipe_operators.llm.pipe_llm`. Direct importers must update their `from pipelex.pipe_operators.llm.pipe_llm import StructuringMethod` line to `from pipelex.pipe_operators.llm.pipe_llm_blueprint import StructuringMethod`.

- **Collapsed the `tprl_content_generation/` workflow layer.** Each content-generation call (LLM text/object/object-list, image generation, Jinja2 rendering, document extraction, PDF page-view rendering) previously went through a dedicated child workflow (`WfMakeLLMText`, `WfMakeObject`, `WfMakeImages`, `WfMakeJinja2Text`, `WfMakeExtract`, `WfRenderPageViews`) that wrapped a single `act_*` activity. The wrappers added one workflow-scheduled / started / completed history-event triplet per call without changing durability guarantees — every retry still happens at the activity level. `ContentGeneratorInWorkflow` now calls `workflow.execute_activity(act_*, ...)` directly from inside `WfPipeRouter`, deleting all `WfMake*` / `WfRenderPageViews` workflows, both `ContentGeneratorTop` and `ContentGeneratorChild` generators along with their factories, and the `content_generator_models.py` assignment-types module. Per-step meaning in the Temporal Web UI now comes from per-activity `summary=` (and Activity Type), replacing the old semantic `activity_id` strings. Page-views augmentation (`should_include_page_views`) now works in Temporal mode: `make_extract_pages` dispatches `act_render_page_views` for `document_uri` inputs and builds an inline single-element `[ImageContent(url=...)]` list for `image_uri` inputs, then attaches each page-view to its `PageContent`. Previously the direct-mode generator handled both branches but the child-workflow path (`WfMakeExtract`) only ran the extract activity and silently skipped the page-views step, so `should_include_page_views=True` was a no-op under Temporal.

- **Per-activity, per-handle Temporal task-queue routing.** Replaced the provisional `WorkerConfig.inference_task_queue` (one-off LLM-text override) with a general `activity_queues: dict[str, ActivityRouteConfig]` table. Each entry declares a per-activity `default` queue and an optional `by_handle` map keyed by runtime handle (LLM model handle for text/object/object-list, `img_gen_handle` for image generation, `extract_handle` for document extraction). At dispatch time, `WorkerConfig.resolve_queue(activity_name, routing_key)` walks three layers: (1) `activity_queues[activity_name].by_handle[routing_key]`, (2) `activity_queues[activity_name].default`, (3) the worker-wide `default_task_queue` default. Every `ContentGeneratorInWorkflow` call site now passes `task_queue=worker_config.resolve_queue(...)` uniformly — the asymmetric "LLM-text-only kwarg" is gone, the `_inference_dispatch_kwargs` stopgap is deleted, and `WorkerConfig.inference_task_queue` is removed (no backward-compat shim). Deployments can now scale OpenAI vs Anthropic worker pools independently, isolate image generation onto dedicated runners, or route specific OCR backends to dedicated queues — all via TOML config, with no code change required. Default `pipelex.toml` ships with an empty `activity_queues` table, so existing single-queue deployments are unaffected.

- **Per-queue submitter options and named worker-runtime profiles.** Layers on top of the per-activity routing above. (1) `[temporal.queue_options.<queue>]` declares per-queue `start_to_close_timeout`, `schedule_to_close_timeout`, `schedule_to_start_timeout`, `heartbeat_timeout`, `retry_policy_config`, and cluster-wide `max_task_queue_activities_per_second`. (2) `activity_queues.<activity>.handle_options.<handle>` declares rare per-handle overrides for a single model/backend variant. (3) `[temporal.worker_runtime_profiles.profiles.<name>]` declares concurrency slots, pollers, heartbeat throttles, worker-local rate cap, and graceful shutdown timeout; one worker process selects one profile via `pipelex worker --profile <name>`. The new `WorkerConfig.resolve_dispatch(activity_name, routing_key)` composes baseline → `queue_options[resolved_queue]` → `handle_options[routing_key]` last-wins for scalars, and unions `non_retryable_error_types` additively across all three layers (baseline main list + queue `_extra` + handle `_extra`). The `RetryPolicyConfig` schema split into a baseline class (owns `non_retryable_error_types`) and an overlay class (owns `non_retryable_error_types_extra`); `extra="forbid"` rejects the wrong field on each layer so the additive composition rule is enforced at config load. Every `workflow.execute_activity(...)` site in `ContentGeneratorInWorkflow` now splats `worker_config.resolve_dispatch(...).to_execute_kwargs()` — fixing a long-standing bug where the workflow-level `workflow_execution_timeout` was used as every activity's `start_to_close_timeout` (a 1h budget on a jinja2 render, same 1h on a slow PDF extract).

- **Strict `--task-queue` validation at worker CLI startup.** `pipelex worker --task-queue X` now fast-fails with `WorkerTaskQueueUnknownError` (and a Levenshtein "Did you mean?" suggestion) when `X` isn't declared in `default_task_queue`, any `activity_queues` entry, or any `queue_options` key. Strict counterpart to the lenient config-load WARN on routing entries that name unknown queues.

- **Dispatch resolution tracing.** Set `temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced = true` to emit one INFO log line per `workflow.execute_activity` call, including the resolved queue, timeout, retry attempts, and the layer (`baseline` / `queue_options` / `handle_options`) each scalar came from. Off by default.

- **Specialized worker scopes.** New `runner-llm`, `runner-img-gen`, `runner-extract`, `runner-jinja2` scopes under `[temporal.worker_scopes.scopes]` for deployment manifests that want one worker pool per backend class. Each scope registers only its activities (e.g. `runner-llm` registers `act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list`). `act_render_page_views` is registered under both `runner-img-gen` and `runner-extract` (belt-and-suspenders for the two paths that need it).

- **`temporal.worker_config.task_queue` renamed to `default_task_queue`.** Migration map entry under `[migration.migration_maps.config]` maps the old key. New required field `default_activity_start_to_close_timeout` (baseline activity timeout, default `"0:10:00"`) replaces the previous accidental reuse of `workflow_execution_timeout` for activities.

- **Cluster-wide queue rate cap moved from Python constant to TOML overlay.** `TemporalTaskManager.make_worker` previously hardcoded `max_task_queue_activities_per_second=1000` on the Temporal `Worker(...)` constructor for every queue. It now reads this knob from `queue_options[task_queue].max_task_queue_activities_per_second`; the shipping default `[temporal.queue_options.temporal_task_queue]` sets it to `1000`, so out-of-the-box behavior on the default queue is unchanged. Deployments using non-default queue names should add their own `[temporal.queue_options.<queue>]` entries with the cap appropriate for that backend pool. The per-worker `max_activities_per_second = 1000` lives on the runtime profile and is unchanged.

- **Removed dead code: `pipelex/temporal/wrapper/`.** The `start_tprl_activity` wrapper had zero callers.

- **Retry removed from the gateway workers; `[cogt.tenacity_config]` removed (breaking).** The `tenacity`-based retry inside `GatewayExtractWorker` and `GatewaySearchWorker` is gone, along with the `[cogt.tenacity_config]` config block and its `TenacityConfig` model. Because config models forbid unknown keys, an existing `~/.pipelex/pipelex.toml` (or any layered override) that still carries `[cogt.tenacity_config]` will fail to load — remove that block from your config. Transient transport blips are left to the provider SDK clients' own retry; the `tenacity` library itself is still used elsewhere (FAL job polling, remote-config fetch) and remains a dependency.

- **`PipeRouter.run()` now reports `CogtError` failures to the observer.** A `CogtError` raised out of pipe execution previously propagated past `run()` without an `observe_after_failing_run` notification (only `PipeRunError` was caught). It is now observed on the failing path, then re-raised as-is — the cause chain is preserved and it is not wrapped into `PipeRouterError` (only the `PipeRunError` path still wraps).

- **Provider HTTP 404s now raise dedicated `*ModelNotFoundError` across LLM, image-gen, extract, and search.** A model-or-deployment-not-found 404 from any LLM or image-gen provider, or from the Pipelex Gateway extract / search workers, now raises a dedicated `*ModelNotFoundError` (`LLMModelNotFoundError`, `ImgGenModelNotFoundError`, `ExtractModelNotFoundError`, `SearchModelNotFoundError` — all `ModelNotFoundError` subclasses, `CONFIGURATION` category) instead of a generic `LLMCompletionError` / `ImgGenGenerationError` / `ExtractJobFailureError` / `GatewaySearchResponseError`. Because these are siblings of the generic errors — not subclasses — a 404 propagates past the operator's generic `except` to `except ModelNotFoundError` in `PipeOperator._live_run_pipe`, which re-raises `PipeOperatorModelAvailabilityError` carrying the unavailable `model_handle`.

- **`RemoteConfigFetcher.fetch_remote_config()` now returns a `RemoteConfigResult`** carrying `config`, `source` (`fresh` | `cached`), and `cached_at`, instead of a bare `RemoteConfig`. Callers unwrap `.config` for the payload and may branch on `.source` to know whether the config is fresh or restored from cache. The fetcher accepts a new keyword-only `require_fresh: bool = False` — when `True`, a cached fallback raises `RemoteConfigUnavailableError` instead. `RemoteConfigValidationError` is never satisfied by the cache (server-side schema breaks must surface loudly).

- **`ModelManager.setup()` and `BackendLibrary._load_gateway_model_specs()` accept a new `gateway_config_source: RemoteConfigSource | None` parameter.** Passed through from `Pipelex.setup()` so the deck-level gateway membership check can branch its error message on `FRESH` vs `CACHED`. `GatewayConfig` itself stays `extra="forbid"` and source-free — provenance is plumbed alongside, not baked in.

- **`RemoteConfigUnavailableError` message branches on whether the cache was refused vs absent.** When `require_fresh=True` (dev-CLI generators) refuses to fall back to an existing cache, the message now reads "the local cache at `<path>` was refused because a fresh fetch is required" instead of the previously misleading "no local cache is available at `<path>`". The cache-truly-missing path keeps its original wording.

### Fixed

- **Inference-failure `ErrorReport`s now carry `model` and `provider` in production.** A real LLM / image-gen / extract / search failure used to surface an `ErrorReport` with `model = None` and `provider = None`: the leaf errors (`LLMCompletionError`, `ImgGenGenerationError`, `ExtractJobFailureError`, `SearchJobFailureError`, `ExtractOutputError`) carry no model or provider of their own, and `CogtError.to_error_report()` only duck-typed whatever attributes happened to be set on the exception. Each inference worker family now fills `model_handle` / `backend_name` from the worker — where both are unambiguously known — at its public-method chokepoint (`gen_text` / `gen_object`, `gen_image` / `gen_image_list`, `extract_pages`, `search_sourced_answer` / `search_structured`), via the new `CogtError.fill_model_and_provider()`. The fill never overwrites a value an inner error already set and skips the `"unknown"` placeholder external plugins report. `model_handle` / `backend_name` are now declared on `CogtError` (so `to_error_report()` reads them directly instead of `getattr`), making them uniformly `str | None` across the exception hierarchy.

- **Two worker error-classification miscategorizations corrected.** `LinkupNoResultError` (a search or fetch that returned nothing) had no explicit branch in either Linkup worker's `_classify_linkup_error` and fell through to the `TRANSIENT` catch-all — marking a query that cannot succeed by retrying as retryable. It is now classified `CONTENT` + `CHANGE_INPUT` in both the search and the extract worker. **Behavior change:** a no-result search is now non-retryable (`CONTENT.is_retryable` is `False`), so Temporal's activity retry policy no longer retries a query that returns nothing on every attempt. Separately, the `FileNotFoundError` branch in the Docling and pypdfium2 extract workers was classified `CONFIGURATION` — inconsistent with its sibling branches (`CONTENT` + `CHANGE_INPUT`) and with the rest of the codebase, where `CONFIGURATION` is reserved for setup problems. A missing input file is a content problem; it is now `CONTENT`. This second change does not alter retry behavior — `CONFIGURATION` and `CONTENT` are both non-retryable.

- **Wrapped exceptions now surface the underlying inference error's classification.** `PipelexError.to_error_report()` enriches its report from the `__cause__` chain, so a `PipelineExecutionError` — or any wrapper around a transient `CogtError` — now reports `error_category`, `retryable`, `model`, and `provider` instead of dropping them. Previously the agent-CLI JSON / markdown error output for a failed pipeline run lost the worker's category and retryability once the error had been wrapped by the pipe operator → router → runner layers, leaving an agent unable to tell a transient failure from a fatal one.

- **MTHDS JSON schema no longer leaks the `elaboration_metadata` side-table.** `PipelexBundleBlueprint.elaboration_metadata` carried `Field(exclude=True)` so it stayed out of `model_dump()` / `model_validate()` round-trips, but Pydantic v2's `exclude=True` does not affect `model_json_schema()` — so `derived/mthds_schema.json` ended up declaring a top-level `elaboration_metadata` property plus `$defs/ElaborationMetadata` and `$defs/StepRole` entries, even though the side-table is process-local in the reference runtime. Wrapped the field type with `SkipJsonSchema[...]` so it is hidden from the schema. After regenerating, the three entries are gone from the public schema, matching the spec's silence on them.

- **Cross-process Temporal decode of `ListContent` payloads for dynamic concepts.** `WorkingMemory.dump_for_temporal()` was tagging each list item with `__class__` / `__module__` markers so the receiving worker could rebuild the right subclass for `Anything[]` outputs. Those keys are also kajson's universal-decoder protocol, so the Temporal data converter tried to eagerly bind dynamic-concept classes (e.g. `structured_output_test__Invoice`) at the payload boundary — before the child workflow's per-workflow `ClassRegistry` was loaded. In a true 3-process topology the class is not in the global registry (the child workflow tore down its scoped registry in `finally`), so `kajson.loads` raised `KajsonDecoderError` → `RuntimeError: Failed decoding arguments` and any `--temporal` run that produced a list of dynamic-structured-concept items hung. Renamed the markers to the pipelex-private namespace `__pipelex_class__` / `__pipelex_module__` in `WorkingMemory.dump_for_temporal()` and `_hydrate_list_item()`; kajson's decoder gates strictly on `__class__` (`kajson/json_decoder.py:132`) so pipelex's nested dicts now pass through untouched and class binding stays inside pipelex's hydrator where the per-workflow registry lives. Also extended `CLEAN_JSON_FIELDS_TO_SKIP` in `pipelex/tools/misc/json_utils.py` to strip both marker families from user-facing JSON output.

- **A directory containing a `.pipelex/` config dir is now recognized as a project root.** `.pipelex` was added to `PROJECT_ROOT_MARKERS`, so project-level config (e.g. `.pipelex/inference/backends.toml`) is honored even when the directory has no `.git`, `pyproject.toml`, or other source-project marker. Previously such a directory fell through to the global `~/.pipelex/` config, silently ignoring the project's own overrides — so a backend disabled in the project's `backends.toml` could still demand credentials because the global config (where it was enabled) was loaded instead. The home directory remains excluded from project-root detection, so the global `~/.pipelex/` is unaffected.

- **`PipeLLM` outputting a concept that refines the native `JSON` concept no longer crashes with `NameError: name 'Any' is not defined`.** On a LIVE run, such a concept resolves to a structured-output model carrying a `dict[str, Any]` field inherited from `JSONContent`. `SchemaToModelFactory` generates that model as source with `from __future__ import annotations` (every annotation becomes a string) and then rebuilds each class to resolve the string annotations. The rebuild namespace was assembled from the exec'd user types plus a hand-listed `Literal`, but `typing.Any` is a special form, not a `type`, so it was filtered out — `model_rebuild` then raised `PydanticUndefinedAnnotation` evaluating `"dict[str, Any]"`. The rebuild namespace is now the exec namespace itself (minus `__builtins__`), so it carries exactly the names the generated source was written against and cannot drift as codegen emits other typing constructs. Fixed in `pipelex/cogt/content_generation/schema_to_model_factory.py`; covers both the sender path (`make_from_json_schema`) and the cross-process receiver path (`make_types_from_source`).

## [v0.28.0] - 2026-05-13

### Changed

- **Breaking (rendering): graph viewer assets are no longer bundled into generated HTML.** The ReactFlow HTML output now references `@pipelex/mthds-ui` (the standalone IIFE bundle + its CSS) and `elkjs` from `cdn.jsdelivr.net` with pinned versions and `sha384` Subresource Integrity hashes. Three external requests now load from jsDelivr at view time; the HTML itself is still generated offline by Pipelex — only viewing the rendered graph requires network access. The previous `make sync-graph-ui` / `make check-graph-ui-sync` workflow and the committed `pipelex/graph/reactflow/assets/graph-viewer.{js,css}` files have been removed; the manifest-style `package.json` and the `Graph UI sync check` GitHub Actions workflow are gone. A single Python module (`pipelex/graph/reactflow/standalone_assets.py`) is the source of truth for pinned versions and integrity hashes — the template reads them via Jinja2, so a bump touches one file plus the regenerated SRI constants. The new `pipelex-dev refresh-graph-ui-sri` command re-fetches the URLs, recomputes `sha384`, and rewrites the constants module; the `update-graph-ui` skill drives that flow. Previously, the "self-contained HTML" was already not offline (elkjs loaded from `unpkg.com` without integrity), and bumping the vendored bundle meant committing ~2 MB of regenerated JS+CSS on every mthds-ui release — SRI hashes give the same tamper-evidence with none of the diff churn.
- **Breaking: `@var` / `@?var` sigils must be alone on their own line, and inline `@<ident>` raises at load time only when `<ident>` collides with a declared input of the surrounding pipe.** The `@`/`@?` rewriters wrap the value in a tag-shaped block envelope (`<var>...</var>` via the `tag()` filter), so the inline shapes never produced sensible output and are now rejected at load time with a new `TemplateSigilSyntaxError` — surfaced through pydantic validation with the line number, the offending span, and a migration hint. To stay friendly to coding agents authoring HTML/CSS templates (`<style>@media (...) { ... }</style>`, `@font-face { ... }`, Python/Java decorators like `@deprecated` / `@Override`), the validator is gated on the surrounding pipe's declared `inputs`: an inline `@<ident>` raises only when the candidate's root identifier matches a declared input (a real typo). Every inline candidate on a line is inspected, so a later collision can't hide behind an earlier CSS at-rule. Other inline `@` candidates pass through silently. The line-bounded rewriter (alone-on-line `@var` → `{{ var|tag("var") }}`, leading/trailing whitespace preserved) is unchanged and remains inputs-agnostic. The strict rule replaces the heuristic regex tightening from the prior CSS-collision fix: there are no residual rewrites for `@font-face` / `@counter-style` / `@view-transition` / `@property --x`, no special-case lookbehind/lookahead arms. The `$var` inline sigil is unchanged. **API:** `preprocess_template(template, *, declared_inputs=...)` gained a keyword-only `declared_inputs: set[str] | None` parameter (default `None` = lenient, no validation); a new pair of helpers `validate_template_sigils(template, declared_inputs)` and `rewrite_template_sigils(template)` exposes the validate and rewrite steps separately. `render_template` (runtime) calls `rewrite_template_sigils` directly — templates are already validated at load time, so the render path doesn't need the `declared_inputs` context. All pipe blueprints (`PipeLLMBlueprint`, `PipeComposeBlueprint`, `PipeSearchBlueprint`, `PipeImgGenBlueprint`, `PipeComposeFactory`) and template analyzers (`TemplateDocumentAnalyzer`, `TemplateImageAnalyzer`) thread their declared inputs into the validator; the base `TemplateBlueprint` and `ConstructBlueprint`-discovery validators remain lenient (no inputs context at that layer — the surrounding pipe's validator catches typos). **Migration:** for inline values, switch from `@var` to `$var`; for block-shaped content, move the sigil onto its own line; for literal `@` or `$` characters, use the `@@` / `$$` escapes documented below.

### Added

- **`@@` and `$$` template escapes.** Authors can opt out of sigil interpolation per occurrence: `@@var` renders as the literal string `@var` (no `{{ ... }}`), and `$$var` renders as the literal `$var`. The escapes are non-overlapping left-to-right (`@@@@var` → `@@var`, two literal `@`s). Use these for any literal `@`/`$` the author needs to keep in the rendered output — most commonly `@@font-face`, `@@namespace`, `@@media` inside CSS `<style>` blocks, or `$$10` for a literal dollar amount. Cross-link: `wip/template-preprocessor-line-bounded-at.md`.
- **`TemplateSigilSyntaxError`** (`pipelex/cogt/templating/template_errors.py`): raised by the preprocessor when a candidate `@`/`@?` sigil is not alone on its line. Pipe blueprints (`PipeLLMBlueprint`, `PipeComposeBlueprint`, `PipeImgGenBlueprint`, `PipeSearchBlueprint`, `TemplateBlueprint`, `ConstructBlueprint`, `pipe_compose_factory`) and the `TemplateBlueprint` validator catch and re-raise as pydantic `ValueError` with pipe-specific context, so the diagnostic surfaces through normal MTHDS validation errors and IDE/`plxt check` diagnostics.

### Fixed

- **Template preprocessor: `$<var>` no longer substitutes when `$` is adjacent to a word character on the left** (e.g. `micro$oft`, `user$host.com`, `P@ssw$rd123`, `a$b$c` now pass through unchanged instead of producing mid-word `{{ ... }}` substitutions), and no longer emits invalid Jinja for shapes like `$name..` (now renders `{{ name|format() }}..` with both trailing dots preserved as literal punctuation). The `$` arm now mirrors the `@` candidate pattern's word-boundary lookbehind (`(?<!\w)`) and uses a strict segmented identifier `[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*` that rules out a leading digit and consecutive dots structurally. The trailing-dot kludge in the `$` replacement function is gone (unreachable under the strict identifier shape). `$var` keeps its silent pass-through posture for non-candidate shapes — it does not raise like the `@` arm does.
- **Project `.pipelex/telemetry.toml` created by `pipelex init` no longer silently disables globally-enabled telemetry.** The kit previously shipped one `telemetry.toml` template carrying explicit `enabled = false` / `mode = "off"` defaults, and `pipelex init telemetry` copied it into both `~/.pipelex/` and the project's `.pipelex/`. Because the layered loader appends the project base file after `~/.pipelex/telemetry_override.toml`, a user who enabled Langfuse/PostHog globally in their override still had it turned off in every initialized project. The kit now ships a separate `telemetry.project.toml` template with every setting commented out, used only by project-level init. The global init still copies the active `telemetry.toml`. As a safety net, `telemetry_allowed_modes` defaults (`ci=False`, `cli=True`, `docker=True`, `fastapi=True`, `mcp=True`, `n8n=True`, `pytest=False`, `python=False`) now live in the `TelemetryConfig` Pydantic model rather than the TOML template, so a project file that omits the section can't disable custom telemetry for everyone.
- **Global `pipelex.toml` and `telemetry.toml` overrides no longer silently disappear when a project `.pipelex/` exists.** `ConfigLoader.load_config()` previously sourced *all* override files (`pipelex_local.toml`, `pipelex_{env}.toml`, `pipelex_{run_mode}.toml`, `pipelex_override.toml`, `pipelex_temporary_override.toml`) from a single "effective config dir" — project `.pipelex/` if present, else `~/.pipelex/`. As a result, the user's machine-wide overrides in `~/.pipelex/` were ignored entirely the moment a project shipped its own `.pipelex/`. `load_telemetry_config` had the same shadowing behavior for `telemetry.toml` and `telemetry_override.toml`, which was particularly painful because telemetry holds Langfuse/PostHog/OTLP secrets that users typically set once globally. Both loaders now layer global → project: package defaults → global base → global overrides → project base → project overrides, deep-merged so machine-wide personal preferences keep applying unless explicitly overridden by the project. The unit-testing run_mode behavior is preserved: `./tests/pipelex_{run_mode}.toml` is still the only run_mode file loaded under unit testing, replacing both layers to keep test runs hermetic. **Migration:** if a project previously relied on its `.pipelex/` to fully *replace* the user's global config rather than merging over it, the project must now redeclare any keys it wants to set explicitly — silent inheritance from `~/.pipelex/` is the new default.
- **`pipelex build structures` now emits domain-qualified class names and cross-references.** `ConceptFactory` registers each concept's structure class under `make_qualified_structure_class_name(domain, concept_code)` (e.g. `expense_validator__SpendingLimitCheck`), but the CLI generator was passing the bare `concept_code` to `StructureGenerator`. Generated files therefore contained `class ConceptCode(StructuredContent)` and unqualified cross-imports/types, while the registry expected the qualified name. `PipeFunc` validation against `concept.structure_class_name` then rejected the mismatch with `output concept expects structure class 'domain__X', but the function return type is 'X'`, breaking library load for any project that had regenerated structures. Fixed in `pipelex/cli/commands/build/structures_cmd.py`: the class-definition call sites now call `make_qualified_structure_class_name(blueprint.domain, concept_code)`; `_build_concept_ref_to_class_info` qualifies cross-reference class names while keeping the file stem unqualified so output filenames stay `domain__concept_code.py`; the `refines:` branch resolves the refined concept's domain via `QualifiedRef.parse_stripping_cross_package` and qualifies the base-class name for non-native refines, mirroring `ConceptFactory._handle_refines`.
- **`pipelex build structures` cross-package refines now emit the base-class import.** A concept that refines a class defined in another already-installed package (e.g. `RefiningConcept` with `refines: some_alias->other_domain.OtherConcept`) was generating a file that inherited from `other_domain__OtherConcept` without importing it. `StructureGenerator._validate_execution` injects the base class into `exec_globals` from the class registry, so codegen-time validation passed; the failure surfaced only when the generated structures module was later loaded via the normal Python import system, raising `NameError: name 'other_domain__OtherConcept' is not defined`. The generator now falls back to the class registry's `__module__` when `concept_ref_to_class_info` has no entry for the base class and emits the corresponding import (guarded on `cls.__name__ == base_class` so we never emit a name the target module won't expose). Regression test in `tests/unit/pipelex/cli/commands/build/test_structures_cmd_cross_package_refines.py` was tightened to assert the import statement is present.

## [v0.27.0] - 2026-05-07

### Changed

- **`RunEnvironment` env var renamed from `ENVIRONMENT` to `PIPELEX_ENV`.** The variable that selects the environment-specific `pipelex_<env>.toml` overlay (and is stamped on OTel spans as `deployment.environment`) is now namespaced to avoid collisions with unrelated `ENVIRONMENT` variables already set in deployment environments. Update any shell, CI, or container config that exported `ENVIRONMENT=...` to export `PIPELEX_ENV=...` instead.

## [v0.26.4] - 2026-05-06

### Fixed

- **Temporal storage delivery no longer fails when `working_memory_raw` contains rehydrated Pydantic instances.** `WorkingMemory.dump_for_temporal()` embeds `__class__`/`__module__` markers on `ListContent` items so the receiving workflow can hydrate them. Kajson's Temporal data converter then eagerly rebuilds those dicts back into `BaseModel` instances (e.g. `PageContent` from `Page[]` outputs) on the activity worker that runs delivery — even though `working_memory_raw` is typed as `dict[str, Any]`. `clean_json_content()` previously walked only dicts/lists/scalars and let `BaseModel` instances reach `json.dumps`, which raised `TypeError: Object of type PageContent is not JSON serializable` and aborted `act_deliver`. `clean_json_content` now reduces any `BaseModel` it encounters via `model_dump(serialize_as_any=True)` (the canonical `smart_dump` path) before continuing the recursive walk.

## [v0.26.3] - 2026-05-06

### Fixed

- **OpenAI SDK 2.34.0 compatibility for Portkey/Gateway clients.** The new SDK adds both a constructor-time check (`_enforce_credentials`) and a request-time `_validate_headers` guard that reject an empty `api_key`. Pipelex's gateway and Portkey factories were passing `api_key=""` because auth is delivered via `x-portkey-api-key` and `x-portkey-config` headers, not the OpenAI `Authorization` header. Replaced the empty string with a non-empty placeholder (`"unused-auth-via-portkey-headers"`) in `gateway_completions_factory`, `gateway_responses_factory`, `portkey_completions_factory`, and `portkey_responses_factory`. Same fix applied to `openai_client_factory` for the no-auth case (e.g. local Ollama backends), where `backend.api_key` is intentionally unset. Bumps the `openai` requirement to `>=2.0.0`.

## [v0.26.2] - 2026-05-06

### Fixed

- **`choices` fields no longer fail validation with `'EnumName.MEMBER_NAME'` errors.** A concept declared with `choices = [...]` produces a `Literal[...]` field on the dynamic Pydantic class. That schema is round-tripped through `SchemaToModelFactory.make_from_json_schema` (used to rebuild dynamic models on Temporal workers and to feed structured-output schemas to LLM providers). Previously the round-trip silently re-emitted the field as a plain Python `Enum` class — e.g. `Literal["Strong Match", "Good Match", "Partial Match", "Poor Match"]` became `class Recommendation(Enum): Poor_Match = "Poor Match"; ...`. LLMs filling that schema then returned the enum's Python repr (`"Recommendation.Poor_Match"`) instead of the literal string (`"Poor Match"`), which failed Pydantic validation against the original choice set with errors like `Invalid choice errors: 'recommendation': got 'Recommendation.Poor_Match', expected one of 'Strong Match', 'Good Match', 'Partial Match' or 'Poor Match'`. `_generate_source_from_schema` now passes `enum_field_as_literal=LiteralType.All` to `datamodel-code-generator`, so `enum: [strings]` schema nodes round-trip as `Literal[...]` instead of being regenerated as `Enum` classes. `_exec_source_to_types` now also exposes `Literal` in the rebuild namespace so `model_rebuild` resolves the deferred annotations.

## [v0.26.1] - 2026-05-05

### Changed

- **Live-run graph output**: `pipelex-agent run` now emits the assembled `GraphSpec` as `live_run_graph.json` alongside `live_run.json` and the ReactFlow HTML.

## [v0.26.0] - 2026-05-04

### Highlights

- **Temporal distributed execution** — Pipelex pipelines can now run as Temporal workflows across worker processes. New `pipelex[temporal]` extra, `pipelex worker` CLI, `PipeRun` layer, and `LibraryCrate` IR for cross-process library propagation.
- **Distributed tracing** — pluggable event-log backends (NDJSON, DynamoDB, in-memory, buffering) emit cross-worker `TraceEvent`s that reassemble offline into a complete `GraphSpec`. Enabled by default; works in single-process mode too.

### Added

#### Temporal distributed execution

- **`pipelex[temporal]` extra and full Temporal integration package (`pipelex/temporal/`)**: includes `temporal_manager`, `temporal_connect`, `temporal_data_converter` (kajson-based JSON), `sandbox_manager`, `task_manager`, and a `pipelex worker` CLI subcommand that boots a worker against a configured queue. Toggle via `[temporal] is_enabled` in `pipelex.toml`. Bumps `temporalio` to `1.23.0`.
- **`PipeRun` layer (`pipelex/pipe_run/`)**: new `PipeRunProtocol` with `PipeRun` (in-process) and `TemporalPipeRun` (workflow-orchestrated) implementations. Wraps pipe execution + delivery in a single orchestration unit. In Temporal mode, `WfPipeRun` orchestrates `WfPipeRouter` as a child workflow followed by delivery activities. `TemporalPipeRun.start()` is non-blocking and returns `workflow_id` + `WorkflowHandle` immediately.
- **`TemporalPipeRouter`**: single router that auto-detects context (top-level vs child workflow) and dispatches accordingly.
- **Delivery framework**: `DeliveryAssignment` model with `WebhookDeliveryAssignment` (HTTP POST) and `StorageDeliveryAssignment` (S3 / local). Deliveries run as Temporal activities with automatic retry, or inline in direct mode.
- **`LibraryCrate` IR (`pipelex/libraries/library_crate.py`, `library_crate_factory.py`)**: serializable intermediate representation that lets a Temporal worker reconstruct the exact set of libraries (concepts, pipes, structures) required to execute a job — no shared filesystem assumed.
- **`StoragePayloadCodec`**: offloads Temporal payloads larger than a configurable threshold (default 1 MiB) to external storage (S3 or local) and replaces them with lightweight URI references. Configurable via `[temporal.payload_codec_config]`. New `pipelex codec serve` CLI launches the codec server consumed by the Temporal Web UI for payload inspection.
- **Schema-based dynamic model construction (`pipelex/cogt/content_generation/schema_to_model_factory.py`)**: rebuilds dynamic Pydantic models on a Temporal worker from the JSON schema embedded in `ObjectAssignment`, instead of relying on cross-process class identity. Cache bounded by an LRU (`_SCHEMA_CACHE_MAX_SIZE = 1024`); codegen serialized through a file lock to kill thundering-herd duplication on long-running workers receiving many distinct schemas. Adds `datamodel-code-generator>=0.55.0` as a runtime dependency.
- **Worker scopes**: `pipelex worker --scope ...` lets a worker subscribe to a subset of activities/workflows so deployments can specialize workers (e.g. inference workers vs orchestration workers).
- **`WorkerConfig.inference_task_queue`**: optional task-queue override for `act_llm_gen_text` so router and inference activities can be deployed on separate worker pools.
- **Pre-generated `pipeline_run_id` support**: `pipeline_run_setup()`, `PipelineFactory`, and `PipelineManager` accept an optional `pipeline_run_id` parameter for external run-record creation.
- **`workflow_id` in start response**: `PipelexPipelineStartResponse` includes `workflow_id`.
- **Temporal `callbacks` passthrough**: `WorkflowExecutor.start_workflow()` accepts optional Temporal `Callback` objects.

#### Distributed tracing (`pipelex/tracing/`)

- **`EventLogProtocol` with pluggable backends**: `NdjsonEventLog`, `DynamoDBEventLog`, `InMemoryEventLog`, `BufferingEventLog`. Emits `TraceEvent`s as pipes start/finish across processes. Configured via `[pipelex.tracing_config]` (`backend = "ndjson" | "dynamodb"`). Tracing is **enabled by default** and decoupled from Temporal — single-process runs also produce a trace.
- **`pipelex[dynamodb]` extra**: `pip install "pipelex[dynamodb]"` for the DynamoDB event log backend.
- **`writer_id` on `TraceEvent`** (default `"primary"`): every event records which writer (worker / process) produced it, propagated through every backend. Standalone activity worker processes use a distinct `writer_id` so they can emit into the same backend partition as workflow workers without colliding on `(workflow_id, sequence)`. Stamped at construction time (no copy-on-emit). Enables cross-worker dedup and per-writer aggregation.
- **NDJSON multi-writer key scheme**: dedup key is `(workflow_id, writer_id, type, sequence)`; sort key is `(workflow_id, sequence, writer_id)` — sequence is primary so the runner's `UsageReportEvent` does not sort before the router's `PipeStartEvent`. The file-handle cache key includes `writer_id`, so two writers for the same `(pipeline_run_id, workflow_id)` cannot share a stale handle.
- **DynamoDB sort key format**: `EVENT#{workflow_id}#{writer_id}#{sequence:010d}`.
- **Cross-worker `UsageReportEvent` emission from runner processes**: runner processes that never execute `WfPipeRouter.run()` (so `_event_log_contexts` has no entry for the workflow's `lookup_key`) emit usage events through a process-local event log built from `tracing_config`. The fallback log is cached per process via a `threading.Lock`-guarded factory in `pipelex.tracing.activity_event_log` and keyed by a stable per-process `writer_id = f"act_{pid}_{uuid8}"`. A single one-shot warning per process records that the fallback engaged. Specific exceptions (`OSError`, `MissingDependencyError`, `PipelexConfigError`, `botocore.ClientError`) are caught and logged at WARNING — never silently dropped, never re-raised into the inference path.
- **`ReportingManager` registry lookup split into `_get_registry_strict` and `_get_or_create_registry`**: strict raises on miss and is used by `_report_*_job`, so runner processes silently skip the registry add when `open_registry` was never called; or-create is used by `inject_tokens_usages`, the console cost-report path, and `generate_report` for never-opened runs. Activity workers do not accumulate orphan registries.
- **`ContentGeneratorDry` emits `UsageReportEvent`s**: invokes `report_inference_job` with a synthetic `LLMTokensUsage` so dry-run mode produces real events observable through the same backend path as live runs.
- **`GraphSpecAssembler`**: rebuilds a complete `GraphSpec` offline from a stream of `TraceEvent`s — equivalence with the live `GraphTracer` is pinned by tests.
- **`UsageAggregator`**: aggregates per-pipeline LLM/extract/img-gen usage across workers from the event log.
- **Hub DI**: `PipelexHub.set_event_log()` / `get_event_log()` for dependency injection of custom event log backends. `make_event_log()` factory selects the backend from config or hub injection; the 3 prior call sites that hardcoded `NdjsonEventLog` now go through it.

#### Inference error classification

- **`InferenceErrorCategory` enum (`transient`, `configuration`, `content`, `capacity`)** with per-provider helpers that distinguish quota exhaustion from rate limits and detect content-policy violations — covers OpenAI, Anthropic, Google, Mistral, AWS Bedrock, and Pipelex Gateway.
- **All inference workers attach error category + user action**: every LLM, image-gen, extract, and search worker across all providers raises exceptions with an `InferenceErrorCategory` and actionable `user_action` hint.
- **Structured `ErrorReport`**: `PipelexError.to_error_report()` returns a dataclass with error type, category, retryable flag, user-action hint, model, and provider. CLI error handlers consume `to_error_report()` for consistent, structured display.
- **`SecurityError(PipelexError)`**: new base class in `pipelex.base_exceptions` for security-policy violations. `UnsafeSchemaError` now extends it (was `ContentGenerationError`) so security signals are not silently swallowed by domain `except` handlers.

#### Documentation

- New "Under the Hood" pages: `pipe-routing-and-execution.md`, `temporal-integration.md`, `distributed-content-generation.md`. Cover routing/dispatch, Temporal architecture, and the dynamic-model + storage-codec serialization story.
- New `AGENTS.md` at repo root, generated from the same source as `CLAUDE.md` via `make rules`.

#### Other

- **`PipeOutput.graph_assembly_error`**: optional `str` field set when the Temporal `act_assemble_graph` activity raises so consumers can distinguish "graph never produced" from "graph assembly failed". Previously the failure was logged as a warning and `graph_spec` silently stayed `None`.
- **`pipe extract` web URL support** with full test coverage in `tests/integration/pipelex/pipes/pipe_operators/pipe_extract/`.
- **`needs_inference` flag on CLI commands**: non-inference subcommands (e.g. `worker`, `doctor`) skip inference setup, shaving cold-start time.
- **Environment-specific config**: `RunEnvironment` is now loaded from the `ENVIRONMENT` env var (was `ENV`). Accepted values: `local`, `dev`, `staging`, `prod`.

### Changed

- **Tightened inference quota classification patterns** to reduce false positives on auth/setup errors:
  - Anthropic: bare `"credit"` token replaced with `"credit balance"`, `"out of credits"`, `"insufficient credit"`. No longer misclassifies `"your credit card was declined"` or `"we will credit your account"` as quota exhaustion.
  - Google: bare `"billing"` token replaced with `"billing limit"`, `"billing quota"`, `"billing exceeded"`, and `"billing account"`. Continues to match real 429-class messages (`"Billing account is not active"`, `"billing limit reached"`); stops matching unrelated billing-mentioning text.
  - Mistral / Gateway: bare `"billing"` likewise narrowed to `"billing limit"` / `"billing quota"`. Mistral additionally distinguishes `"out of credits"` vs `"insufficient credits"`.
- **Removed duplicate `ContentGenerationError` class**: the unused `pipelex.cogt.content_generation.exceptions.ContentGenerationError` was deleted (had zero external imports). Its subclasses re-parented: `NeitherUrlNorDataError` → `PipelexError`, `UnsafeSchemaError` → new `SecurityError`. The temporal `pipelex.temporal.exceptions.ContentGenerationError` is now the only class with that name.
- **Storage providers unified**: `StorageConfig` flattened to inheritance-based config so providers (`local`, `s3`) share a single shape across delivery and trace storage.
- **`make rules` now generates both `CLAUDE.md` and `AGENTS.md` by default**: the `pipelex.kit_config.preferred_agent_target` setting has been renamed to `preferred_agent_targets` and is now a list. The default is `["claude", "agents"]`. Cursor remains exclusive (`["cursor"]`) and cannot be combined with single-file targets. Downstream projects overriding this setting must rename the key and wrap the value in a list.
- **Cold start trimmed**: heavy SDK imports (`boto3`, `huggingface_hub`, etc.) deferred behind `TYPE_CHECKING` or function-local guards across multiple plugins.
- **Graph viewer updated to mthds-ui v0.3.4**: bumped from v0.3.0 — additional polish atop the resizable detail panel, escape-to-close, sticky header, prompt expand/collapse with copy button, concept refinement display.
- **Default models**: small-vision and creative defaults now point to `gemini-3.0-flash-preview`. Added `claude-4.6-sonnet` and Bedrock token-auth support.
- **`kajson` upgraded** from `0.3.1` to `0.5.0` — required for the dynamic-class source registry that backs schema-to-model reconstruction.
- **README install instructions**: replaced step-by-step Claude Code setup with single copy-paste messages for Claude Code and Codex, added manual install section.

### Fixed

- **Anthropic structured generation no longer flattens all errors to `CONTENT`.** `AnthropicLLMWorker._gen_object` runs requests through `instructor`, which wraps SDK exceptions in `InstructorRetryException`. The previous handler categorized every wrapped error as `CONTENT`, so genuine `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `PermissionDeniedError`, and `AuthenticationError` cases never reached the typed branches — they were reported as content failures (non-retryable) instead of `TRANSIENT` / `CAPACITY` / `CONFIGURATION`. The handler now unwraps `InstructorRetryException.failed_attempts[-1].exception` (with a `__cause__`/`RetryError.last_attempt` fallback) and routes recognized SDK exceptions through a shared categorization helper; truly unrecognized errors keep the `CONTENT` fallback.
- **Managed-deck detection no longer misclassifies user TOMLs.** `_is_managed_deck_filename` previously treated any non-`x_custom_*.toml` as kit-managed, so a user file like `my_overrides.toml` dropped into the deck dir would have been reported (and on `pipelex update` overwritten) as if it were a kit file. Now requires the numbered `^\d+_.*\.toml$` prefix that the kit actually ships.
- **`PipeLLM` output structure prompt used the unresolved concept ref.** When `is_structure_prompt_enabled`, `get_output_structure_prompt` was called with `pipe_run_params.dynamic_output_concept_ref or output_stuff_spec.concept.concept_ref`. The first form can be a bare code (no domain), which broke downstream concept resolution. Now passes the already-resolved `output_stuff_spec.concept.concept_ref` directly.
- **`PIPELEX_NO_DECK_NOTICE` suppression was too lax.** Any non-empty value silenced the deck-staleness notice — including `PIPELEX_NO_DECK_NOTICE=0`, which users might reasonably expect to _enable_ the notice. Now requires the documented `PIPELEX_NO_DECK_NOTICE=1`.
- **Shipped `.kit_manifest.json` carried `kit_version: "0.25.0"`** for the 0.25.1 release, which would have triggered false stale-detection on fresh installs. Bumped to `0.25.1` and re-synced into `pipelex/kit/configs/`.
- **Stored-XSS guard**: HTML escaped in fallback `main_stuff.html`.
- **`GatewayExtractWorker` teardown**: guarded done-callbacks against cancelled tasks to stop noisy teardown errors.
- **URL checker**: 401/403 are now treated as OK for auth-walled URLs.
- **Pipeline duplicate guard**: registering the same pipeline twice raises explicitly instead of silently shadowing.

### Documentation

- **`docs/tools/cli/update.md` no longer claims the deck advisory fires on every CLI invocation.** Clarified that it is suppressed for `login`, `init`, `doctor`, `update`, and `which`.

### Security

- **`schema_to_model` rejects `x-python-*` codegen extensions and restricts `__import__` to an allowlist.** `datamodel-code-generator` honors the `x-python-import` JSON Schema extension by emitting arbitrary `from <module> import <name>` statements with no sanitization. Combined with the prior gap that `_make_restricted_builtins()` did not block `__import__`, an attacker able to plant a crafted `object_class_schema` on a Temporal payload (where `ObjectAssignment.object_class_schema: dict[str, Any]` round-trips untouched) could cause arbitrary modules to be imported during `exec()` of generated code. Two-layer defense added: (1) `_reject_unsafe_schema_extensions` raises `UnsafeSchemaError` if any `x-python-*` key is present anywhere in the schema; (2) `__import__` in the exec namespace is now wrapped to allow only `pydantic`, `typing`, `typing_extensions`, `enum`, `datetime`, `decimal`, `uuid`, `__future__`, `collections`, and `re`.
- **Restricted exec builtins, path sanitization, and atomic fingerprint caching** in the schema-to-model pipeline.
- **CORS hardened on codec server error paths**; no leaked exception strings; prefix guards on storage URIs.

## [v0.25.2] - 2026-04-30

### Fixed

- **`pipelex update` no longer flags user-added deck files for removal.** The "managed file" filter accepted any `.toml` not prefixed with `x_custom_`, so project-local additions like `pipelex-cookbook`'s `cookbook.toml` were reported as "removed upstream" with action "back up + remove". The filter now matches the documented numbered convention only (`<digits>_*.toml`); any other filename — `cookbook.toml`, `x_custom_*.toml`, etc. — is invisible to the update planner.

## [v0.25.1] - 2026-04-29

### Added

- **`pipelex update` command + model-deck staleness detection.** New top-level command refreshes the installed model deck (`~/.pipelex/inference/deck/`) to match the kit shipped with the running pipelex version. Tracks per-file SHA-256 hashes plus the kit version in a `.kit_manifest.json` written next to the deck files. Supports `--dry-run`, `--yes` (non-interactive), `--no-backup` (skip `.bak` files for locally-modified deck files), and `--local` (project-local deck instead of global).
- **Boot-time deck staleness warn.** Every `pipelex` CLI invocation prints a one-line yellow advisory when the installed deck's recorded kit version is older than the running pipelex (or when no manifest exists yet). Cost is one file read + one string compare. Suppress with `PIPELEX_NO_DECK_NOTICE=1`. Skipped automatically for `pipelex login`, `init`, `doctor`, `update`, and `which`.
- **`pipelex doctor` deck section.** Reports per-file deck status (`up_to_date`, `kit_added`, `kit_removed`, `clean_behind`, `locally_modified`) and offers `pipelex update` as an auto-fix under `--fix`.
- **Manifest written by `pipelex init`.** Fresh installs land with a current `.kit_manifest.json` so future updates can detect drift cleanly.
- **`--dynamic-output-concept` / `-O` flag on `pipelex run`.** All three subcommands (`run bundle`, `run pipe`, `run method`) accept a concept ref (e.g. `document_qa.ReferenceCount`) used to resolve a pipe whose output is declared as `Dynamic`. Threaded through `_run_core.execute_run` to `PipelexRunner.execute_pipeline(dynamic_output_concept_ref=...)`. Until now, Dynamic-output pipes were only callable from the Python runner.
- **Line-length-safe wrapping in the structures generator.** `pipelex build structures` now wraps long descriptions so every emitted line stays under the 150-char ruff limit. Long class docstrings become a multi-line triple-quoted block; long Field descriptions become a parenthesized implicit-string-concatenation block (`description=("first chunk " "second chunk")`). Short descriptions still emit the compact single-line form. New unit tests in `tests/unit/pipelex/core/concepts/structure_generation/test_structure_generator_wrapping.py` cover both lengths and the combined long-everything case. Previously, descriptions above ~140 chars produced files that failed `ruff check` with E501.

### Changed

- **Numbered deck files (`N_*_deck.toml`) are pipelex-managed.** Each file now carries a header banner explaining that customizations belong in `x_custom_*.toml` (which pipelex never tracks or overwrites). Local edits to numbered files are preserved with a timestamped `.bak.<UTC-timestamp>` backup on `pipelex update` but will not survive future updates.

### Fixed

- **`PipeLLM` Dynamic-output detection compared the wrong fields.** `pipe_llm.py` checked `self.output.concept.code == "native.Dynamic"`, but `concept.code` is the bare code (`"Dynamic"`) not the qualified ref. The check never matched, so when a caller passed `dynamic_output_concept_ref` for a `Dynamic`-output pipe, the resolver branch was skipped silently: the output structure stayed `DynamicContent` (an empty `StuffContent` subclass), the LLM produced JSON shaped like the requested concept, and the result deserialized to `{}`. Detection now uses `concept.code == NativeConceptCode.DYNAMIC and concept.domain_code == SpecialDomain.NATIVE`.

- **Dynamic-output concept resolution rejected qualified refs.** When the runtime override was supplied (e.g. `"document_qa.ReferenceCount"`), the previous code called `make_concept_ref_with_domain(domain_code=self.domain_code, concept_code=output_concept_ref)`, producing `"document_qa.document_qa.ReferenceCount"` and a missing-concept lookup. Now uses `make_concept_ref_with_domain_from_concept_ref_or_code`, which extracts the domain from the input when it's already qualified and falls back to the pipe's domain only for bare codes. Callers can pass either form.

## [v0.25.0] - 2026-04-28

### Added

- **GPT-5.5 model support.** New `gpt-5.5` entry on the `openai`, `azure_openai` and gateway backends.

- **`gpt-image-2` image generation (OpenAI).** New model entry with img-gen routing and constraints on `openai`, `azure_openai`.

### Fixed

- **PDF input declared on Azure OpenAI and gateway for the GPT-5.4 series.** `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.4-pro` (and `gpt-5.5`) now advertise `pdf` in their `inputs` on `azure_openai` and the gateway, matching the existing OpenAI direct entries. Verified end-to-end with live document tests against both backends.

### Changed

- **Img-gen taxonomies aligned for `gpt-image-2`.** Convention: `gpt_image` for taxonomies/values shared across all OpenAI GPT Image models (legacy + gpt-image-2); `gpt_image_legacy` when the value applies only to gpt-image-1/-1-mini/-1.5 (gpt-image-2 uses `unavailable` where a legacy-only option does not apply). Renames:
  - `AspectRatioTaxonomy.OPENAI_GPT_IMAGE_LEGACY` → `GPT_IMAGE_LEGACY` (value `"openai_gpt_image_legacy"` → `"gpt_image_legacy"`)
  - `AspectRatioTaxonomy.OPENAI_GPT_IMAGE_2` → `GPT_IMAGE_2` (value `"openai_gpt_image_2"` → `"gpt_image_2"`)
  - `OutputFormatTaxonomy.GPT` → `GPT_IMAGE_LEGACY` (value `"gpt"` → `"gpt_image_legacy"`)
  - `OutputCompressionTaxonomy.GPT_IMAGE` → `GPT_IMAGE_LEGACY` (value `"gpt_image"` → `"gpt_image_legacy"`)
  - `InputFidelityTaxonomy.OPENAI_IMAGE` → `GPT_IMAGE_LEGACY` (value `"openai_image"` → `"gpt_image_legacy"`)
  - `NumImagesTaxonomy.GPT` → `GPT_IMAGE` (value `"gpt"` → `"gpt_image"`)
  - `InferenceTaxonomy.GPT` → `GPT_IMAGE` (value `"gpt"` → `"gpt_image"`)
  - Removed dead `AspectRatioTaxonomy.GPT`.
  - `InputImagesTaxonomy.GPT_IMAGE` unchanged (already correct — shared across legacy and gpt-image-2).

- **HuggingFace and Fal img-gen workers honor `model_choice` rule.** `huggingface_img_gen` and `fal` workers now pop `"model"` from `args_dict` instead of hardcoding `inference_model.model_id`, mirroring how `prompt` is already extracted. The `model_choice = "model_id"` rule is now required on every model under these backends; missing it raises `ImgGenParameterError` at call time. Rules added to `qwen-image` (HF) and to all Fal models (`flux-pro`, `flux-pro/v1.1`, `flux-pro/v1.1-ultra`, `flux-2`, `fast-lightning-sdxl`).

## [v0.24.1] - 2026-04-22

### Security

- **lxml floor `>=6.1.0`** to patch CVE-2026-41066 (GHSA-vfmq-68hx-4jfw): default configuration of `iterparse()` and `ETCompatXMLParser()` allowed XXE to local files (`resolve_entities=True`). lxml 6.1.0 changes the default to `resolve_entities='internal'`. Transitive via `docling`; floor added to the `docling` extra in `pyproject.toml` so downstream installs of `pipelex[docling]` cannot resolve a vulnerable version.
- **cryptography floor `>=46.0.7`** to patch CVE-2026-39892 (GHSA-p423-j2cm-9vmq): non-contiguous Python buffers passed to hashing APIs (e.g. `Hash.update()`) could read past the end of the buffer on Python >3.11. Transitive via `google-auth` (pulled by `google`, `gcp-storage`, `google-genai` extras) and `moto` (dev). Floor added to each affected extra in `pyproject.toml` — previous bump was lockfile-only, which did not protect downstream users resolving fresh from PyPI metadata.
- **pytest bumped to 9.0.3** to patch CVE-2025-71176 (GHSA-6w46-j5rx-g56g): vulnerable `/tmp/pytest-of-{user}` directory handling on UNIX could let a local user cause DoS or gain privileges. Dev-only dependency; `pyproject.toml` minimum bumped from `>=9.0.2` to `>=9.0.3`.
- **transformers CVE-2026-1839 (GHSA-69w3-r845-3855) risk-accepted, alert dismissed.** The vulnerability requires calling `transformers.Trainer._load_rng_state()` with an attacker-controlled checkpoint file. Pipelex only pulls `transformers` transitively through `docling-ibm-models` for PDF layout inference; the `Trainer` class is never imported or executed. Upgrade path is blocked upstream: `docling-ibm-models` 3.13.0 pins `transformers!=5.0.*,!=5.1.*,!=5.2.*,!=5.3.*,<6.0.0,>=4.42.0`, explicitly excluding the patched 5.0.0rc3 release. Revisit when `docling-ibm-models` adds support for `transformers>=5.4`.
- **Release-publishing GitHub Actions pinned to SHAs**: `pypa/gh-action-pypi-publish` and `sigstore/gh-action-sigstore-python` in `publish-pypi.yml` are now pinned to full commit SHAs (version kept as a trailing comment) so a compromised tag on a third-party action cannot silently alter a PyPI release. Dependabot keeps them fresh.
- **`.github/dependabot.yml` added**: declares `pip` and `github-actions` ecosystems, weekly cadence, with dev and runtime deps grouped to reduce PR noise. Security updates fire immediately regardless of schedule.
- **`dependency-review.yml` workflow added**: runs GitHub's `dependency-review-action` on PRs to `main`, `dev`, and release branches. Fails the PR if it introduces a dependency with a moderate-or-higher CVE. Respects the existing transformers (GHSA-69w3-r845-3855) risk-acceptance via `allow-ghsas`. Enable as a required status check in branch protection for `main` to block vulnerable merges.

## [v0.24.0] - 2026-04-16

### Added

- **claude-opus-4-7 model**: Registered on anthropic, bedrock, and gateway backends with 128k max output tokens, $5/$25 per MTok pricing, adaptive thinking, and PDF/vision support
- **`XHIGH` reasoning effort level**: New effort tier across all providers, mapped to Anthropic's `xhigh` (recommended for coding/agentic work), OpenAI's `xhigh`, and best-available equivalents for Google and Mistral
- **`TEMPERATURE_UNSUPPORTED` constraint**: New listed constraint for models that reject sampling parameters entirely, checked in both Anthropic and OpenAI completions workers
- **claude-4.6-sonnet model**: Registered on anthropic, bedrock, and gateway backends
- **LLM deck cheap presets**: Added cheap variants for writing-factual, retrieval, and engineering-code presets, with retrieval tiers from `gemini-2.5-flash-lite` to `claude-4.7-opus`
- **Bedrock bearer token authentication**: New `bedrock_access_variant` config option supports `"bedrock_token"` auth using `AWS_BEARER_TOKEN_BEDROCK` env var, alongside the existing `"aws_access"` method (default)

### Changed

- **Anthropic adaptive thinking rejects `reasoning_budget`**: `_build_thinking_params_for_budget` now raises `LLMCapabilityError` for adaptive thinking models, guiding users to `reasoning_effort` instead — extended thinking (`type: "enabled"`) is removed on Opus 4.7+
- **LLM deck**: Updated `best-claude` alias to `claude-4.7-opus`, switched `img-gen-prompting-cheap` to `@default-small-creative`, removed deprecated builder presets, standardized cheap preset descriptions
- **Google `MINIMAL` reasoning level**: `ReasoningEffort.MINIMAL` now maps to Google's `ThinkingLevel.MINIMAL` (was previously collapsed to `LOW`); `GoogleThinkingLevel` enum gains `MINIMAL` and the default `google_config.effort_to_level_map` updates accordingly

## [v0.23.9] - 2026-04-14

### Added

- **Graph UI asset sync workflow**: `package.json` pins `@pipelex/mthds-ui` to a git tag, `make sync-graph-ui` clones and builds standalone assets, `make check-graph-ui-sync` verifies version alignment
- **CI check**: `graph-ui-check.yml` workflow validates graph viewer assets match the pinned version on PRs to main
- **`/update-graph-ui` skill**: automates bumping the mthds-ui version, syncing assets, and running tests

### Changed

- **Graph viewer updated to mthds-ui v0.3.0**: resizable detail panel, escape-to-close, sticky header, prompt expand/collapse with copy button, concept refinement display
- **README install instructions**: Replaced step-by-step Claude Code setup with single copy-paste messages for Claude Code and Codex, added manual install section

## [v0.23.8] - 2026-04-07

### Changed

- **Standalone ReactFlow graph rendering**: Replaced Jinja2 template-based HTML generation with a single standalone HTML asset, simplifying the graph rendering pipeline and removing the Jinja2 template dependency for ReactFlow output.

## [v0.23.7] - 2026-04-06

### Added

- **Graph tracing for pipe run data**: Pipe run data and concept are now included inside the flowchart graph spec, enabling richer visualization of pipe execution results across all pipe types (LLM, extract, compose, search, image gen, sequence, condition, batch, parallel).
- **Assignment pipe**: New `pipe_assignment` pattern for direct value assignment within pipe execution.

## [v0.23.6] - 2026-04-06

### Changed

- **Sub-pipe input normalization**: Silently drop unsupported `inputs` field from step/branch dicts instead of logging a warning.

## [v0.23.5] - 2026-04-04

### Added

- **Gateway config**: Introduced `GatewayConfig` to bundle gateway model specs with AWS region, propagating it through the backend library so bedrock backends use the correct region.
- **Config coverage tests**: Integration tests that validate one model per Portkey config for each model type (LLM, image gen, extract, search), with `all_configs_gw` test profile and `make ticc` target.
- **nano-banana-2 model**: Added `gemini-3.1-flash-image-preview` as `nano-banana-2` with updated Google image gen costs.
- **DeepSeek models on bedrock**: Added DeepSeek models to the bedrock backend configuration.

### Changed

- **Image gen deck aliases**: Updated aliases to nano-banana model variants and removed `flux-2-pro`.
- **Remote config**: Bumped to v08.
- **Gateway model docs**: Regenerated, removing retired models (claude-3.7-sonnet, deepseek-v3.1, deepseek-v3.2-speciale, flux-2-pro).

### Fixed

- **deepseek-v3.1 structured output**: Removed unsupported `structured` output capability from the bedrock deepseek-v3.1 model spec — the `bedrock_aioboto3` worker does not implement object generation, so structured calls would fail at runtime.

## [v0.23.4] - 2026-04-02

### Changed

- **Pipe spec output alias**: Removed `output_type` alias from `parse_pipe_spec`, keeping only `output_concept` as the single alias for the `output` field. Simplified the alias resolution logic accordingly.

## [v0.23.3] - 2026-04-02

### Changed

- **Pipe spec output aliases**: `parse_pipe_spec` now accepts `output_concept` and `output_type` as aliases for the `output` field, with smart fallback when both alias and canonical field are present.

### Fixed

- **Gateway terms check**: Terms acceptance is now only required for inference operations, not for read-only operations like model spec fetching during validation.

## [v0.23.2] - 2026-03-30

### Changed

- **Claude Code plugin install command**: Fixed as → `/plugin install mthds@mthds-plugins` across README and docs.
- **Claude Code plugin reload instructions**: Added `/reload-plugins` as the primary method to activate the plugin, with exit/reopen as fallback.

## [v0.23.1] - 2026-03-30

### Changed

- **Concept spec: `concept_code` replaces `the_concept_code`** as the canonical field name in concept specs and working memory factory.
- **Shared spec parsing**: `concept_cmd` and `pipe_cmd` now delegate to the shared `parse_concept_spec` and `parse_pipe_spec` helpers, removing stale duplicate parsing logic while preserving compatibility and fixing alias/dict-mutation edge cases.
- **`concept_ref` / `pipe_ref` aliases**: `parse_concept_spec` and `parse_pipe_spec` now accept `concept_ref` and `pipe_ref` as input aliases for better AI-agent compatibility.
- **Replace `pip` with `uv`** in install commands across config files and error messages.
- **Docs links**: Updated mthds.ai links to include `/latest/` path.

### Fixed

- **Concept alias bug**: Concept alias handling previously listed `concept_code` as an alias instead of `the_concept_code`, causing valid input to be silently dropped. Fixed by the new shared `parse_concept_spec` helper.

## [v0.23.0] - 2026-03-29

### Added

- **Builder Operations module** (`pipelex/builder/operations/`): New standalone operation functions for the build agent — `concept_ops`, `inputs_ops`, `models_ops`, `output_ops`, `pipe_ops`, `runner_code_ops`, `validate_ops`. These decouple build logic from CLI commands so it can be reused by agents and the API.
- **`dry_run_pipeline`** (`pipelex/pipe_run/dry_run_pipeline.py`): New shared entrypoint to dry-run a pipeline from MTHDS contents and produce a `GraphSpec`. Used by both CLI graph commands and the API.

### Changed

- **`mthds_content` → `mthds_contents`**: Unified singular `mthds_content: str | None` into `mthds_contents: list[str] | None` across `PipelexRunner`, `pipeline_run_setup`, `validate_bundle`, CLI commands, and builder operations. Callers now pass a list of bundle content strings.
- **`bundle_uri` → `bundle_uris`**: Renamed `bundle_uri: str | None` to `bundle_uris: list[str] | None` across `PipelexRunner.__init__`, `pipeline_run_setup`, `dry_run_pipeline`, and all CLI call sites. Multiple bundles can now be loaded simultaneously.
- **Bump `mthds` dependency** to `>=0.2.0` (from `>=0.1.1`) to match the updated `RunnerProtocol` interface.
- **Graph rendering refactor**: Extracted dry-run logic from `graph_rendering._dry_run_bundle` into the new shared `dry_run_pipeline` function.
- **Agent CLI inputs**: Refactored `_inputs_core` to delegate to `builder.operations.inputs_ops.build_inputs_for_pipe` instead of duplicating bundle validation and input rendering logic.
- **Agent CLI run**: Added graph generation support with ReactFlow HTML output and side-effect metadata tracking in `_run_core`.
- **Deduplicate `models_cmd` → `models_ops`**: `models_cmd.py` is now a thin CLI wrapper delegating to `list_models()` and `format_models_markdown()` in `models_ops.py`, consistent with other agent CLI commands.

### Removed

- **`BuilderLoop`** and its iterative build-validate-fix cycle (`builder_loop.py`, `builder.py`, `builder_errors.py`). The build-agent CLI now drives spec construction directly.
- **`pipelex build pipe`** CLI command and associated MTHDS workflow files (`builder.mthds`, `agentic_builder.mthds`, `pipe_design.mthds`, `concept_fixer.mthds`, `synthesize_image.mthds`).
- **`pipelex-tools` runtime dependency**: Moved to dev-only dependency; `plxt` is now invoked via subprocess passthrough.

- **Talent system**: Removed talent enums, config mappings (`talent_preset_mappings`), and talent preset tests. Pipe specs accept model presets directly via the `model` field, making the talent indirection unnecessary.

### Fixed

- **Per-bundle dedup in pipeline run setup**: Fixed duplicate bundle loading when the same bundle appears in multiple sources.
- **HTTP utils**: Use HEAD-first strategy for URL validation to avoid downloading large payloads unnecessarily.
- **`library_dirs` passthrough**: Fixed `library_dirs` not being forwarded in builder operations (`inputs_ops`, `validate_ops`).
- **Dry-run status**: Fixed validation status reporting for dry-run results.

## [v0.22.0] - 2026-03-25

### Added

- **MiniMax Backend Support**: Added integration for MiniMax models (M2, M2.1, M2.5, M2.7 series including high-speed variants) with an `all_minimax` routing profile.
- **`check-model` Agent CLI Command**: Introduced `pipelex-agent check-model` to validate model references. Provides fuzzy matching suggestions, cross-collection suggestions, and wrong-sigil hints when an invalid model is provided.
- **Domain-Qualified Pipe References (`pipe_ref`)**: Added a `pipe_ref` property (`domain.code`) as the primary pipe index, allowing pipes with the same code to coexist across different domains. Bare code lookups remain supported as a fallback when unambiguous.
- **Duplicate Concept Detection**: Added validation to warn about duplicate concept declarations across different bundles within the same library.
- **Shared TOML Formatter**: Extracted a shared `format_toml_string` utility for consistent multi-line string formatting across the MTHDS factory and Agent CLI.

### Changed

- **Agent CLI Output Formats**: Overhauled `pipelex-agent` CLI output for LLM agents: `concept` and `pipe` commands now output raw TOML to stdout; `models` and `doctor` commands output Markdown by default (JSON still available via `--format json`).
- **Unified `model` Field in Pipe Specs**: Replaced type-specific talent fields (`llm_talent`, `extract_talent`, `img_gen_talent`, `search_talent`) with a single `model` field accepting model presets directly. Talent mappings removed from `pipelex-agent models` output accordingly.
- **Initialization Checks**: `check_is_initialized` now additionally verifies the presence of `plxt.toml`.
- **Documentation & Handoffs**: Updated Claude Code skills plugin docs, CLI references.

### Fixed

- **Domain Metadata Conflicts**: Loading multiple bundles declaring the same domain with differing descriptions or system prompts now emits a warning and keeps the first declaration instead of throwing an error.
- **Cross-Domain Execution Tracking**: Pipe controllers and the dry-run engine now track visited pipes using `pipe_ref` instead of bare codes, preventing false-positive loop detections when crossing domains.

### Removed

- **`assemble` Agent CLI Command**: Removed the `pipelex-agent assemble` command.

## [v0.21.0] - 2026-03-19

### Added

- **Web Page Extraction:** `PipeExtract` now supports extracting content from web pages via the new `linkup-fetch` model, with `render_js` and `include_raw_html` parameters. Added `@default-extract-web-page` alias to the extraction model deck.
- **New AI Models:** OpenAI / Azure: `gpt-5.4`, `gpt-5.4-pro`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.2-codex`; Mistral: `mistral-small-4`
- **DocumentContent Enhancements:** Added `public_url`, `filename`, `title`, and `snippet` fields to support web pages and search citations.
- **AI Agent Documentation:** Integrated `mkdocs-llmstxt-md` plugin to generate `/llms.txt` and `/llms-full.txt` for AI agents.
- **Claude Code Skills:** Added internal `.claude/skills` (`add-model`, `test-model`) for registering and testing new inference models.

### Changed

- **Web Fetching → Extract Domain:** Moved web fetching from the Search domain into the Extract domain. Replaced `FetchJob`, `FetchWorkerAbstract`, and related classes with native handling in `PipeExtract` and a new `GatewayExtractWorker`. Split `LinkupWorker` into dedicated `LinkupSearchWorker` and `LinkupExtractWorker`.
- **Search Results Unification:** `SearchResultContent` now uses `DocumentContent` instead of the removed `SearchSourceContent`.
- **Search Job Refactoring:** Encapsulated `SearchJob` parameters into a new `SearchJobParams` object; updated `SearchWorkerAbstract` signatures accordingly.
- **Documentation Build:** Replaced inline HTML generation with a `docs/root-index.html` template. Updated `robots.txt` to allow AI crawler access to `llms.txt`.

### Fixed

- **Remote Image Fetching:** Added error handling (`httpx.HTTPStatusError`, `httpx.RequestError`) in `GeneratedContentFactory` when downloading remote images, with graceful fallback to using the original URL as `public_url`.

### Removed

- **`page_image_captions` parameter:** Removed from `PipeExtractSpec` and `ExtractJobParams`.

## [v0.20.13] - 2026-03-16

### Removed

- Remove unused `ViewSpec` class and related code from graph/reactflow — dead code that was no longer referenced.

## [v0.20.12] - 2026-03-16

### Fixed

- Fix Google "Sitemap could not be read" error by adding `Allow: /sitemap.xml` to `ROOT_ROBOTS_TXT` — `Disallow: /` was blocking Googlebot from fetching the root sitemap even though `Sitemap:` pointed to it.

## [v0.20.11] - 2026-03-16

### Fixed

- Fix `docs-deploy-root` silently failing due to shell comments breaking the `\` continuation chain in the Makefile recipe — root `sitemap.xml` and updated `robots.txt` were never deployed in v0.20.10.

## [v0.20.10] - 2026-03-16

### Fixed

- Fix sitemap double-path bug (`latest/0.20.9/page/`) caused by `site_url` including `/latest/` while mike also inserts the version prefix during deployment.
- Override canonical URLs, `og:url`, and JSON-LD `url` to always point to `/latest/` via template override.
- Add root-level `sitemap.xml` generation with `/latest/` URLs to `docs-deploy-root`.

## [v0.20.9] - 2026-03-16

### Changed

- Reorganize documentation site architecture and navigation.
- Add SEO meta descriptions to all doc pages.
- Redesign README: lead with value, collapse details.

## [v0.20.8] - 2026-03-13

- Add `needs_model_specs=True` to agent CLI run and models commands.

## [v0.20.7] - 2026-03-12

- Bump `mthds` dependency to `>=0.1.1`.

## [v0.20.6] - 2026-03-12

### Added

- **`needs_model_specs` parameter**: New option on `Pipelex.make()` and CLI factories to load real gateway model specs without enabling full inference. Validation commands (`pipelex validate`, `pipelex-agent validate`) now fetch live model specs, improving accuracy of pipe/method/bundle validation.

### Removed

- **Deprecated `pipelex_inference` backend**: Removed all traces of the legacy backend — config files, enum values, migration logic, deprecation warnings, and documentation admonitions. The transition to `pipelex_gateway` is complete.

### Fixed

- **`pipelex init inference --local`**: Fixed file filter to also copy `.md` files (e.g. Gateway model lists) to the backends directory, not just `.toml` files.
- **Gateway terms persistence**: Hardened failure handling — when terms acceptance can't be persisted (e.g. unwritable global directory), gateway is now properly disabled in `backends.toml` as a fallback, preventing `GatewayTermsNotAcceptedError` at runtime.

## [v0.20.5] - 2026-03-09

### Changed

- **Config paths use `pathlib.Path`**: All `ConfigLoader` properties and methods now return `Path` instead of `str`. Consumer code across the config system (doctor, init, backends, routing, credentials, telemetry, agent CLI) updated accordingly.
- **Layered config resolution for `pipelex doctor` and `pipelex init`**: Config files are now resolved with project-first, global-fallback layering per file. Fixed `replace_backend_file` using CWD-relative path that broke when run from another directory.
- **Gateway terms are explicitly global**: `update_service_terms_acceptance` now targets `~/.pipelex/` by default, since gateway terms are a user-level agreement, not project-level.
- Tweaks to the `pipelex-agent` CLI to play well with the Claude Code plugin and skills.

## [v0.20.4] - 2026-03-04

- Improve README.md instructions for Claude Code and MTHDS skills.

## [v0.20.3] - 2026-03-04

### Fixed

- Rewrote README with updated CV Batch Screening example, corrected CLI command, inputs schema, Python snippet, and pipe descriptions.

## [v0.20.2] - 2026-03-04

### Fixed

- Fixed removal of the --reset flag from the init command docs.
- Fixed the name of the `PipeSequence` results within a batch.

## [v0.20.1] - 2026-03-03

### Changed

- **Cost Report Consistency**: Renamed `platform_llm_id` field to `platform_model_id` in `LLMTokenCostReport`, aligning with all other report types (ImgGen, Extract, Search, Fetch) that already use `platform_model_id`.
- **Test Coverage**: Added `linkup` backend to the coverage test profile.

## [v0.20.0] - 2026-03-03

### Added

- **CLI Authentication**: `pipelex login` command that initiates a browser-based OAuth flow (GitHub/Google) to authenticate with the Pipelex Gateway and save the API key locally.
- **Search Filtering**: `from_date`, `to_date`, `include_domains`, and `exclude_domains` options on the `PipeSearch` operator, routed through a new `GatewaySearchWorker`.
- **Expanded Cost Reporting**: Token usage and cost tracking now covers Search, Fetch, Extraction, and Image Generation jobs, in addition to LLMs.
- **New Models**: Added `gpt-5.3-codex` (text, images, pdf inputs) and `nano-banana-2`.

### Changed

- **Search Configuration**: Renamed Linkup model IDs from `linkup/standard` to `linkup-standard` (and `deep` variant), simplified presets to `$standard` and `$deep`.
- **Default Pipeline Execution**: Changed from `in_memory` to `local`.
- **Default Extraction Model**: Changed from `mistral-document-ai-2505` to `azure-document-intelligence`; removed `mistral-document-ai-2505` from the supported Gateway models list.
- **Content Handling**: `TextAndImagesContent` now supports an optional `raw_html` field.
- **Dev Experience**: `Makefile` commands (`generate-mthds-schema`, `update-gateway-models`) run in quiet mode by default.

## [v0.19.0] - 2026-03-02

### Added

- **Web Search Integration**: Introduced a new `PipeSearch` operator, native support for Linkup as a search backend provider, `SearchResult` and `SearchResultContent` concepts for handling answers with citations, and Model Deck support for search models.
- **Graph View Generation**: Added a `--view` option to `pipelex validate bundle` that generates a `ViewSpec` JSON (compatible with ReactFlow) for client-side graph rendering without writing files to disk.

### Changed

- **Test Configuration**: Added a `search` pytest marker, excluded from default test runs.
- `mthds` bumped to `>=0.1.0`.
- `pipelex-tools` bumped to `>=0.2.3`.
- `linkup-sdk>=0.12.0` added as optional dependency for the Linkup search provider.

## [v0.18.6] - 2026-03-01

### Added

- **GitHub URL support for CLI method targets** — All CLI commands accepting a method target (`pipelex validate method`, `pipelex run method`, `pipelex build inputs method`, etc.) now accept a public GitHub URL (e.g., `https://github.com/org/repo/tree/main/methods/my-method`). The repository is cloned automatically, and the method package is discovered and validated. Subdirectory URLs are supported.
- **Local path support for CLI method targets** — Method targets can now also be local filesystem paths pointing to a directory containing a `METHODS.toml`. This works for both `pipelex` and `pipelex-agent` CLIs.
- Added `clone_default_branch()` in `mthds` package for shallow-cloning a git repository's default branch.

## [v0.18.5] - 2026-03-01

### Changed

- `pipelex-agent assemble` command now outputs JSON to stdout by default.

## [v0.18.4] - 2026-03-01

### Added

- Introduced a **lenient loading mode** for `InferenceBackendLibrary` and `RoutingProfileLoader`: when enabled, logs warnings instead of raising errors for missing credentials, variable fallback failures, or disabled backends — skipping individual backends gracefully rather than crashing the entire load process.
- Added `needs_inference` parameter to `Pipelex.make`, `make_pipelex_for_cli`, and `make_pipelex_for_agent_cli` to control whether full inference setup (credentials, gateway checks, telemetry) is required.
- Added `needs_inference_in_pipelex` helper to `shared_pytest_plugins` to replace the inverted logic of the previous helper.

### Changed

- **CLI Robustness:** `pipelex build`, `validate`, `show`, `graph`, `inputs`, and `which` commands now run with `needs_inference=False`, allowing them to succeed even when backend credentials are missing or incomplete.
- Refactored `Pipelex.make`: renamed `disable_inference` to `needs_inference` (default `True`). When `False`, enables lenient backend loading, uses a dummy remote config, disables telemetry, and skips `validate_model_deck()`.

### Deprecated

- `is_inference_disabled_in_pipelex` in `shared_pytest_plugins` — migrate to `needs_inference_in_pipelex`.

## [v0.18.3] - 2026-02-27

- Updated `pipelex-tools` dependency to `0.2.1`

## [v0.18.2] - 2026-02-27

### Added

- **Inputs path resolution** — Relative file paths (e.g., `"url": "data/invoice.pdf"`) inside `inputs.json` are now resolved relative to the inputs file's parent directory, making bundle directories self-contained and portable. Applies to both user and agent CLIs. Handles HTTP, data:, pipelex-storage://, and absolute paths by leaving them unchanged.

### Changed

- **`pipelex-agent init` defaults to local project** — The `init` command now targets the project-level `.pipelex/` directory by default (at detected project root) instead of auto-detecting. The `--local` flag has been removed. Use `--global`/`-g` to target `~/.pipelex/`. Errors out if no project root is found without `-g`.
- **`pipelex-agent doctor` supports `--global`/`-g`** — The `doctor` command now accepts `--global`/`-g` to check the global `~/.pipelex/` directory. Without the flag, it auto-detects project `.pipelex/` if present, else falls back to `~/.pipelex/`.
- **`pipelex-agent init --config` improved help** — The `--config` option help text now shows the JSON schema with field types upfront for better discoverability.

### Fixed

- **`pipelex-agent init -g` service agreement** — The `--global` flag now correctly writes the gateway service terms acceptance (`pipelex_service.toml`) to the target directory instead of always writing to the auto-detected config dir.
- **Deterministic file discovery order** — `find_files_in_dir` now sorts `rglob`/`glob` results for consistent ordering across platforms and Python versions. On Linux with Python < 3.13, `rglob` returned filesystem-order results, which could cause `test_validate_all` to fail by picking up a test package's `METHODS.toml` before pipelex internal bundles.

## [v0.18.1] - 2026-02-25

### Fixed

- Fix docs deployment failure caused by shell metacharacters (parentheses) in Makefile `PRINT_TITLE` macro argument for `docs-deploy-root` target
- Fix `mike` unable to find `mkdocs` binary by adding venv `bin/` to PATH in all mike-based Makefile targets

## [v0.18.0] - 2026-02-25

**Highlights:**

- **Pipelex Gateway** — The deprecated `pipelex_inference` backend is now replaced by `pipelex_gateway`, featuring remote model configuration fetching so you always have access to the latest models without updating Pipelex.

  **Getting your API key:**
  1. Get your API key at [app.pipelex.com](https://app.pipelex.com/)
  2. Add it to your `.env` file: `PIPELEX_GATEWAY_API_KEY=your-key-here`

  **Gateway Supported models — included with the Free API Key**
  - **Language Models (LLM):**
    - OpenAI: all models up to GPT-5.2 and Codex
    - Anthropic: Claude 3.7 Sonnet through Claude 4.5 Haiku/Sonnet/Opus
    - Google: Gemini 2.0/2.5 Flash, Gemini 2.5 Pro, Gemini 3.0 Flash/Pro
    - xAI: Grok 3/mini, Grok 4 (+ fast reasoning variants)
    - Open-source: Mistral Large 3, DeepSeek v3.1/3.2/Speciale, GPT-OSS 20B/120B1, Kimi K2, Phi-4, Qwen3-VL 235B
  - **Document Extraction:** Mistral Document AI, Azure Document Intelligence, DeepSeek OCR
  - **Image Generation:** GPT-Image 1/1.5, Flux 2 Pro, Nano Banana/Pro

  **Accepting the Terms of Service:**

  When you run `pipelex init`, you'll be prompted to accept the Gateway terms of service. By using Pipelex Gateway, telemetry is automatically enabled and identified by your API key (hashed for security) to monitor service quality and enforce fair usage. **We only collect technical data** (model names, token counts, latency, error rates)—never your prompts, completions, or business data. See our [Privacy Policy](https://go.pipelex.com/privacy-policy).

  **⚠️ Migration deadline:** If you were using `pipelex_inference`, please migrate soon—the legacy service will be shut down within few days. Get your new Gateway key at [app.pipelex.com](https://app.pipelex.com/).

- **Execution Graph Visualization System** (preview feature) — Comprehensive tracing and visualization for pipeline executions.

  **CLI:** `--graph` flag on `pipelex run` generates execution graphs. New `pipelex graph render <graph.json>` command for post-run rendering.

  **Viewers:** Interactive ReactFlow viewer (`reactflow.html`) with pan/zoom and node inspector. Mermaid diagrams (`mermaidflow.html`) with subgraphs and clickable nodes.

  **Makefile:** `make view-graph` (`vg`) and `make serve-graph` (`sg`) to start a local graph viewer.

- **Pydantic Structure Generation** — Two new CLI commands bridge Pipelex's declarative concepts with your Python code:

  **`pipelex build structures /library_dir/`** — Generates Pydantic models from all concept definitions found in the specified library directory. Now you have your structures as Python code: you can iterate on them, add custom validation functions, or use them as type hints in your code.

  **`pipelex build runner`** — Now automatically generates both the Python runner file AND the required Pydantic structures. When you run this command, it creates a complete, ready-to-execute Python script that imports the generated structures, so you can immediately use typed objects in your pipeline code.

  See the [Build Commands documentation](https://docs.pipelex.com/latest/tools/cli/build/) for usage examples.

- **New Backends & Models**:
  - **Hugging Face Inference** — Support for Hugging Face Inference API, including `qwen-image` text-to-image model.
  - Google `gemini-3.0-flash-preview`
  - Mistral OCR latest model `mistral-ocr-2512`
  - **Scaleway** inference provider support for open-source models
  - **Portkey AI** backend integration for unified access to multiple models through a single API key

- **Document Support in `PipeLLM`** — Include `Document` objects (like PDFs) directly in prompts using `@variable` or `$variable` syntax. Supports single documents, multiple documents, and lists, combinable with text and image inputs.

- **`PipeCompose` Construct Mode** — New mode for deterministically building `StructuredContent` objects without an LLM. Compose fields from working memory variables, fixed values, templates, and nested structures.

- **Content Storage System** — Configurable storage for generated artifacts (images, extracted pages). Supports `local` filesystem (`.pipelex/storage/`), `in_memory`, **AWS S3** (`pip install pipelex[s3]`), and **Google Cloud Storage** (`pip install pipelex[gcp-storage]`). Cloud providers support both public URLs and time-limited signed URLs. Content referenced via stable `pipelex-storage://` URIs.

- **Langfuse & OpenTelemetry Observability** — New OpenTelemetry-based observability system enables powerful tracing and Evals through Langfuse integration. Also supports OTLP-compatible backends (Datadog, Honeycomb, etc.). Configured via `.pipelex/telemetry.toml`.

- **Python 3.14 Support** — Officially tested and supported.

- **Agent CLI (`pipelex-agent`)**: New machine-first CLI for AI agents with structured JSON output for all commands (`build`, `run`, `validate`, `inputs`, `concept`, `pipe`, `assemble`, `graph`, `models`, `doctor`).
- **LLM Reasoning Controls**: Unified support for "Thinking" models (Chain of Thought) with `reasoning_effort`, `reasoning_budget`, and `thinking_mode` parameters. Supports Anthropic Extended Thinking, Google Gemini Thinking, OpenAI Reasoning (`o1`/`o3`), and Mistral/Magistral models. Includes new presets: `$deep-analysis` and `$quick-reasoning`.
- **Image-to-Image Generation**: `PipeImgGen` now supports input images via `input_images` field, with `InputImagesTaxonomy` for provider-specific handling and variable reference detection (`{{ var }}`, `$var`, `@var`) in prompts.
- **PipeCompose "Construct" Mode**: New `construct` mode for building structured objects (dictionaries/Pydantic models) directly from variables.
- **Nested concepts in inline structures**: You can now define nested structures for your concepts in your `.plx` files. Learn more here: [Nested Concepts in Inline Structures](https://docs.pipelex.com/latest/building-methods/concepts/inline-structures).

### Breaking Changes

- **CLI restructure: `method` / `pipe` subcommands** — `pipelex run`, `pipelex validate`, and all `pipelex build` subcommands (`runner`, `inputs`, `output`) now require an explicit `method` or `pipe` keyword. For example: `pipelex run method my-method` or `pipelex run pipe scoring.compute`. The old `pipelex run <target>` form is no longer supported. The agent CLI (`pipelex-agent`) follows the same structure.

### Added

- **Method resolution (`cli/method_resolver.py`)** — resolves installed method names to pipe codes and library directories. Integrates with `mthds` discovery module to find methods in `~/.mthds/methods/` and `./.mthds/methods/`.
- **`run method` command** — run an installed method by name, optionally overriding the pipe with `--pipe`.
- **`validate method` command** — validate all bundles in an installed method.
- **`build runner/inputs/output method` commands** — generate build artifacts for installed methods.
- **Persistent Credential Storage (`~/.pipelex/.env`)**: `pipelex init` now prompts for missing API keys after backend selection and saves them to `~/.pipelex/.env` with `0600` permissions. Credentials are loaded automatically at startup (global defaults, overridden by project `.env`).
- **`pipelex init credentials` Command**: New standalone focus to re-enter API keys without resetting configuration. Scans enabled backends, detects missing env vars, and prompts only for those.
- **Package Management System:** Introduced a full package manager for MTHDS with `METHODS.toml` manifests, `methods.lock` lockfile generation, local path and remote Git-based dependency resolution (MVS), a local package cache (`~/.mthds/packages`), and a new `pipelex pkg` CLI command group (`init`, `list`, `add`, `lock`, `install`, `update`, `publish`, `search`, `inspect`, `graph`).
- **Hierarchical Domains:** Support for dot-separated domain namespaces (e.g., `legal.contracts.shareholder`) and cross-package references via `alias->domain.pipe` syntax.
- **PipelexRunner:** Introduced the `PipelexRunner` class as the primary entry point for executing pipelines, replacing `PipelexClient` and standalone `execute_pipeline`/`start_pipeline` functions.
- **Linting & Formatting:** Integrated `plxt` (Pipelex Tools) for formatting and linting `.mthds` and `.toml` files, including CI/CD checks alongside `ruff`.
- **JSON Schema:** Automatic generation of `mthds_schema.json` for standard definition, IDE validation, and auto-completion.
- **Dev CLI:** Added `pipelex-dev` CLI for internal development tasks (e.g., schema generation).
- **CSP Nonce Support:** Added Content Security Policy nonce support for generated HTML graphs (Mermaid/ReactFlow) to enable secure rendering in VS Code webviews.
- **OpenRouter Backend:** Added OpenRouter as an inference backend with 337 chat model definitions and 14 image generation models.
- **Builder Auto-Repair**: Self-healing capabilities including auto-generation of undeclared concepts, multiplicity mismatch fixes, and pruning of unreachable pipes/unused concepts.
- **Concept Field Features**: Added `choices` support (compiles to `Literal` types/Enums) and explicit `list` type with `item_type`/`item_concept_ref`.
- **PipeFunc Execution Error Context**: When a `@pipe_func` function fails during execution, the error message now includes detailed context: the function name, actual input values from working memory, expected output type, and the original error with its type. This makes debugging PipeFunc errors much easier.
- **`pipelex build output` CLI Command**: New command to generate example output JSON for a pipe, complementing the existing `pipelex build inputs` command. Shows the expected output structure based on the pipe's output concept type, with multiplicity support. For pipes with `native.Anything` output (e.g., `PipeCondition` with different mapped pipe outputs), displays all possible outputs from mapped pipes.
- **Telemetry System**: Introduced anonymous usage tracking and exception capture for CLI commands (`graph render`), reporting to both user-configured and Pipelex analytics endpoints.
- **PipeExtract Operator Validation**: Added strict input validation that raises configuration errors for incompatible input types or when document-specific parameters are used with image inputs.
- **PipeCondition Output Auto-Fix in Builder Loop**: The pipe builder now automatically fixes `PipeCondition` output concept errors during validation. If all mapped pipes have the same output, the `PipeCondition` output is set to that concept; otherwise it's set to `native.Anything`.
- **PipeFunc Return Type Validation**: Added validation to ensure that a `PipeFunc` function's return type matches the output concept's structure class.
- **URL Validation on `ImageContent` and `DocumentContent`**: Both models validate external resources (HTTP/HTTPS URLs via HEAD request, local file paths via existence check) through a `validate_resources()` method called during pipeline execution (`validate_before_run`) rather than at model instantiation. Internal URIs (`data:`, `pipelex-storage://`) skip validation entirely. Validation is skipped in dry-run mode where inputs use mock URLs.
- **Literal Type Support in Dry Run Mocks**: `DryRunFactory` now detects `Literal` type annotations (including `Optional[Literal[...]]`) and generates valid mock values by randomly picking from the allowed choices instead of producing invalid random strings.
- **Literal Type Support in `pipelex build inputs`/`pipelex build output`**: The concept representation generator now handles `Literal` fields by picking a random value from the allowed choices, and generates mock URL patterns for `url` fields.
- **Literal Error Handling in Validation Messages**: Pydantic validation error formatting now recognizes `literal_error` types and displays them as "Invalid choice errors" with the actual value and expected options.
- **`PipeRunError` Catching in Bundle Validation**: `validate_bundle` now catches `PipeRunError` during dry run and wraps it in `ValidateBundleError` with a clear message.
- **`ValidationError` Catching in Pipeline Execution**: `execute_pipeline` now catches Pydantic `ValidationError` from input construction, formats the errors, and raises a `PipeExecutionError` with a clear message.
- **Broader Error Handling in CLI `pipelex run`**: The CLI run command now catches `PipelexError` in addition to `PipelineExecutionError`, providing better error messages for failures that occur outside the pipeline execution itself.
- **Content Filenames:** Added `filename` field to `ImageContent` and `DocumentContent`, with auto-population from local file paths via new `extract_filename_from_uri` helper.
- **Batch Validation Error Type:** Introduced `PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION` for naming conflicts in batch operations.
- **Documentation:** Added naming convention rules to `builder.plx` and `pipe_design.plx` (batch input lists should be plural, item names singular).
- **`--library-dir` CLI Option**: `--library-dir` / `-L` option for `pipelex run`, `pipelex validate`, and `pipelex build` subcommands (`one-shot-pipe`, `partial-pipe`) to specify additional directories for searching pipe definitions. Can be specified multiple times.
- **Automatic File Loading**: The core pipeline execution functions (`pipelex.execute_pipeline`, `pipelex.start_pipeline`) can now directly load a pipeline from a file path via a new `bundle_uri` parameter.
- **Dry Run Mode**: `pipelex run --dry-run` executes pipeline logic without API calls, useful for validating structure and generating orchestration graphs. Combine with `--mock-inputs` to generate mock data for missing required inputs.
- **`| with_images` Jinja2 Filter**: Explicitly extract and include all nested images from complex data structures (e.g., `Page` objects or custom concepts with `Image` fields). Renders the object's text representation while making associated images available to the LLM.
- **System Prompt Media Support**: Reference images and documents in `system_prompt` using the same `$variable` and `@variable` syntax as the user `prompt`.
- **Pipelex Gateway Service**: Terms of service management via `.pipelex/pipelex_service.toml` and interactive acceptance flow in `pipelex init` and `pipelex init agreement`.
- **Gateway Available Models Documentation**: Auto-generated reference of all LLM, Document Extraction, and Image Generation models available through the Gateway.
- **Configurable Retry Logic**: Exponential backoff for inference API calls, configurable in `pipelex.toml` under `[cogt.tenacity_config]`
- **Context Manager Support**: The `Pipelex` class now supports `with Pipelex.make(): ...` for graceful shutdown
- **Validation Improvements**:
  - Pipelex Bundle concept keys: prevent bundles from re-creating a native concept
  - `PipeSequence`: output multiplicity must match the last step's output multiplicity
  - `PipeFunc`: output multiplicity must match the function return type (`ListContent` subclass for multiplicity=true)
- **Rendering Protocols**: Three new `@runtime_checkable` protocols (`ImageRenderable`, `TagRenderable`, `TextFormatRenderable`) to formalize the interaction between data types and Jinja2 filters.
- **Unified URI Handling System**: New `pipelex.tools.uri` module providing type-safe parsing for HTTP/HTTPS URLs, local file paths, file URIs, `pipelex-storage://` URIs, and base64 data URLs.
- **Automatic Input Data Storage**: Pipeline pre-processing step that converts large `data:` URLs in an `ImageContent` or `DocumentContent` into `pipelex-storage://` URIs for improved performance, by storing the data with the configured storage provider. Configurable via `is_normalize_data_urls_to_storage` in `pipelex.toml`.
- **`pipelex build inputs` Command**: New CLI command to generate example input JSON files for pipes. Supports `--library-dir` (`-L`) to specify library directories.
- **Pipe Code Syntax Validation**: Bundle validation now checks that pipe codes and `main_pipe` values use valid snake_case syntax, with proper error categorization (`INVALID_PIPE_CODE_SYNTAX`).

### Changed

- **CI Runner Optimization**: Split self-hosted runners into dedicated test (D32) and lint (D4) pools with pre-baked Docker image (Python 3.10-3.14, UV, dependency cache) for faster job startup.
- **MTHDS Light Client Extraction**: The light client protocol (runner, pipeline models, pipe output abstractions) has been extracted from pipelex into the new [`mthds`](https://github.com/mthds-ai/mthds-python) package on PyPI. Pipelex now depends on `mthds>=0.0.1` and implements its `RunnerProtocol`.
- **Global/Local Config Split**: `pipelex init` now creates configuration in `~/.pipelex/` (global) by default. Use `pipelex init --local` to create project-level overrides in `{project_root}/.pipelex/`. Config loading merges: package defaults → global → project → overrides.
- **IDE Extension Detection**: Extension check now uses `code --list-extensions` / `cursor --list-extensions` for reliable detection instead of folder scanning. Shows separate marketplace links for VS Code (Microsoft Marketplace) and Cursor (Open VSX Registry).
- **Quieter `pipelex init`**: Removed verbose file listing and reset messages from config initialization output.
- **`pipelex init` Help Text**: Detailed focus option descriptions now shown in `pipelex init --help` explaining each focus (`all`, `config`, `credentials`, `inference`, `routing`, `telemetry`, `agreement`).
- **File Extension:** Pipeline definitions now use `.mthds` instead of `.plx`; the project refers to "Methods" (MTHDS) rather than "Pipelex workflows".
- **Syntax:** In `PipeParallel` definitions, `parallels` field renamed to `branches`; `plx_config` in `pipelex.toml` renamed to `mthds_config`.
- **Documentation:** Comprehensive update to reflect `.mthds` file format, package management, and new project structure.
- **Model Deck Updates**: Default premium model now `claude-4.6-opus`; added Mistral models (`mistral-small-3.2`, `mistral-large`, `magistral` series) and `gpt-5` placeholders.
- **Jinja2 Rendering**: Image objects now replaced with placeholders (e.g., `[Image 1]`) during text generation; async filters only registered in async environments.
- **Backend Configurations**: Added `effort_to_level_map` and `effort_to_budget_maps` for reasoning translation; disabled Google Vertex AI by default.
- **Dependencies**: Updated `pypdfium2`, `anthropic`, and `mistralai` version constraints.
- **`pipelex run --dry-run`**: No longer pretty prints the main_stuff output, matching the expected behavior for dry runs where no actual inference occurs.
- **`pipelex build structures` Command**: Now uses a lightweight loading mechanism that only processes domains and concepts, skipping pipe loading and validation entirely. This fixes the chicken-and-egg problem where structure generation would fail due to pipe validation errors before the structures were even created. Added `--force` / `-f` flag to regenerate all structures without checking if classes already exist.
- **Test Profile System**: Refactored integration tests to use a new configuration system (`.pipelex/test_profiles.toml`) with `dev`, `ci`, and `full` profiles for controlling which AI models are used in parametrized tests, replacing runtime filtering and hardcoded model lists.
- **`pipelex run --graph` Flag**: Now acts as an override for `pipelex.toml` settings instead of defaulting to `true`.
- **Default Image Generation Models**: Updated in `base_deck.toml`: `base-img-gen`: `flux-2-pro`, `best-img-gen`: `nano-banana-pro`, `fast-img-gen`: `gpt-image-1-mini`
- **Remote Configuration**: Updated service URL to version 3.
- **GatewayExtractWorker**: Now checks model capabilities before attempting image captioning.
- Change the output validation of `PipeCondition`: If all mapped pipes have the same output concept, `PipeCondition`'s output MUST be that same concept. If mapped pipes have different output concepts, `PipeCondition`'s output MUST be the native concept `Anything`.
- **CLI**: Changed `pipelex validate all` to `pipelex validate --all` (or `-a`).
- **StructuredContent.rendered_html()**: Now recursively calls `rendered_html()` on nested `StuffContent` fields instead of using json2html conversion. Also skips `None` values and uses HTML table format.
- **Batch Pipe Validation:** Enforced stricter naming rules for batch specs—`input_item_name` must differ from `input_list_name` and not shadow existing input keys, with clearer error messages suggesting plural/singular conventions.
- **Jinja2 Integration Refactored to Protocol-Based Approach**: Replaced the `Jinja2Registry` singleton and handler functions with a decoupled protocol-based system, eliminating circular dependencies between the template layer and core domain logic.
- **`StuffArtefact` Redesigned as Delegation Adapter**: Now a lightweight, immutable adapter that delegates attribute access directly to underlying `Stuff` and `StuffContent` objects, improving performance and providing more intuitive field access.
- **Image Extraction Moved to Content Types**: `StructuredContent`, `ListContent`, `ImageContent`, and `TextAndImagesContent` now implement the `ImageRenderable` protocol, replacing centralized handler logic.
- **⚠️ Breaking**: User override config renamed from `pipelex_super.toml` to `pipelex_override.toml`.
- **Image Generation Architecture**: Refactored to taxonomy-based approach. Standardizes parameter translation (`aspect_ratio`, `quality`, `output_format`) to provider-specific APIs.
- **Document Extraction Improvements**: `pypdfium2` extractor now extracts embedded images from PDFs. Response parsing uses dedicated Pydantic schemas for validation.
- **Default Model Change**: `extract_text_from_visuals` deck now defaults to `azure-document-intelligence`
- **`pipelex_inference` replaced by `pipelex_gateway`**: See Highlights for migration details. New `PIPELEX_GATEWAY_API_KEY` environment variable; default routing profiles updated to `pipelex_gateway_first`.
- **Telemetry System Split**: Now two separate streams:
  1. Pipelex Gateway telemetry for service monitoring (never collects prompts/completions/business data)
  2. Custom telemetry to user-configured backends
  3. Config updated accordingly (`telemetry.toml`):
     - Renamed `[posthog]` to `[custom_posthog]` to distinguish user's PostHog from Pipelex Gateway telemetry
     - Added new `[custom_portkey]` section with `force_debug_enabled` and `force_tracing_enabled` settings

- **Main Configuration Overrides Updated** (`.pipelex/pipelex.toml`):
  - `pipelex_override.toml` (final override) renamed from `pipelex_super.toml` to `pipelex_override.toml` and moved from repo root to `.pipelex/` directory
  - `telemetry_override.toml` (personal telemetry settings)
  - `is_generate_cost_report_file_enabled` default changed from `true` to `false`

- **Documentation**:
  - Clarified **Setup (first run)** vs **Configuration (TOML reference)**, added a Setup overview page, and added contributor docs for configuration defaults/overrides.
  - Added the "Under the Hood" page documenting the execution graph tracing system.
- **`pipelex init`**: Now creates a documented `telemetry.toml` template instead of prompting for preferences
- **Model Catalog Updated**: Latest models (gpt-5.1, claude-4.5-opus, gemini-3.0-pro, etc.) and updated waterfalls in `base_deck.toml`
- **Model Constraints Refactored**: From simple lists to structured `valued_constraints` dictionaries (e.g., `valued_constraints = { fixed_temperature = 1 }`)
- **OpenAI Responses API**: New implementation now differentiates between `openai_completions` and `openai_responses`
- **CLI Initialization**: Commands refactored to use centralized `Pipelex` initialization factory for improved error handling
- **`pipelex doctor`**: Enhanced to detect outdated `telemetry.toml` formats and suggest fixes
- **`--output-dir` Option**: The `runner`, `structures`, and `inputs` CLI commands now accept this option
- **Cost Report**: Now displays a note clarifying that it only includes LLM costs
- **`description` Field Now Required**: In `PipeAbstract`, `PipeBlueprint`, and `PipeSpec` classes.
- **Configuration**: New `[pipelex.pipeline_execution_config.graph_config]` section in `pipelex.toml` for fine-grained control over graph generation, data embedding, and rendering options.
- **CLI**: All `pipelex` commands now accept `--no-logo` to suppress the Pipelex banner in the terminal — useful to reduce tokens.

### Fixed

- **`find_project_root` Home Directory Bug**: The project root walker no longer considers the home directory (`~`) as a project root, even if it contains stray marker files like `package.json`.
- **Python 3.10 Compatibility**: Fixed `datetime.UTC` import (Python 3.11+) to use `datetime.timezone.utc`.
- **Graph Rendering:** Fixed dashed edge rendering for `PipeBatch` and `PipeParallel` relationships.
- **Image Generation Response Parsing:** Hardened image response parsing to handle varied provider response formats more robustly.
- **Helpful Error for `get_stuff_as(ListContent[T])`**: When users incorrectly call `get_stuff_as("name", ListContent[Something])` instead of `get_stuff_as_list("name", Something)`, the error message now explicitly suggests using `get_stuff_as_list()`.
- **PipeFunc `ListContent[T]` Validation**: Fixed validation rejecting valid `ListContent[T]` return types for array outputs (`T[]`). Previously, a function returning `ListContent[Expense]` would fail validation for `output = "Expense[]"` with a misleading error. The validation now correctly extracts and validates the generic type parameter from Pydantic's metadata.
- **PipeFunc Class Name Matching**: Fixed validation failing when the return type class and concept structure class are logically the same but loaded from different contexts. The validation now uses class name matching as a fallback, allowing `ListContent[Expense]` to match `Expense[]` even if the `Expense` class objects differ.
- Fixed `PipeImgGen` not properly converting `ImageContent` to custom subclasses (e.g., `Receipt(ImageContent)`). The pipe now uses `smart_dump()` before `model_validate()` to correctly instantiate the output concept's structure class.
- Corrected output directory creation logic in `pipelex run` to properly respect the `--no-graph` flag and configuration settings.
- Fixed a bug when trying to print HTML content in a TextContent object.
- Fixed the Pipelex CLI for generating structures, inputs, runner files.
- Fixed `@pipe_func` decorated functions showing "function not found" instead of explaining why the function is ineligible (e.g., missing return type annotation).
- Fixed PipeLLM with list output (e.g., `output = "Item[]"`) not producing `ListContent` when run inside a nested PipeSequence with `batch_over`.
- **Duplicate Pipe Error Message**: When a pipe code is declared in multiple `.plx` files (or twice in the same file), the error message now shows which bundle file(s) contain the conflicting declarations instead of a misleading message about "running the same pipe twice in the same pipeline".
- Fixed `pipelex build runner` and `pipelex build inputs` generating string placeholders (e.g., `"number_int | float"`) instead of numeric values for Number concepts with `int | float` union type fields.
- Fixed structure generation failing with `PydanticUserError` when a concept structure references native concepts (e.g., `native.Html`). The generator now properly resolves native concept refs to their content classes (e.g., `HtmlContent`) with correct imports.
- **Nested Image Handling**: Images nested within structured data are now properly replaced with `[Image N]` tokens. The `| with_images` filter and `ImageRegistry` system correctly extract images from complex nested structures.
- **`PipeCondition` Validation**: Output multiplicity validation now works correctly.
- **Error Reporting**: `PipeCompose` validation errors now include formatted details and failing field values.
- **Duplicate Pipeline Registration**: Running a pipeline from a file that was also part of a pre-loaded library (via `PIPELEXPATH`) no longer causes a duplicate domain registration error. The system now tracks absolute paths of loaded library files and skips files already loaded.
- **`pipelex build structures`**: Corrected output file naming and resolved import path generation.
- **`ConceptFactory.make_from_blueprint`**: Now correctly handles native concepts.

### Removed

- **Legacy Client & Execution Modules:** Removed `PipelexClient`, protocol files, and standalone `pipelex.pipeline.execute`/`pipelex.pipeline.start` modules (replaced by `PipelexRunner` and `mthds` package).
- **Legacy Config:** Removed `plx_config.py` and `.plx`-specific configuration references.
- **`pipelex kit` Command**: The kit commands have been removed from the main CLI. They are now internal tools for Pipelex contributors only, available via `pipelex-dev kit rules`.
- **`pipelex kit migrations` Command**: Removed entirely.
- **`pipelex kit remove-rules` Command**: Removed entirely.
- **PLX Syntax Agent Rules**: Removed `write_pipelex.md` and `run_pipelex.md` agent rules. These PLX syntax guides are no longer installed in client projects.
- **`[pipelex.kit_config]` Configuration**: Removed from client project configuration (`.pipelex/pipelex.toml`).
- **`openai_utils` Module**: Removed `pipelex.plugins.openai.openai_utils`; logic now in centralized image preparation utilities.
- **Pipeline Tracking feature**: Removed entirely, including the `pipelex/pipeline/track` module, `PipelineTracker` components, related configuration, tracker calls in pipe controllers, and associated documentation.
- **`Flow` Generator**: The old flow generator has been removed.

### Security

- **CSP Nonce Support:** Added Content Security Policy nonce for generated HTML graph outputs.

### Deprecated

- `pipelex_inference` backend in favor of `pipelex_gateway` (marked as "🛑 Legacy" in configuration template)

### For Contributors

- **Technical Documentation**: Added a new "Under the Hood" page documenting the `StuffArtefact` delegation pattern and image rendering architecture.
- **Enhanced Testing**: Added extensive unit and integration tests for the protocol-based rendering system, including nested image extraction and filter error conditions.
- **Agent Rules**: Added `pipelex_standards.md` outlining standards for the Pipelex configuration system, also included as rules for AI development agents.
- **Agent Rules**: New target `make agent-check` for faster linting.
- **⚠️ Breaking — Content Handling Overhaul**: `GeneratedImage` replaced by internal `GeneratedImageRawDetails`; `ImageContent` is now standard (without `base_64` field). `PipeExtract` outputs `PageContent` list directly. Content persistence now handled automatically by storage system.
- **⚠️ Breaking — Image Prompt Representation**: Redesigned `PromptImage` models—consolidated `PromptImagePath` and `PromptImageUrl` into `PromptImageUri`; now uses Pydantic discriminated union for URI, base64, and raw bytes sources.
- **Centralized Image Preparation**: Moved image fetching and base64 conversion logic to `pipelex.cogt.image.prompt_image_utils`, simplifying LLM provider plugins (Anthropic, Google, Mistral, OpenAI).
- **Unified Resource Loading**: Updated all file/URL reading components (PDF renderers, document extractors) to use the new URI handling system, replacing the legacy `pipelex.tools.misc.path_utils` module.
- **Async HTTP Fetching**: Renamed `fetch_file_from_url_httpx_async` to `fetch_file_from_url_httpx`; removed redundant synchronous version.
- **`PreparedImage` Abstraction**: New models (`PreparedImageHttpUrl`, `PreparedImageBase64`) representing images ready for LLM provider APIs.
- **Pipelex Gateway Model Management**: New CLI commands (`pipelex-dev update-gateway-models`, `pipelex-dev check-gateway-models`) and corresponding `make` targets (`ugm`, `cgm`) to generate and verify gateway model catalog. CI now validates this documentation is up-to-date.
- **Test Suite Pre-flight Check**: Verifies Gateway terms acceptance before running tests, providing clear error messages.
- **Content Rendering**: `StuffContent.rendered_*` methods now provide both synchronous and asynchronous variants.

### Migration Notes

- **Telemetry configuration migration**: If you have an existing `telemetry.toml`, rename:
  - `[posthog]` → `[custom_posthog]`
  - `[posthog.tracing]` → `[custom_posthog.tracing]`
  - `[posthog.tracing.capture]` → `[custom_posthog.tracing.capture]`
  - Or run `pipelex init telemetry --reset` to regenerate the file with the new structure

### Refactored

- **Anthropic Backend**: Internal streaming for standard completions to prevent SDK timeouts, configurable structured output timeout (`structured_output_timeout_seconds`), improved error mapping, and increased Bedrock Claude `max_tokens` (8K → 64K) with removal of `max_output_tokens_limit` constraint.
- **⚠️ Breaking — Pipe I/O Specification**: The output (and inputs) of a pipe is now a `StuffSpec` object that holds the concept and the multiplicity.
- **Naming Convention**: Renamed `domain` to `domain_code` where relevant.
- **Dry Run Methods**: Refactored the dry run methods of the `PipeAbstract` class.

## [v0.18.0b4] - 2026-02-23

### Added

- **Persistent Credential Storage (`~/.pipelex/.env`)**: `pipelex init` now prompts for missing API keys after backend selection and saves them to `~/.pipelex/.env` with `0600` permissions. Credentials are loaded automatically at startup (global defaults, overridden by project `.env`).
- **`pipelex init credentials` Command**: New standalone focus to re-enter API keys without resetting configuration. Scans enabled backends, detects missing env vars, and prompts only for those.
- **Package Management System:** Introduced a full package manager for MTHDS with `METHODS.toml` manifests, `methods.lock` lockfile generation, local path and remote Git-based dependency resolution (MVS), a local package cache (`~/.mthds/packages`), and a new `pipelex pkg` CLI command group (`init`, `list`, `add`, `lock`, `install`, `update`, `publish`, `search`, `inspect`, `graph`).
- **Hierarchical Domains:** Support for dot-separated domain namespaces (e.g., `legal.contracts.shareholder`) and cross-package references via `alias->domain.pipe` syntax.
- **PipelexRunner:** Introduced the `PipelexRunner` class as the primary entry point for executing pipelines, replacing `PipelexClient` and standalone `execute_pipeline`/`start_pipeline` functions.
- **Linting & Formatting:** Integrated `plxt` (Pipelex Tools) for formatting and linting `.mthds` and `.toml` files, including CI/CD checks alongside `ruff`.
- **JSON Schema:** Automatic generation of `mthds_schema.json` for standard definition, IDE validation, and auto-completion.
- **Dev CLI:** Added `pipelex-dev` CLI for internal development tasks (e.g., schema generation).
- **CSP Nonce Support:** Added Content Security Policy nonce support for generated HTML graphs (Mermaid/ReactFlow) to enable secure rendering in VS Code webviews.
- **OpenRouter Backend:** Added OpenRouter as an inference backend with 337 chat model definitions and 14 image generation models.

### Changed

- **CI Runner Optimization**: Split self-hosted runners into dedicated test (D32) and lint (D4) pools with pre-baked Docker image (Python 3.10-3.14, UV, dependency cache) for faster job startup.
- **MTHDS Light Client Extraction**: The light client protocol (runner, pipeline models, pipe output abstractions) has been extracted from pipelex into the new [`mthds`](https://github.com/mthds-ai/mthds-python) package on PyPI. Pipelex now depends on `mthds>=0.0.1` and implements its `RunnerProtocol`.
- **Global/Local Config Split**: `pipelex init` now creates configuration in `~/.pipelex/` (global) by default. Use `pipelex init --local` to create project-level overrides in `{project_root}/.pipelex/`. Config loading merges: package defaults → global → project → overrides.
- **IDE Extension Detection**: Extension check now uses `code --list-extensions` / `cursor --list-extensions` for reliable detection instead of folder scanning. Shows separate marketplace links for VS Code (Microsoft Marketplace) and Cursor (Open VSX Registry).
- **Quieter `pipelex init`**: Removed verbose file listing and reset messages from config initialization output.
- **`pipelex init` Help Text**: Detailed focus option descriptions now shown in `pipelex init --help` explaining each focus (`all`, `config`, `credentials`, `inference`, `routing`, `telemetry`, `agreement`).
- **File Extension:** Pipeline definitions now use `.mthds` instead of `.plx`; the project refers to "Methods" (MTHDS) rather than "Pipelex workflows".
- **Syntax:** In `PipeParallel` definitions, `parallels` field renamed to `branches`; `plx_config` in `pipelex.toml` renamed to `mthds_config`.
- **Documentation:** Comprehensive update to reflect `.mthds` file format, package management, and new project structure.

### Fixed

- **`find_project_root` Home Directory Bug**: The project root walker no longer considers the home directory (`~`) as a project root, even if it contains stray marker files like `package.json`.
- **Python 3.10 Compatibility**: Fixed `datetime.UTC` import (Python 3.11+) to use `datetime.timezone.utc`.
- **Graph Rendering:** Fixed dashed edge rendering for `PipeBatch` and `PipeParallel` relationships.
- **Image Generation Response Parsing:** Hardened image response parsing to handle varied provider response formats more robustly.

### Removed

- **Legacy Client & Execution Modules:** Removed `PipelexClient`, protocol files, and standalone `pipelex.pipeline.execute`/`pipelex.pipeline.start` modules (replaced by `PipelexRunner` and `mthds` package).
- **Legacy Config:** Removed `plx_config.py` and `.plx`-specific configuration references.

### Security

- **CSP Nonce Support:** Added Content Security Policy nonce for generated HTML graph outputs.

## [v0.18.0b3] - 2026-02-11

**Highlights:**

- **Agent CLI (`pipelex-agent`)**: New machine-first CLI for AI agents with structured JSON output for all commands (`build`, `run`, `validate`, `inputs`, `concept`, `pipe`, `assemble`, `graph`, `models`, `doctor`).
- **LLM Reasoning Controls**: Unified support for "Thinking" models (Chain of Thought) with `reasoning_effort`, `reasoning_budget`, and `thinking_mode` parameters. Supports Anthropic Extended Thinking, Google Gemini Thinking, OpenAI Reasoning (`o1`/`o3`), and Mistral/Magistral models. Includes new presets: `$deep-analysis` and `$quick-reasoning`.
- **Image-to-Image Generation**: `PipeImgGen` now supports input images via `input_images` field, with `InputImagesTaxonomy` for provider-specific handling and variable reference detection (`{{ var }}`, `$var`, `@var`) in prompts.
- **PipeCompose "Construct" Mode**: New `construct` mode for building structured objects (dictionaries/Pydantic models) directly from variables.
- **Nested concepts in inline structures**: You can now define nested structures for your concepts in your `.plx` files. Learn more here: [Nested Concepts in Inline Structures](https://docs.pipelex.com/latest/building-methods/concepts/inline-structures).

### Added

- **Builder Auto-Repair**: Self-healing capabilities including auto-generation of undeclared concepts, multiplicity mismatch fixes, and pruning of unreachable pipes/unused concepts.
- **Concept Field Features**: Added `choices` support (compiles to `Literal` types/Enums) and explicit `list` type with `item_type`/`item_concept_ref`.
- **PipeFunc Execution Error Context**: When a `@pipe_func` function fails during execution, the error message now includes detailed context: the function name, actual input values from working memory, expected output type, and the original error with its type. This makes debugging PipeFunc errors much easier.
- **`pipelex build output` CLI Command**: New command to generate example output JSON for a pipe, complementing the existing `pipelex build inputs` command. Shows the expected output structure based on the pipe's output concept type, with multiplicity support. For pipes with `native.Anything` output (e.g., `PipeCondition` with different mapped pipe outputs), displays all possible outputs from mapped pipes.
- **Telemetry System**: Introduced anonymous usage tracking and exception capture for CLI commands (`graph render`), reporting to both user-configured and Pipelex analytics endpoints.
- **PipeExtract Operator Validation**: Added strict input validation that raises configuration errors for incompatible input types or when document-specific parameters are used with image inputs.
- **PipeCondition Output Auto-Fix in Builder Loop**: The pipe builder now automatically fixes `PipeCondition` output concept errors during validation. If all mapped pipes have the same output, the `PipeCondition` output is set to that concept; otherwise it's set to `native.Anything`.
- **PipeFunc Return Type Validation**: Added validation to ensure that a `PipeFunc` function's return type matches the output concept's structure class.
- **URL Validation on `ImageContent` and `DocumentContent`**: Both models validate external resources (HTTP/HTTPS URLs via HEAD request, local file paths via existence check) through a `validate_resources()` method called during pipeline execution (`validate_before_run`) rather than at model instantiation. Internal URIs (`data:`, `pipelex-storage://`) skip validation entirely. Validation is skipped in dry-run mode where inputs use mock URLs.
- **Literal Type Support in Dry Run Mocks**: `DryRunFactory` now detects `Literal` type annotations (including `Optional[Literal[...]]`) and generates valid mock values by randomly picking from the allowed choices instead of producing invalid random strings.
- **Literal Type Support in `pipelex build inputs`/`pipelex build output`**: The concept representation generator now handles `Literal` fields by picking a random value from the allowed choices, and generates mock URL patterns for `url` fields.
- **Literal Error Handling in Validation Messages**: Pydantic validation error formatting now recognizes `literal_error` types and displays them as "Invalid choice errors" with the actual value and expected options.
- **`PipeRunError` Catching in Bundle Validation**: `validate_bundle` now catches `PipeRunError` during dry run and wraps it in `ValidateBundleError` with a clear message.
- **`ValidationError` Catching in Pipeline Execution**: `execute_pipeline` now catches Pydantic `ValidationError` from input construction, formats the errors, and raises a `PipeExecutionError` with a clear message.
- **Broader Error Handling in CLI `pipelex run`**: The CLI run command now catches `PipelexError` in addition to `PipelineExecutionError`, providing better error messages for failures that occur outside the pipeline execution itself.
- **Content Filenames:** Added `filename` field to `ImageContent` and `DocumentContent`, with auto-population from local file paths via new `extract_filename_from_uri` helper.
- **Batch Validation Error Type:** Introduced `PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION` for naming conflicts in batch operations.
- **Documentation:** Added naming convention rules to `builder.plx` and `pipe_design.plx` (batch input lists should be plural, item names singular).

### Changed

- **Model Deck Updates**: Default premium model now `claude-4.6-opus`; added Mistral models (`mistral-small-3.2`, `mistral-large`, `magistral` series) and `gpt-5` placeholders.
- **Jinja2 Rendering**: Image objects now replaced with placeholders (e.g., `[Image 1]`) during text generation; async filters only registered in async environments.
- **Backend Configurations**: Added `effort_to_level_map` and `effort_to_budget_maps` for reasoning translation; disabled Google Vertex AI by default.
- **Dependencies**: Updated `pypdfium2`, `anthropic`, and `mistralai` version constraints.
- **`pipelex run --dry-run`**: No longer pretty prints the main_stuff output, matching the expected behavior for dry runs where no actual inference occurs.
- **`pipelex build structures` Command**: Now uses a lightweight loading mechanism that only processes domains and concepts, skipping pipe loading and validation entirely. This fixes the chicken-and-egg problem where structure generation would fail due to pipe validation errors before the structures were even created. Added `--force` / `-f` flag to regenerate all structures without checking if classes already exist.
- **Test Profile System**: Refactored integration tests to use a new configuration system (`.pipelex/test_profiles.toml`) with `dev`, `ci`, and `full` profiles for controlling which AI models are used in parametrized tests, replacing runtime filtering and hardcoded model lists.
- **`pipelex run --graph` Flag**: Now acts as an override for `pipelex.toml` settings instead of defaulting to `true`.
- **Default Image Generation Models**: Updated in `base_deck.toml`: `base-img-gen`: `flux-2-pro`, `best-img-gen`: `nano-banana-pro`, `fast-img-gen`: `gpt-image-1-mini`
- **Remote Configuration**: Updated service URL to version 3.
- **GatewayExtractWorker**: Now checks model capabilities before attempting image captioning.
- Change the output validation of `PipeCondition`: If all mapped pipes have the same output concept, `PipeCondition`'s output MUST be that same concept. If mapped pipes have different output concepts, `PipeCondition`'s output MUST be the native concept `Anything`.
- **CLI**: Changed `pipelex validate all` to `pipelex validate --all` (or `-a`).
- **StructuredContent.rendered_html()**: Now recursively calls `rendered_html()` on nested `StuffContent` fields instead of using json2html conversion. Also skips `None` values and uses HTML table format.
- **Batch Pipe Validation:** Enforced stricter naming rules for batch specs—`input_item_name` must differ from `input_list_name` and not shadow existing input keys, with clearer error messages suggesting plural/singular conventions.

### Fixed

- **Helpful Error for `get_stuff_as(ListContent[T])`**: When users incorrectly call `get_stuff_as("name", ListContent[Something])` instead of `get_stuff_as_list("name", Something)`, the error message now explicitly suggests using `get_stuff_as_list()`.
- **PipeFunc `ListContent[T]` Validation**: Fixed validation rejecting valid `ListContent[T]` return types for array outputs (`T[]`). Previously, a function returning `ListContent[Expense]` would fail validation for `output = "Expense[]"` with a misleading error. The validation now correctly extracts and validates the generic type parameter from Pydantic's metadata.
- **PipeFunc Class Name Matching**: Fixed validation failing when the return type class and concept structure class are logically the same but loaded from different contexts. The validation now uses class name matching as a fallback, allowing `ListContent[Expense]` to match `Expense[]` even if the `Expense` class objects differ.
- Fixed `PipeImgGen` not properly converting `ImageContent` to custom subclasses (e.g., `Receipt(ImageContent)`). The pipe now uses `smart_dump()` before `model_validate()` to correctly instantiate the output concept's structure class.
- Corrected output directory creation logic in `pipelex run` to properly respect the `--no-graph` flag and configuration settings.
- Fixed a bug when trying to print HTML content in a TextContent object.
- Fixed the Pipelex CLI for generating structures, inputs, runner files.
- Fixed `@pipe_func` decorated functions showing "function not found" instead of explaining why the function is ineligible (e.g., missing return type annotation).
- Fixed PipeLLM with list output (e.g., `output = "Item[]"`) not producing `ListContent` when run inside a nested PipeSequence with `batch_over`.
- **Duplicate Pipe Error Message**: When a pipe code is declared in multiple `.plx` files (or twice in the same file), the error message now shows which bundle file(s) contain the conflicting declarations instead of a misleading message about "running the same pipe twice in the same pipeline".
- Fixed `pipelex build runner` and `pipelex build inputs` generating string placeholders (e.g., `"number_int | float"`) instead of numeric values for Number concepts with `int | float` union type fields.
- Fixed structure generation failing with `PydanticUserError` when a concept structure references native concepts (e.g., `native.Html`). The generator now properly resolves native concept refs to their content classes (e.g., `HtmlContent`) with correct imports.

### Removed

- **`pipelex kit` Command**: The kit commands have been removed from the main CLI. They are now internal tools for Pipelex contributors only, available via `pipelex-dev kit rules`.
- **`pipelex kit migrations` Command**: Removed entirely.
- **`pipelex kit remove-rules` Command**: Removed entirely.
- **PLX Syntax Agent Rules**: Removed `write_pipelex.md` and `run_pipelex.md` agent rules. These PLX syntax guides are no longer installed in client projects.
- **`[pipelex.kit_config]` Configuration**: Removed from client project configuration (`.pipelex/pipelex.toml`).

## [v0.18.0b2] - 2026-01-20

**Highlights:**

- **Pipelex Gateway** — The deprecated `pipelex_inference` backend is now replaced by `pipelex_gateway`, featuring remote model configuration fetching so you always have access to the latest models without updating Pipelex.

  **Getting your API key:**
  1. Get your API key at [app.pipelex.com](https://app.pipelex.com/)
  2. Add it to your `.env` file: `PIPELEX_GATEWAY_API_KEY=your-key-here`

  **Gateway Supported models — included with the Free API Key**
  - **Language Models (LLM):**
    - OpenAI: all models up to GPT-5.2 and Codex
    - Anthropic: Claude 3.7 Sonnet through Claude 4.5 Haiku/Sonnet/Opus
    - Google: Gemini 2.0/2.5 Flash, Gemini 2.5 Pro, Gemini 3.0 Flash/Pro
    - xAI: Grok 3/mini, Grok 4 (+ fast reasoning variants)
    - Open-source: Mistral Large 3, DeepSeek v3.1/3.2/Speciale, GPT-OSS 20B/120B1, Kimi K2, Phi-4, Qwen3-VL 235B
  - **Document Extraction:** Mistral Document AI, Azure Document Intelligence, DeepSeek OCR
  - **Image Generation:** GPT-Image 1/1.5, Flux 2 Pro, Nano Banana/Pro

  **Accepting the Terms of Service:**

  When you run `pipelex init`, you'll be prompted to accept the Gateway terms of service. By using Pipelex Gateway, telemetry is automatically enabled and identified by your API key (hashed for security) to monitor service quality and enforce fair usage. **We only collect technical data** (model names, token counts, latency, error rates)—never your prompts, completions, or business data. See our [Privacy Policy](https://go.pipelex.com/privacy-policy).

  **⚠️ Migration deadline:** If you were using `pipelex_inference`, please migrate soon—the legacy service will be shut down within few days. Get your new Gateway key at [app.pipelex.com](https://app.pipelex.com/).

- **Execution Graph Visualization System** (preview feature) — Comprehensive tracing and visualization for pipeline executions.

  **CLI:** `--graph` flag on `pipelex run` generates execution graphs. New `pipelex graph render <graph.json>` command for post-run rendering.

  **Viewers:** Interactive ReactFlow viewer (`reactflow.html`) with pan/zoom and node inspector. Mermaid diagrams (`mermaidflow.html`) with subgraphs and clickable nodes.

  **Makefile:** `make view-graph` (`vg`) and `make serve-graph` (`sg`) to start a local graph viewer.

- **Pydantic Structure Generation** — Two new CLI commands bridge Pipelex's declarative concepts with your Python code:

  **`pipelex build structures /library_dir/`** — Generates Pydantic models from all concept definitions found in the specified library directory. Now you have your structures as Python code: you can iterate on them, add custom validation functions, or use them as type hints in your code.

  **`pipelex build runner`** — Now automatically generates both the Python runner file AND the required Pydantic structures. When you run this command, it creates a complete, ready-to-execute Python script that imports the generated structures, so you can immediately use typed objects in your pipeline code.

  See the [Build Commands documentation](https://docs.pipelex.com/latest/tools/cli/build/) for usage examples.

- **New Backends & Models**:
  - **Hugging Face Inference** — Support for Hugging Face Inference API, including `qwen-image` text-to-image model.
  - Google `gemini-3.0-flash-preview`
  - Mistral OCR latest model `mistral-ocr-2512`
  - **Scaleway** inference provider support for open-source models
  - **Portkey AI** backend integration for unified access to multiple models through a single API key

- **Document Support in `PipeLLM`** — Include `Document` objects (like PDFs) directly in prompts using `@variable` or `$variable` syntax. Supports single documents, multiple documents, and lists, combinable with text and image inputs.

- **`PipeCompose` Construct Mode** — New mode for deterministically building `StructuredContent` objects without an LLM. Compose fields from working memory variables, fixed values, templates, and nested structures.

- **Content Storage System** — Configurable storage for generated artifacts (images, extracted pages). Supports `local` filesystem (`.pipelex/storage/`), `in_memory`, **AWS S3** (`pip install pipelex[s3]`), and **Google Cloud Storage** (`pip install pipelex[gcp-storage]`). Cloud providers support both public URLs and time-limited signed URLs. Content referenced via stable `pipelex-storage://` URIs.

- **Langfuse & OpenTelemetry Observability** — New OpenTelemetry-based observability system enables powerful tracing and Evals through Langfuse integration. Also supports OTLP-compatible backends (Datadog, Honeycomb, etc.). Configured via `.pipelex/telemetry.toml`.

- **Python 3.14 Support** — Officially tested and supported.

### Added

- **`--library-dir` CLI Option**: `--library-dir` / `-L` option for `pipelex run`, `pipelex validate`, and `pipelex build` subcommands (`one-shot-pipe`, `partial-pipe`) to specify additional directories for searching pipe definitions. Can be specified multiple times.
- **Automatic File Loading**: The core pipeline execution functions (`pipelex.execute_pipeline`, `pipelex.start_pipeline`) can now directly load a pipeline from a file path via a new `bundle_uri` parameter.
- **Dry Run Mode**: `pipelex run --dry-run` executes pipeline logic without API calls, useful for validating structure and generating orchestration graphs. Combine with `--mock-inputs` to generate mock data for missing required inputs.
- **`| with_images` Jinja2 Filter**: Explicitly extract and include all nested images from complex data structures (e.g., `Page` objects or custom concepts with `Image` fields). Renders the object's text representation while making associated images available to the LLM.
- **System Prompt Media Support**: Reference images and documents in `system_prompt` using the same `$variable` and `@variable` syntax as the user `prompt`.
- **Pipelex Gateway Service**: Terms of service management via `.pipelex/pipelex_service.toml` and interactive acceptance flow in `pipelex init` and `pipelex init agreement`.
- **Gateway Available Models Documentation**: Auto-generated reference of all LLM, Document Extraction, and Image Generation models available through the Gateway.
- **Configurable Retry Logic**: Exponential backoff for inference API calls, configurable in `pipelex.toml` under `[cogt.tenacity_config]`
- **Context Manager Support**: The `Pipelex` class now supports `with Pipelex.make(): ...` for graceful shutdown
- **Validation Improvements**:
  - Pipelex Bundle concept keys: prevent bundles from re-creating a native concept
  - `PipeSequence`: output multiplicity must match the last step's output multiplicity
  - `PipeFunc`: output multiplicity must match the function return type (`ListContent` subclass for multiplicity=true)
- **Rendering Protocols**: Three new `@runtime_checkable` protocols (`ImageRenderable`, `TagRenderable`, `TextFormatRenderable`) to formalize the interaction between data types and Jinja2 filters.
- **Unified URI Handling System**: New `pipelex.tools.uri` module providing type-safe parsing for HTTP/HTTPS URLs, local file paths, file URIs, `pipelex-storage://` URIs, and base64 data URLs.
- **Automatic Input Data Storage**: Pipeline pre-processing step that converts large `data:` URLs in an `ImageContent` or `DocumentContent` into `pipelex-storage://` URIs for improved performance, by storing the data with the configured storage provider. Configurable via `is_normalize_data_urls_to_storage` in `pipelex.toml`.
- **`pipelex build inputs` Command**: New CLI command to generate example input JSON files for pipes. Supports `--library-dir` (`-L`) to specify library directories.
- **Pipe Code Syntax Validation**: Bundle validation now checks that pipe codes and `main_pipe` values use valid snake_case syntax, with proper error categorization (`INVALID_PIPE_CODE_SYNTAX`).

### Fixed

- **Nested Image Handling**: Images nested within structured data are now properly replaced with `[Image N]` tokens. The `| with_images` filter and `ImageRegistry` system correctly extract images from complex nested structures.
- **`PipeCondition` Validation**: Output multiplicity validation now works correctly.
- **Error Reporting**: `PipeCompose` validation errors now include formatted details and failing field values.
- **Duplicate Pipeline Registration**: Running a pipeline from a file that was also part of a pre-loaded library (via `PIPELEXPATH`) no longer causes a duplicate domain registration error. The system now tracks absolute paths of loaded library files and skips files already loaded.
- **`pipelex build structures`**: Corrected output file naming and resolved import path generation.
- **`ConceptFactory.make_from_blueprint`**: Now correctly handles native concepts.

### Changed

- **Jinja2 Integration Refactored to Protocol-Based Approach**: Replaced the `Jinja2Registry` singleton and handler functions with a decoupled protocol-based system, eliminating circular dependencies between the template layer and core domain logic.
- **`StuffArtefact` Redesigned as Delegation Adapter**: Now a lightweight, immutable adapter that delegates attribute access directly to underlying `Stuff` and `StuffContent` objects, improving performance and providing more intuitive field access.
- **Image Extraction Moved to Content Types**: `StructuredContent`, `ListContent`, `ImageContent`, and `TextAndImagesContent` now implement the `ImageRenderable` protocol, replacing centralized handler logic.
- **⚠️ Breaking**: User override config renamed from `pipelex_super.toml` to `pipelex_override.toml`.
- **Image Generation Architecture**: Refactored to taxonomy-based approach. Standardizes parameter translation (`aspect_ratio`, `quality`, `output_format`) to provider-specific APIs.
- **Document Extraction Improvements**: `pypdfium2` extractor now extracts embedded images from PDFs. Response parsing uses dedicated Pydantic schemas for validation.
- **Default Model Change**: `extract_text_from_visuals` deck now defaults to `azure-document-intelligence`
- **`pipelex_inference` replaced by `pipelex_gateway`**: See Highlights for migration details. New `PIPELEX_GATEWAY_API_KEY` environment variable; default routing profiles updated to `pipelex_gateway_first`.
- **Telemetry System Split**: Now two separate streams:
  1. Pipelex Gateway telemetry for service monitoring (never collects prompts/completions/business data)
  2. Custom telemetry to user-configured backends
  3. Config updated accordingly (`telemetry.toml`):
     - Renamed `[posthog]` to `[custom_posthog]` to distinguish user's PostHog from Pipelex Gateway telemetry
     - Added new `[custom_portkey]` section with `force_debug_enabled` and `force_tracing_enabled` settings

- **Main Configuration Overrides Updated** (`.pipelex/pipelex.toml`):
  - `pipelex_override.toml` (final override) renamed from `pipelex_super.toml` to `pipelex_override.toml` and moved from repo root to `.pipelex/` directory
  - `telemetry_override.toml` (personal telemetry settings)
  - `is_generate_cost_report_file_enabled` default changed from `true` to `false`

- **Documentation**:
  - Clarified **Setup (first run)** vs **Configuration (TOML reference)**, added a Setup overview page, and added contributor docs for configuration defaults/overrides.
  - Added the "Under the Hood" page documenting the execution graph tracing system.
- **`pipelex init`**: Now creates a documented `telemetry.toml` template instead of prompting for preferences
- **Model Catalog Updated**: Latest models (gpt-5.1, claude-4.5-opus, gemini-3.0-pro, etc.) and updated waterfalls in `base_deck.toml`
- **Model Constraints Refactored**: From simple lists to structured `valued_constraints` dictionaries (e.g., `valued_constraints = { fixed_temperature = 1 }`)
- **OpenAI Responses API**: New implementation now differentiates between `openai_completions` and `openai_responses`
- **CLI Initialization**: Commands refactored to use centralized `Pipelex` initialization factory for improved error handling
- **`pipelex doctor`**: Enhanced to detect outdated `telemetry.toml` formats and suggest fixes
- **`--output-dir` Option**: The `runner`, `structures`, and `inputs` CLI commands now accept this option
- **Cost Report**: Now displays a note clarifying that it only includes LLM costs
- **`description` Field Now Required**: In `PipeAbstract`, `PipeBlueprint`, and `PipeSpec` classes.
- **Configuration**: New `[pipelex.pipeline_execution_config.graph_config]` section in `pipelex.toml` for fine-grained control over graph generation, data embedding, and rendering options.
- **CLI**: All `pipelex` commands now accept `--no-logo` to suppress the Pipelex banner in the terminal — useful to reduce tokens.

### Removed

- **`openai_utils` Module**: Removed `pipelex.plugins.openai.openai_utils`; logic now in centralized image preparation utilities.
- **Pipeline Tracking feature**: Removed entirely, including the `pipelex/pipeline/track` module, `PipelineTracker` components, related configuration, tracker calls in pipe controllers, and associated documentation.
- **`Flow` Generator**: The old flow generator has been removed.

### Deprecated

- `pipelex_inference` backend in favor of `pipelex_gateway` (marked as "🛑 Legacy" in configuration template)

### For Contributors

- **Technical Documentation**: Added a new "Under the Hood" page documenting the `StuffArtefact` delegation pattern and image rendering architecture.
- **Enhanced Testing**: Added extensive unit and integration tests for the protocol-based rendering system, including nested image extraction and filter error conditions.
- **Agent Rules**: Added `pipelex_standards.md` outlining standards for the Pipelex configuration system, also included as rules for AI development agents.
- **Agent Rules**: New target `make agent-check` for faster linting.
- **⚠️ Breaking — Content Handling Overhaul**: `GeneratedImage` replaced by internal `GeneratedImageRawDetails`; `ImageContent` is now standard (without `base_64` field). `PipeExtract` outputs `PageContent` list directly. Content persistence now handled automatically by storage system.
- **⚠️ Breaking — Image Prompt Representation**: Redesigned `PromptImage` models—consolidated `PromptImagePath` and `PromptImageUrl` into `PromptImageUri`; now uses Pydantic discriminated union for URI, base64, and raw bytes sources.
- **Centralized Image Preparation**: Moved image fetching and base64 conversion logic to `pipelex.cogt.image.prompt_image_utils`, simplifying LLM provider plugins (Anthropic, Google, Mistral, OpenAI).
- **Unified Resource Loading**: Updated all file/URL reading components (PDF renderers, document extractors) to use the new URI handling system, replacing the legacy `pipelex.tools.misc.path_utils` module.
- **Async HTTP Fetching**: Renamed `fetch_file_from_url_httpx_async` to `fetch_file_from_url_httpx`; removed redundant synchronous version.
- **`PreparedImage` Abstraction**: New models (`PreparedImageHttpUrl`, `PreparedImageBase64`) representing images ready for LLM provider APIs.
- **Pipelex Gateway Model Management**: New CLI commands (`pipelex-dev update-gateway-models`, `pipelex-dev check-gateway-models`) and corresponding `make` targets (`ugm`, `cgm`) to generate and verify gateway model catalog. CI now validates this documentation is up-to-date.
- **Test Suite Pre-flight Check**: Verifies Gateway terms acceptance before running tests, providing clear error messages.
- **Content Rendering**: `StuffContent.rendered_*` methods now provide both synchronous and asynchronous variants.

### Migration Notes

- **Telemetry configuration migration**: If you have an existing `telemetry.toml`, rename:
  - `[posthog]` → `[custom_posthog]`
  - `[posthog.tracing]` → `[custom_posthog.tracing]`
  - `[posthog.tracing.capture]` → `[custom_posthog.tracing.capture]`
  - Or run `pipelex init telemetry --reset` to regenerate the file with the new structure

### Refactored

- **Anthropic Backend**: Internal streaming for standard completions to prevent SDK timeouts, configurable structured output timeout (`structured_output_timeout_seconds`), improved error mapping, and increased Bedrock Claude `max_tokens` (8K → 64K) with removal of `max_output_tokens_limit` constraint.
- **⚠️ Breaking — Pipe I/O Specification**: The output (and inputs) of a pipe is now a `StuffSpec` object that holds the concept and the multiplicity.
- **Naming Convention**: Renamed `domain` to `domain_code` where relevant.
- **Dry Run Methods**: Refactored the dry run methods of the `PipeAbstract` class.

## [v0.17.6] - 2026-02-14

### Added

- **Claude Code GitHub Actions**: Added `claude.yml` workflow for interactive Claude Code assistance on issues and PR comments, and `claude-code-review.yml` workflow for automated code review on pull requests.

## [v0.17.5] - 2026-01-16

- Added target `make docs-deploy-404` to deploy the 404.html file to the gh-pages root for versionless URL redirects.

## [v0.17.4] - 2026-01-16

### Added

- Added the `mike` dependency to support mutiple docs versions. `version` plugin added to the MkDocs configuration, make targets and CI scripts.

## [v0.17.3] - 2025-12-01

### Fixed

- Fixed the issue with the `find_files_in_dir` force including virtual environment directories: Now it force includes the `pipelex.builder` directory.
- Fixed a bug with the comparison of Concept structures.

## [v0.17.2] - 2025-12-01

### Added

- **New AI models support**: Added GPT-5.1, Claude 4.5 Opus, and Gemini 3 Preview to the available models.
- **Codex Cloud support**: Added support for running Pipelex in Codex Cloud environments with appropriate configuration and testing capabilities.
- **Enhanced file discovery**: Added `force_include_dirs` parameter to the `find_files_in_dir` function. This allows specific directories to be force included in the search even when they are nested within excluded directories. For example, you can now exclude `.venv` while still including `.venv/lib/python3.11/site-packages/pipelex` for loading Pipelex libraries from installed packages.
- Added validation of the PipeLLM inputs at the blueprint level.
- Added a xfailed test for `PipeCondition`: if one of the outcome of the pipe is `continue`, it does nothing, but the main stuff still points towards the last step. Therefore when trying to get the main stuff out of the working memory as a specific type, it fails.

### Changed

- Backend fallback now only activates when explicitly opted-in, giving users more control over model selection.
- Renamed and improved the Azure Image Generation SDK implementation.
- Enhanced language spec examples, operator details, and added Viewpoint documentation.

### Fixed

- Fixed kit rules to be idempotent and work correctly across multiple executions.

## [v0.17.1] - 2025-11-27

### Fixed

- Fixed a bug in the `find_files_in_dir` function.

## [v0.17.0] - 2025-11-27

**Highlights:** - Previously, in the pipelex config files (`.toml` files in the `.pipelex/` directory, such as `.pipelex/pipelex.toml`, but also the routing profiles files, backends, etc.), when an array was overridden, the new array was concatenated to the old array. Now, the new array overrides the old array.

### Fixed

- **Relaxed concept structure field naming restrictions**: Users can now use field names like `content`, `stuff_code`, `stuff_name`, and `concept` in their concept structures without conflicts. Internal metadata fields in stuff artefacts now use underscore prefixes (`_stuff_name`, `_content_class`, `_concept_code`, `_stuff_code`, `_content`) to avoid collisions with user-defined fields. Reserved field names (Pydantic BaseModel attributes like `model_config`, `model_fields`, etc.) and field names starting with underscore remain forbidden with improved error messages that clearly specify which fields are problematic.

### Changed

- Modified the GHA `version-check.yml` so that the check of the version is only applying to release branches.
- Removed the `pyproject.toml` file from the build.
- No more implicit concepts. A concept reference has a domain and a code. If there is no domain, it should be a native concept, or it is declared in the same bundle.

### Refactored

- The `find_files_in_dir` function was coded in 3 different places, now it's in `pipelex/tools/misc/file_utils.py`, and accepts `excluded_dirs`.
- Refactored the Pipe factories: Centralized everything in the `PipeFactory` class.

## [v0.16.0] - 2025-11-25

**Highlights:** - Library manager now supports multiple libraries. You can now have multiple libraries in your project, each with its own set of concepts, pipes, and stuffs.
You can run the same pipe at the same times as much as you want, with different inputs.
Side effets: Unit tests now run in 30s.

### Fixed

- Fixed some issues with inputs of pipes: The validation methods was not detecting misconceptions with implicit concepts.

### Changed

- Improved pipe builder by auto-fixing errors, forcing consistency in the inputs and outputs of the pipes.

### Refactor

- PipeCondition: Moved the expression/expression_template choosing to the factory.
- Moved a lot of validation to blueprints instead of pipe instances.
- Refactored the Blueprint validation errors, and validation functions.
- Refactored the PipelexInterpreter validation errors.
- Refactored the pipe builder validation loop.
- Reorganized the unit tests, and added new ones.
- Reorganized the config files.
- Refactored methods `execute_pipeline` and `start_pipeline`.
- Moved `dev_cli` to `cli.dev_cli`.

## [v0.15.7] - 2025-11-18

### Fixed

- Fixed issue with `get_console()` function returning `None` if Pipelex is not initialized. Now always defaults to `stderr` if not set.

## [v0.15.6] - 2025-11-18

### Contributors

- Welcome to our new contributor @0x090909 (yup, that's his github username) for his work on Groq support in PR #445! 🎉

### Added

- **Improved configuration repair**: New `--fix` option for `pipelex doctor` command that interactively detects and repairs outdated or invalid backend configuration files using latest templates from the Pipelex kit.
- **Developer CLI & tooling**: New internal `pipelex-dev` CLI for project maintenance with `check-config-sync` command to verify user-facing configuration templates (`.pipelex/`) are synchronized with package's internal kit configs. Includes `make check-config-sync` command and CI check (`lint-check.yml`) to enforce synchronization.
- **Enhanced test infrastructure**: Integration tests now automatically parameterized to run against all supported backend routing profiles. Tests are intelligently skipped at collection time if a model is not supported by the active backend profile, with a summary of skipped tests provided at session end.
- **New routing profiles**: Added `all_groq` and `all_pipelex_inference` routing profiles.
- **Vision support flag**: Added `is_vision_supported` property to `LLMWorkerAbstract` class for explicit checks of model vision capabilities.
- **New type of `StuffContent`**: `JSONContent` to support an arbitrary JSON object as input or output of a pipe.
- **Azure image generation**: Support for image generation models via Azure OpenAI backend using `gpt-image-1`.

### Changed

- **Unified structured output**: Complete overhaul of structured generation settings. Replaced global configuration setting with new `structure_method` parameter in backend `.toml` files (configurable at backend level in `[defaults]` or per individual model). Expanded `StructureMethod` enum to include dozens of modes supported by `instructor`, enabling fine-grained control over provider-specific features like OpenAI Structured Outputs or Anthropic Tools, and various JSON-based modes.
- **Groq integration**: Updated to use standard `openai` SDK, simplifying integration.
- **Default configurations**: All official backend providers now enabled by default after `pipelex init`. Default prompting style changed from `ticks` to `xml`.
- **Code & test organization**: Unit test suite reorganized from `tests/unit/core` and other directories into unified `tests/unit/pipelex/` structure. Integration test fixtures modularized from `conftest.py` into separate files within `tests/integration/pipelex/fixtures/`.
- **Console output settings**: Added `console_print_target` and `console_log_target` settings in `pipelex.toml` for redirecting output to `stdout` or `stderr`, with CLI and logging refactored to use centralized console instance. This makes it easier to support MCP communication based on stdio.

### Fixed

- Improved Pydantic validation error messages when loading backend configurations to clearly indicate the specific file and model containing the error.

### Removed

- **Perplexity backend**: Default configuration for Perplexity AI backend (`perplexity.toml`) removed from kit (it was obsolete, it will come back).
- **Groq plugin**: Dedicated `pipelex/plugins/groq` plugin removed (now uses standard `openai` SDK).
- **Global instructor config**: Global `is_openai_structured_output_enabled` setting, replaced by per-model `structure_method` approach.

## [v0.15.4] - 2025-11-12

### Added

- **Enhanced `pipelex build` Command**: Now generates a self-contained directory (e.g., `results/pipeline_01/`) containing `bundle.plx`, `inputs.json`, `run_{pipe_code}.py`, `bundle_view.html`, and `bundle_view.svg`. New CLI options: `--output-name (-o)` for custom base name, `--output-dir` for custom directory, and `--no-extras` to generate only the `.plx` file.
- **CLI Readiness Check**: Verifies that a virtual environment is active for development installations.
- **Model Deck Presets**: Added `llm_for_creativity` and `cheap_llm_for_creativity` model waterfalls, plus `[cogt.model_deck_config]` section in `pipelex.toml` for configuring model fallback behavior.
- WIP: **Groq Inference Backend Support**: Integrated full support for the Groq API with configuration file (`.pipelex/inference/backends/groq.toml`), model specifications, costs, capabilities, new model aliases (`base-groq`, `fast-groq`, `vision-groq`), and routing profile (`all_groq`).

### Changed

- **CLI Output and Visualization**: Overhauled command-line output with rich, table-based layouts for pipeline components. Final output of `pipelex run` is now pretty-printed and adapts to content type.
- **Documentation**: Updated "Get Started" and "Build Reliable AI Workflows" to reflect new directory-based build output and CLI options.
- **Internal Code Refactoring**: Reorganized exception hierarchy into dedicated `exceptions.py` files per module, centralized validation logic into `validation.py` modules, added `ValueError` to blueprints, and removed unused exceptions for improved maintainability.
- Updated pytest to `>=9.0.1` to support their new `pyproject.toml` config format.

### Fixed

- Adjusted default temperature for `llm_for_testing_gen_object` preset from `0.5` to `0.1` for more deterministic structured data generation.
- Corrected `LLM_FOR_VISUAL_DESIGN` skill in `pipe_llm_spec` to point to `cheap_llm_for_creativity` preset.
- Standardized input variable names in `pipe_llm_vision.plx` from `imageA`/`imageB` to `image_a`/`image_b`.

### Removed

- Deleted `pipelex/core/validation_errors.py` file as part of exception hierarchy refactoring.

## [v0.15.3] - 2025-11-07

### Fixed

- Fixed weird import issues with `posthog` and `StrEnum`

## [v0.15.2] - 2025-11-07

### Fixed

- Fixed resetting routing profile when calling with `--reset` flag in `pipelex init`

## [v0.15.1] - 2025-11-07

### Fixed

- Bumped OpenAI dependency to `>=1.108.1` to support their breaking change: "change optional parameter type from `NotGiven` to `Omit`"
- `get_selected_backend_keys()` now correctly considers backends enabled by default (like before v0.15.0)

## [v0.15.0] - 2025-11-07

**Highlights:** This release dramatically simplifies onboarding with interactive CLI setup, comprehensive documentation relaunch, and intelligent model fallbacks, making Pipelex more accessible and resilient than ever.

### Added

- Model Waterfalls: Define prioritized model lists in `base_deck.toml` (e.g., `smart_llm = ["gpt-4o", "claude-4.5-sonnet", "grok-3"]`). Pipelex automatically falls back to the next model if the preferred one is unavailable.
- Advanced Routing Profiles: New capabilities in `routing_profiles.toml`: `fallback_order` (Global fallback sequence specifying which backends to try if a model isn't found) and `optional_routes` (Routes that activate only when their target backend is enabled)
- New Models: Anthropic `claude-4.5-haiku` (Pipelex Inference, Anthropic, and Bedrock backends) and Azure OpenAI `o3`
- Comprehensive Documentation Relaunch: Complete restructure under `/home/` with new "Get Started" guides for `pipelex build` and manual workflows, plus in-depth sections on Domains, Bundles, Concepts, and Pipe lifecycle.
- Enhanced CLI: `pipelex init` now interactively guides backend selection and automatically configures routing profiles, including primary backend and fallback order. Added `pipelex init routing` focus.
- Enhanced CLI: Improved error reporting across all commands (`build`, `validate`, `run`, `show`) with clear, actionable feedback for configuration errors, missing models, and invalid presets.
- Enhanced CLI: `pipelex doctor` now validates model deck configuration.
- New Routing Profiles: Full suite of `all_*` profiles (e.g., `all_openai`, `all_anthropic`, `all_google`) to route all requests to a single provider.

### Changed

- BREAKING: for inline concept structures, the fields are now optional by default: the `required` property defaults to `false`. Explicitly set `required = true` to make fields mandatory, which we discourage as it increases risks of hallucinations.
- LLM Presets Overhaul: Rationalized and renamed default presets in `base_deck.toml`. Single-model aliases replaced with waterfall aliases. Key renames: `llm_for_complex_reasoning` → `engineering-structured`, `llm_to_answer_hard_questions` → `llm_to_answer_questions`, `llm_to_write_questions` → `llm_for_writing_cheap`. Removed redundant older presets.
- Stricter Configuration Validation: Pipelex validates model deck on startup and raises errors if presets reference unavailable models.

### Fixed

- Local OpenAI-Compatible Endpoints: OpenAI plugin now handles empty API keys, enabling seamless integration with local servers like Ollama.

### Removed

- Old Documentation Structure: Previous `/pages/` directory documentation removed in favor of new structure.

## [v0.14.3] - 2025-10-29

### Added

- Image generation models via BlackBoxAI backend: `flux-pro`, `flux-pro/v1.1`, `flux-pro/v1.1-ultra` (Black Forest Labs), `fast-lightning-sdxl` (ByteDance), and `nano-banana` (Google). Implemented using new `openai_alt_img_gen` SDK worker with chat completion-style API.
- Language model: `claude-4.5-sonnet` (Anthropic) via BlackBoxAI backend.
- Routing profile: `all_blackboxai` profile routes all supported model requests to BlackBoxAI backend.

### Changed

- Model aliases in `base_deck.toml`: `base-img-gen` → `flux-pro/v1.1-ultra`, `best-img-gen` → `nano-banana`, `llm_for_large_codebase` now includes `claude-4.5-sonnet`.
- Configuration file: `BLACKBOX_RULES.md` renamed to `.blackboxrules`.

### Fixed

- Image generation schema: `ImgGenJobParams.seed` field now explicitly defined with `default=None`.
- CLI bundle validation: `pipelex validate` command now accepts bundle path (`.plx` file) which are in the package and already loaded and performs dry run on all pipes in the bundle.

## [v0.14.2] - 2025-10-29

### Chaged

- Improved pipe builder.

### Added

- CLI to generate inputs JSON.

## [v0.14.1] - 2025-10-27

### Added

- Tutorial GIF on the README.md file.

## [v0.14.0] - 2025-10-27

### Added

- **`pipelex doctor` command**: Diagnoses and fixes common configuration issues including missing files, invalid telemetry settings, and unset environment variables for enabled backends.
- **Interactive backend selection in `pipelex init`**: Multi-select menu for enabling/disabling inference backends (OpenAI, Anthropic, Amazon Bedrock, etc.).
- **JSON input support**: `pipelex run --inputs` flag accepts a JSON file path for passing structured data to pipelines.
- **`pretty_print` methods**: Added to `PipeSpec`, `ConceptSpec`, and `Stuff` objects for readable debugging output.
- **VS Code debug configuration**: "Debug run pipe" launch configuration for debugging pipeline executions.
- **`display_name` attribute**: Added to all inference backends in `backends.toml` for better UI presentation.
- **Documentation headers**: All default `.toml` configuration files now include headers with links to documentation and support channels.

### Changed

- **`pipelex init` redesign**: Transformed into a unified, interactive setup wizard with rich terminal UI for configuration files, backend selection, and telemetry preferences. Telemetry is now configured here instead of via first-run prompt.
- **`README.md` rewrite**: Complete overhaul featuring a simplified 5-step quick-start guide highlighting the `pipelex build` command.
- **Documentation updates**: "Quick Start" guide renamed to "Writing Workflows" with simplified content. Python examples updated to use JSON input method, removing manual `Stuff` and `WorkingMemory` object creation boilerplate. Developer guides and AI assistant rules now recommend `pipelex validate` over `make validate`. Added instructions emphasizing `.venv` activation before running commands.
- **Error handling improvements**: Pipelines now validate required inputs upfront and fail early with `PipeRunInputsError`. `pipelex run` prints full rich-formatted exception tracebacks on error.
- **Default enabled backends**: Amazon Bedrock, Google AI, and Google Vertex AI are now enabled by default.
- **Naming consistency**: "AWS Bedrock" renamed to "Amazon Bedrock" throughout codebase, configuration, and documentation.

### Fixed

- Some documentation links were broken.

## [v0.13.2] - 2025-10-25

### Added

- Added the `n8n` documentation page for the [n8n-nodes-pipelex](https://github.com/Pipelex/n8n-nodes-pipelex) package.
- Added optional telemetry system with first-run interactive prompt offering three modes: off (no data collected), anonymous (usage data without identification), and identified (usage data with user identification). Automatically respects `DO_NOT_TRACK` environment variable and redacts sensitive data (prompts, responses, file paths, URLs). Configuration stored in `.pipelex/telemetry.toml`.
- Added telemetry documentation: user-friendly setup guide and comprehensive configuration reference.

### Changed

- Updated the `PipelexClient` and changed the route of the API calls to `v1/pipeline/execute` and `v1/pipeline/start`.
- Changed the parameter `input_memory` to `inputs` in the documentaton.

## [v0.13.1] - 2025-10-22

### Changed

- Changed the `pydantic`dependency from `==2.10.6` to `>=2.10.6,<3.0.0` to avoid compatibility issues.

## [v0.13.0] - 2025-10-21

### Highlights - Simplifying pipeline execution and improving developer experience

This release focuses on making Pipelex more accessible and easier to use, with major improvements to the CLI, simplified syntax for multiplicity, and a complete documentation overhaul:

- **New CLI commands**: Run pipelines directly with `pipelex run`, generate Python runners with `pipelex build runner`, and inspect your AI backend configuration with `pipelex show backends`
- **Simplified pipeline inputs**: The new `inputs` parameter replaces `input_memory` and accepts strings, lists, or content objects directly - no more complex dictionary structures
- **Getting started faster**: Completely rewritten quick-start guide and new documentation sections help you go from installation to your first pipeline in minutes

### Added

- CLI command `pipelex run`: Top-level command to execute pipelines directly from the CLI. Can run pipes from the package or from any `.plx` bundle file, with options to provide inputs from a JSON file and save the output
- CLI command `pipelex build runner`: Generates Python script with imports and example input structures for any pipe
- CLI command `pipelex show backends`: Displays configured AI providers, their status, and active routing rules
- Model presets: Added task-oriented presets including `llm_to_write_questions`, `llm_to_code`, `llm_for_basic_vision`, `llm_for_visual_analysis`
- Documentation: Complete quick-start guide rewrite, new guides for "Understanding Multiplicity", "API Guide", "Executing Pipelines with Inputs", and updated README with video demo
- Migration guide: Updated guide at `pipelex/kit/migrations/migrate_0.11.0_0.12.x.md`

### Changed

- **Unified bracket notation for multiplicity**: Single items use `"Concept"`, variable lists use `"Concept[]"`, fixed-count lists use `"Concept[3]"`. Applies to both `inputs` and `output` fields in `.plx` files
- **Pipeline input format**: `input_memory` parameter renamed to `inputs`; now accepts strings, lists of strings, `StuffContent` objects, or explicit concept dictionaries instead of `CompactMemory`
- **Bundle `main_pipe` attribute**: Pipelex bundles (`.plx` files) now support a `main_pipe` attribute to designate the primary entry point of the bundle. Used by `pipelex run` and `pipelex build runner` commands to simplify execution
- **Model preset names**: `llm_to_reason` → `llm_for_complex_reasoning`, `base_ocr_mistral` → `extract_text_from_visuals`, `base_extract_pypdfium2` → `extract_text_from_pdf`, `base_img_gen` → `gen_image_basic`, `fast_img_gen` → `gen_image_fast`, `high_quality_img_gen` → `gen_image_high_quality`
- **Unified model parameter**: `PipeExtract` and `PipeImgGen` now use `model` parameter for consistency across all operator pipes
- **`PipeExtract` operator**: Output is now consistently validated to be the `Page` concept, simplifying its usage for document processing
- **CLI improvements**: `pipelex run` and `pipelex validate` now auto-detect pipe code vs `.plx` bundle files; `pipelex validate` promoted to top-level command with improved error reporting and syntax-highlighted code snippets
- **CLI reorganization**: Main command-line interface restructured for better usability with improved help texts and more logical command order
- **Python API**: `Pipelex.make()` now accepts dependency injection arguments directly
- **Python coding standards**: Updated internal coding standards to recommend declaring variables with a type but no default value to better leverage linters for bug detection
- **Default configuration**: Azure and AWS inference backends now disabled by default in template configuration

### Fixed

- Structure generation: Special characters (double quotes, backslashes) in concept field descriptions or default values no longer produce invalid Python code

### Removed

- Legacy multiplicity syntax: `nb_output`, `multiple_output` parameters, and complex input dictionary syntax with `multiplicity` field
- Pipe-specific model parameters: `ocr` parameter from `PipeExtract` and `img_gen` parameter from `PipeImgGen`
- `prompt_template_to_structure` and `system_prompt_to_structure` configurations at the pipe and domain level
- Project Name discovery from Configuration
- Temporary design document for the new inference backend system (feature now fully implemented and documented)

## [v0.12.0] - 2025-10-15

### Highlights - Moving fast and breaking things

- Added the new builder pipeline system for auto-generating Pipelex bundles from user briefs
  - it's a pipeline to generate pipelines, and it works!
  - the pipeline definitions are in `pipelex_libraries/pipelines/base_library/builder/`
  - removed the previous draft which was named `meta_pipeline.plx`

**Breaking changes... for good!**

We tried to group all the renamings we wanted to do which impact our language, so that you get one migration to apply and then we will be way more stable in the future releases.

This is all in the spirit of making Pipelex a declarative language, where you express what you want to do, and the system will figure out how to do it. So our focus inwas to make the Pipelex language easier to understand and use for non-technical users, and at the same time use more consistent and obvious words that developers are used to.

**💡 Pro tip:** To make migration easier, pass the [migration guide](https://github.com/Pipelex/pipelex/blob/main/pipelex/kit/migrations/migrate_0.11.0_0.12.0.md) to your favorite SWE agent (Cursor, Claude Code, github copilot, etc.) and let it handle the bulk of the changes!

- **Removed centralized `pipelex_libraries` folder system**
  - Pipelines are now auto-discovered from anywhere in your project—no special directory required
  - No config path parameters needed in `Pipelex.make()` or CLI commands (just call `Pipelex.make()`)
  - Custom functions require `@pipe_func()` decorator for auto-discovery
  - Structure classes auto-discovered (must inherit from `StructuredContent`)
  - Configuration stays at repository root in `.pipelex/` directory
  - See [migration guide](https://github.com/PipelexLab/pipelex/blob/main/pipelex/kit/migrations/migrate_0.11.0_0.12.0.md) for details on reorganizing your project structure

- General changes
  - renamed `definition` fields to `description` across all cases

- Renamed **PipeJinja2** to **PipeCompose**
  - the fact that our templating engine is Jinja2 is a technnical detail, not fundamental to the language, especially since we included a pre-processor enabling insertion of variables in prompts using `@variable` or `$variable`, in addition to the jinja2 syntax `{{ variable }}`
  - renamed `jinja2` field to `template` for the same reason
  - for more control, instead of providing a string for the `template` field, you can also use a nested `template` section with `template`, `category` and `templating_style` fields

- Renamed **PipeOCR** to **PipeExtract**
  - this is to account for various text extraction techniques from images and docs, including but not only OCR; e.g. we now have integrated the `pypdfium2` package which can extract text and images from PDF, when it's actually real text (not an image), and soon we'll add support for other document extraction models solutions
  - removed obligation to name your document input `ocr_input`, it can now be named whatever you want as long as it's a single input and it's either an `Image` or a `PDF` or some concept refining PDF or Image
  - renamed `ocr_page_contents_from_pdf` to `extract_page_contents_from_pdf`
  - renamed `ocr_page_contents_and_views_from_pdf` to `extract_page_contents_and_views_from_pdf`
  - introduced model settings and presets for extract models like we had for LLMs
  - renamed `ocr_model` to `model` for choice of model, preset, or explicit setting and introduced `base_ocr_mistral` as an alias to `mistral-ocr`

- **PipeLLM** field renames
  - image inputs must now be tagged in the prompt like all other inputs; you can just drop their names at the beginning or end of the prompt, or you can reference them in meaningful sentences to guide the Visual LLM, e.g. "Analyze the colors in $some_photo and the shapes in $some_painting."
  - renamed `prompt_template` field to `prompt`
  - renamed `llm` field to `model`
  - renamed `llm_to_structure` field to `model_to_structure`

- **PipeImgGen** field renames
  - renamed `img_gen` field to `model` for choice of model, preset, or explicit setting
  - removed some technical settings such as `nb_steps` from the pipe attributes, instead you can set these as model settings or model presets
  - introduced model settings and presets for image generation models like we had for LLMs

- **PipeCondition** field renames
  - renamed `pipe_map` to `outcomes`
  - renamed `default_pipe_code` to `default_outcome` and it's now a required field, because we need to know what to do if the expression doesn't match any key in the outcomes map; if you don't know what to do in that case, then it's a failure and you can use the `fail` value

- **Configuration file changes** (`.pipelex/` directory)
  - Renamed parameter `llm_handle` to `model` across all LLM presets in deck files
  - Renamed parameter `img_gen_handle` to `model` across all image generation presets in deck files
  - Renamed parameter `ocr_handle` to `model` in extraction presets
  - Renamed `ocr` section to `extract` throughout configuration files
  - Renamed `ocr_config` to `extract_config` in `pipelex.toml`
  - Renamed `base_ocr_pypdfium2` to `base_extract_pypdfium2`
  - Renamed `is_auto_setup_preset_ocr` to `is_auto_setup_preset_extract`
  - Renamed `nb_ocr_pages` to `nb_extract_pages`
  - Updated pytest marker from 'ocr' to 'extract'

### Added

- Added `cheap-gpt` model alias for `gpt-4o-mini`
- Added `cheap_llm_for_vision` preset using `gemini-2.5-flash-lite`
- Added `llm_for_testing_vision` and `llm_for_testing_vision_structured` presets for vision testing
- Added `is_dump_text_prompts_enabled` and `is_dump_response_text_enabled` configuration flags to have the console display everything that goes in and out of the LLMs
- Added `generic_templates` section in `llm_config` with structure extraction prompts
- Added useful error messages with migration configuration maps pin-pointing the fields to rename for config and plx files
- Added improved error message for `PipeFunc` when function not found in registry, mentioning `@pipe_func()` decorator requirement since v0.12.0
- Added pytest filterwarnings to ignore deprecated class-based config warnings
- Added `Flow` class that represents the flow of pipe signatures
- Added `pipe-builder` command `flow` to generate flow view from pipeline brief
- Added `FlowFactory` class to create Flow from PipelexBundleSpec or PLX files
- Added `sort_pipes_by_dependencies()` function for topological sorting of pipes
- Added `pipe_sorter.py` module for pipe dependency sorting utilities
- Added `search_for_nested_image_fields_in_structure_class()` method to Concept class
- Added `image_field_search.py` module with utilities to search for image fields in structure classes
- Added `pipe_dependencies` property to PipeBlueprint and controller blueprints
- Added `ordered_pipe_dependencies` property to PipeBlueprint for ordered dependencies
- Added `get_native_concept()` function to hub
- Added `get_pipes()` function to hub
- Added `remove_concepts_by_codes()` method to ConceptLibraryAbstract
- Added `remove_pipes_by_codes()` method to PipeLibraryAbstract
- Added template preprocessing with `preprocess_template()` function
- Added better dependency checking for optional SDK packages (anthropic, mistralai, boto3, aioboto3)
- Added `MissingDependencyError` exception for missing optional dependencies
- Added `library_utils.py` module with utility functions for PLX file discovery using `importlib.resources`
- Added `class_utils.py` module with `are_classes_equivalent()` and `has_compatible_field()` functions
- Added comprehensive unit tests for `CostRegistry`, `WorkingMemory`, and `ModuleInspector`
- Added `ScanConfig` class with configurable excluded directories for library scanning
- Added CSV export capabilities to `CostRegistry` with `save_to_csv()` and `to_records()` methods
- Added default configuration template in `pipelex/kit/configs/pipelex.toml`

### Changed

- Replaced package `toml` by `tomli` which is more modern and faster
- Updated Gemini 2.0 model from `gemini-2.0-flash-exp` to `gemini-2.0-flash` with new pricing (input: $0.10, output: $0.40 per million tokens)
- Updated Gemini 2.5 Series comment from '(when available)' to stable release
- Updated `best-claude` from `claude-4-sonnet` to `claude-4.5-sonnet` across all presets
- Updated kajson dependency from version `0.3.0` to `0.3.1`
- Updated httpx dependency to `>=0.23.0,<1.0.0` for broader compatibility
- Cleanup env example and better explain how to set up keys in README and docs
- Changed Gemini routing from `google` backend to `pipelex_inference` backend
- **BREAKING:** Major module reorganization - moved `tools/config/`, `tools/exceptions.py`, `tools/environment.py`, `tools/runtime_manager.py` to `system/` package structure (`system/configuration/`, `system/exceptions.py`, `system/environment.py`, `system/runtime.py`)
- **BREAKING:** Reorganized registry modules from `tools/` to `system/registries/` (affects `class_registry_utils`, `func_registry`, `func_registry_utils`, `registry_models`)
- **BREAKING:** Split `pipelex.core.stuffs.stuff_content` module into individual files per content type (affects imports: `StructuredContent`, `TextContent`, `ImageContent`, `ListContent`, `PDFContent`, `PageContent`, `NumberContent`, `HtmlContent`, `MermaidContent`, `TextAndImagesContent`)
- **BREAKING:** Renamed package `pipelex.pipe_works` to `pipelex.pipe_run` and moved `PipeRunParams` classes into it
- **BREAKING:** Cost reporting changed from Excel (xlsx) to CSV format using native Python csv module instead of pandas
- Renamed `ConfigManager` to `ConfigLoader`
- Renamed `PipelexRegistryModels` to `CoreRegistryModels`
- Renamed `PipelexTestModels` to `TestRegistryModels`
- Renamed `generate_jinja2_context()` to `generate_context()` in `WorkingMemory` and `ContextProviderAbstract`
- Renamed `ConceptProviderAbstract` to `ConceptLibraryAbstract`
- Renamed `DomainProviderAbstract` to `DomainLibraryAbstract`
- Renamed `PipeProviderAbstract` to `PipeLibraryAbstract`
- Renamed `PipeInputSpec` to `InputRequirements`
- Renamed `PipeInputSpecFactory` to `InputRequirementsFactory`
- Renamed `pipe_input.py` to `input_requirements.py`
- Renamed `pipe_input_factory.py` to `input_requirements_factory.py`
- Renamed `pipe_input_blueprint.py` to `input_requirement_blueprint.py`
- Changed hub methods from `get_*_provider()` to `get_*_library()` pattern
- Changed hub methods from `set_*_provider()` to `set_*_library()` pattern
- Changed `PipeLLM` validation to check all inputs are in required variables
- Updated `LLMPromptSpec` to handle image collections (lists/tuples) in addition to single images
- Changed Mermaid diagram URL generation from `/img/` to `/svg/` endpoint
- Changed `PipeLLMPromptTemplate.make_llm_prompt()` to private method `_make_llm_prompt()`
- Updated pipe-builder prompts to include concept specs for better context
- Updated `PipelexBundleSpec.to_blueprint()` to sort pipes by dependencies before creating bundle
- Changed exception base class from `PipelexError` to `PipelexError` throughout codebase
- Updated Makefile pyright target to use `--pythonpath` flag correctly
- Enhanced `LibraryManager` to use `importlib.resources` for reliable PLX file discovery across all installation modes (wheel, source, relative path)
- Simplified `FuncRegistryUtils` to exclusively register functions with `@pipe_func` decorator (removed `decorator_names` and `require_decorator` parameters)
- Updated `ReportingManager` to get config directly instead of via constructor parameter
- Updated PipeFunc documentation to reflect `@pipe_func()` decorator requirement and auto-discovery from anywhere in project
- Added warnings about module-level code execution during auto-discovery to PipeFunc and StructuredContent documentation

### Fixed

- Fixed Makefile target `pyright` to use correct pythonpath flag
- Fixed bug with inputs of the `PipeLLM` where image inputs couldn't be used and tagged in prompts
- Fixed image input handling in `LLMPromptSpec` to support both single images and image collections
- Fixed template preprocessing to handle jinja2 templates correctly
- Fixed hard dependencies by moving imports to function scope in model_lists.py
- Updated README badge URL to point to main branch instead of feature/pipe-builder branch

### Removed

- Removed centralized `pipelex_libraries` folder system and `pipelex init libraries` command
- Removed config path parameters from `Pipelex.make()` (`relative_config_folder_path`, `config_folder_path`, `from_file`)
- Removed Gemini 1.5 series models: `gemini-1.5-pro`, `gemini-1.5-flash`, and `gemini-1.5-flash-8b`
- Removed `base_templates.toml` file (generic prompts moved to `pipelex.toml`)
- Removed `gpt-5-mini` from possible models in pipe-builder
- Removed useless functions in `LLMJobFactory`: `make_llm_job_from_prompt_factory()`, `make_llm_job_from_prompt_template()`, `make_llm_job_from_prompt_contents()`
- Removed `add_or_update_pipe()` method from PipeLibrary
- Removed `get_optional_library_manager()` method from PipelexHub
- Removed `get_optional_domain_provider()` and `get_optional_concept_provider()` methods from hub
- Removed unused test fixtures (apple, cherry, blueberry, concept_provider, pretty) from conftest.py
- Removed some Vision/Image description pipes from the base library, because we doubt they were useful as they were
- Removed pandas and openpyxl dependencies (including stubs: pandas-stubs, types-openpyxl)
- Removed Excel file generation for cost reports and `to_dataframe()` method from `CostRegistry`
- Removed `should_warn_if_already_registered` parameter from `func_registry.register_function()`
- Removed `decorator_names` and `require_decorator` parameters from `FuncRegistryUtils` methods
- Removed `_find_plx_files_in_dir()` and `_get_pipelex_plx_files_from_dirs()` methods from `LibraryManager` (refactored to `library_utils` module)
- Removed hardcoded excluded directories from `ClassRegistryUtils` and `FuncRegistryUtils` (now use `ScanConfig`)
- Removed `are_classes_equivalent()` and `has_compatible_field()` methods from `ClassRegistryUtils` (moved to `class_utils` module)

## [v0.11.0] - 2025-10-01

### Highlights

- **New pipe builder** pipeline to generate Pipes based on a brief in natural language: use the cli `pipelex build pipe "Your task"` to build the pipe.
- **New observer system:** inject your own class to observe and trace all details before and after each pipe run. We also provide a local observer that dumps the payloads to local JSONL files = new-line delilmited json, i.e. one json object per line.
- **Full refactoring of OCR and Image Generation** to use the same patterns as `LLM` workers and pipes.

### Added

- Added `claude-4.5-sonnet` to the model deck.
- Added a badge on the `README.md` to display the number of tests.
- Added new test cases for environment variable functions
- Added new documentation for `PipeFunc` on how to register functions.
- Added `pipelex show models [BACKEND_NAME]` command to list available models from a specific backend.

### Changed

- Renamed `llm_deck` terminology to `model_deck` throughout codebase and documentation, now that it's also used for OCR and Image Generation models
- Renamed `is_gha_testing` property to `is_ci_testing` in RuntimeManager
- Refactored `all_env_vars_are_set()` function to only accept a list of keys, single string support now uses `is_env_var_set()`
- Modified `any_env_var_is_placeholder()` to use new placeholder detection logic
- Updated test environment setup to use dynamic placeholder generation instead of hardcoded values

### Fixed

- Fixed logic error in `any_env_var_is_placeholder()` function - now correctly returns False when no placeholders are found

### Removed

- Removed `get_rooted_path()` and `get_env_rooted_path()` utility functions which were not used
- Removed hardcoded placeholder dictionary and `ENV_DUMMY_PLACEHOLDER_VALUE` constant in test setup
- Removed function `run_pipe_code` in pipe router because it was not relevant (used mostly in tests)
- Remove the use of `PipeCompose` in `PipeCondition`, to only use jinja2 directly, through the `ContentGenerator`
- Remove the template libraries from the pipelex libraries.
- Removed `claude-3.5-sonnet` and `claude-3.5-sonnet-v2` from the model deck.

## [v0.10.2] - 2025-09-18

### Added

- Unified OCR system using model handles instead of separate OcrHandle enum
- ModelType enum supporting LLM and TEXT_EXTRACTOR types
- Enhanced error handling in library loading with better validation messages
- Config template management with `config-template` and `cft` Makefile targets to update templates from the `.pipelex/` directory

### Changed

- ⚠️ Breaking changes:
  - Renamed `ocr_handle` to `ocr_model` in `PipeExtract` blueprint, so you'll need to update your PLX code accordingly
  - Updated .env.example file with slightly modified key names (more standard).
- OCR system now uses InferenceModelSpec with unified model handles
- Renamed `get_llm_deck()` to `get_model_deck()` and updated parameter names from `llm_handle` to `model_handle`
- Simplified OCR worker factory using plugin SDK matching
- Enhanced plugin system compatibility with InferenceModelSpec
- Improved error messages throughout system
- Improved management of placeholder environment variables for unit tests

### Removed

- Legacy OCR classes: OcrHandle, OcrPlatform, OcrEngine, OcrEngineFactory
- Obsolete configuration fields and setup methods
- PipelexFileError exception class

## [v0.10.1] - 2025-09-17

### Changed

- Enabled all backends, still required to pass all unit tests.
- A few tweaks to the base model deck.

## [v0.10.0] - 2025-09-17

### Highlight: New Inference Backend Configuration System

We've completely redesigned how LLMs are configured and accessed in Pipelex, making it more flexible and easier to get started:

- **Get started in seconds** with [Pipelex Inference](configuration/config-technical/inference-backend-config.md): Use a single API key to access all major LLM providers (OpenAI, Anthropic, Google, Mistral, and more)
- **Flexible backend configuration**: Configure multiple inference backends (Azure OpenAI, Amazon Bedrock, Vertex AI, etc.) through simple TOML files in `.pipelex/inference/`
- **Smart model routing**: Automatically route models to the right backend using [routing profiles](configuration/config-technical/inference-backend-config.md#routing-profiles) with pattern matching
- **User-friendly aliases**: Define shortcuts like `best-claude` → `claude-4.1-opus` with optional fallback chains
- **Cost-aware model specs**: Each model includes detailed pricing, capabilities, and constraints for better cost management

For complete details, see the [Inference Backend Configuration](configuration/config-technical/inference-backend-config.md) documentation.

### Added

- New inference backend configuration system in `.pipelex/inference/` directory
- Support for 10+ inference backends: OpenAI, Anthropic, Azure OpenAI, Amazon Bedrock, Mistral, Vertex AI, XAI, BlackboxAI, Perplexity, Ollama, and **Pipelex Inference**
- Model routing profiles with pattern matching (`*model*`, `model*`, `*model`)
- Model aliases with waterfall fallback chains
- Environment variable and secret substitution in TOML configs (`${VAR}` and `${secret:KEY}`)
- Comprehensive model specifications with detailed cost categories
- Unified plugin SDK registry for all backends
- CI environment detection with automatic placeholder API keys for testing
- Improved `pipelex init config` command to copy entire configuration template directory structure to `.pipelex/` with smart file handling (skips existing files, shows clear progress messages)
- Added `FuncRegistryUtils` to register functions in a pipelex folder that have a specific signature.
- Added `mistral-medium` and `mistral-medium-2508` to the Mistral backend configuration.
- Added `gemini-2.5-flash` to the VertexAI backend configuration.

### Changed

- LLM configuration moved from `pipelex_libraries/llm_deck/` to `.pipelex/inference/deck/`
- LLM handles simplified to direct model names or user-defined aliases
- Model deck completely redesigned with inference models, aliases, and presets
- Plugin system refactored to use backend-specific TOML configuration
- Token categories renamed to cost categories with expanded types

### Fixed

- Improved error messages for missing environment variables
- Enhanced TOML configuration validation
- More robust model routing and backend selection

### Removed

- Legacy LLM model library system (`llm_integrations/` directory)
- Platform-specific configuration classes (AnthropicConfig, OpenAIConfig, etc.)
- Deprecated LLM engine blueprint and factory classes
- Old LLM platform and family enumerations

### Security

- Enhanced secret management with secure fallback patterns
- Improved API key handling through centralized backend configuration

## [v0.9.5] - 2025-09-12

### Highlight

- Pinned `instructor` to version `<1.10.0` to avoid errors with `mypy`

### Added

- Added `PIPELEX_INFERENCE` LLM family enum value
- Added support for `PIPELEX_INFERENCE` in OpenAI LLM worker
- Added Azure OpenAI platform support for Grok models (`grok-3` and `grok-3-mini`)
- Added debug logging for `PipeParallel` output contents
- Added `TOML` file filtering in LLM model library loading
- Added error handling for Unicode decode errors in LLM model library
- Added new test model configurations for `pipelex` and `vertex_ai` platforms

### Changed

- Improved error messages in `StuffFactory` to include concept code and stuff name
- Disabled `is_gen_object_supported` for all Grok models (`grok-3`, `grok-3-mini`, `grok-3-fast`)
- Updated test configurations to use different LLM models and platforms
- Modified `Jinja2` filter to use default `TagStyle.TICKS` instead of raising error
- Added proper error handling for Unicode decode errors when loading model libraries
- Improved error handling in Anthropic plugin tests with specific `AuthenticationError` handling
- Image handling in `AnthropicFactory` now converts image URLs to `base64` data URLs with proper MIME type prefix
- Put back Discord link in `README.md`

### Fixed

- Pinned `instructor` to version `<1.10.0` to avoid errors with `mypy`

## [v0.9.4] - 2025-09-06

### Added

- Added support for BlackboxAI models

## [v0.9.3] - 2025-09-06

### Added

- Better support for BlackboxAI IDE
- VS Code extensions recommendations file with Pipelex, Ruff, and MyPy extensions
- File association for .plx files in VS Code settings

## [v0.9.2] - 2025-09-05

### Fixed

- Fix the rules of all agents.

### Added

- Added agent rule for copilot
- Added a rule to forbidden structuring basic text concepts

## [v0.9.1] - 2025-09-05

### Fixed

- Fixed many inconsistencies in the documentation.

## [v0.9.0] - 2025-09-02

### Refacto

- Changed the pipeline file extension from `.toml` to `.plx`: Updated the LibraryManager in consequence.

## Fixed

- Fixed the `structuring_method` behavior in the `PipeLLM` pipe: Putting it to `preliminary_text`, the `PipeLLM` will always generate text before generating the structure -> Reliability increased by a lot.

### Fixed

- Fixed a bug in the `needed_inputs` method of the `PipeSequence` pipe.

### Changed

- `dry_run_pipe` now returns a `DryRunOutput` object instead of a `str` with additional information.
- Updated `cocode` dependency from version `v0.0.10` to `v0.0.15`.

### Added

- Added the `FuncRegistryUtils` class to register functions in the library.

## [v0.8.1] - 2025-08-27

### Bugfix

- Bugfix: Fixed the `PipeFunc` output concept code and structure class name in the dry run.

## [v0.8.0] - 2025-08-27

### Refactor

- Refactored the concepts: Blueprints are now more explicit, and hold only concept strings or code. Pipes hold concept instances.
- Organized code: Created subfolders for controller and operator pipes.
- Say goodbye to `PipeLLMPrompt`.
- Removed the `PipeCompose` and `PipeLLMPrompt` from the `PipeLLM`.

### Added

- Added a lot of unit tests.
- Loading the library can now be done from toml file or from `PipelexBundleBlueprint`.

### Fixed

- Backported `backports.strenum` to `>=1.3.0` to support Python 3.10 now in dependencies and not in optional dependencies.

## [v0.7.0] - 2025-08-20

### Refactor

- Refactored the Blueprints. Introduces the `PipelexInterpreter` that interprets the Pipelex language and creates the Pipelex Blueprints (and vice versa)
- Modified the way we declare pipes. Use the field `type = "PipeLLM"` instead of field `PipeLLM`. (Same for all pipes)
- Refactored the `LibraryManager`.
- Refactored CLI commands and added new ones. Modified CLI command structure:
  - **`pipelex init`** - Initialization commands
    - `pipelex init libraries [DIRECTORY]` - Initialize pipelex libraries (creates `pipelex_libraries` folder)
    - `pipelex init config` - Initialize pipelex configuration (creates `pipelex.toml`)
  - **`pipelex validate`** - Validation and dry-run commands
    - `pipelex validate all -c pipelex/libraries` - Validate all libraries and dry-run all pipes
    - `pipelex validate pipe PIPE_CODE` - Dry run a single pipe by its code
  - **`pipelex show`** - Show and list commands
    - `pipelex show config` - Show the pipelex configuration
    - `pipelex show pipes` - List all available pipes with descriptions
    - `pipelex show pipe PIPE_CODE` - Show a single pipe definition
  - **`pipelex migrate`** - Migration commands
    - `pipelex migrate run` - Migrate TOML files to new syntax (with `--dry-run` and `--backups` options)
  - **`pipelex build`** - Build artifacts like pipeline blueprints
    - `pipelex build draft PIPELINE_NAME` - Generate a draft pipeline
    - `pipelex build blueprint PIPELINE_NAME` - Generate a pipeline blueprint
- Organized `concept`, `pipe`, `working_memory`, `stuff` files into folders.

### Changed

- Allow `aiofiles` version `>=23.2.1`
- GHA Cla assistant fixed with Github App

### Added

- New LLM families `LLMFamily.GPT_5`, `LLMFamily.GPT_5_CHAT` and `LLMFamily.CLAUDE_4_1`
- Added support for Claude 4.1 and GPT 5 models (inc. mini, nano, chat)
- New Pipe that generates pipe. Pipe code: `build_blueprint`
- New tests. Especially for the `PipelexInterpreter`.
- Migration files and cli commands to migrate Pipelex language to new syntax.
- Introduces `PipelexBundle`, which correspond to the python paradigm of the Pipelex TOML syntax.

## [v0.6.10] - 2025-08-02

### Added

- New test file for source code manipulation functions (tests/cases/source_code.py)
- New integration test for PipeFunc functionality (tests/integration/pipelex/pipes/pipe_operator/pipe_func/test_pipe_func.py)
- New package structure file for pipe_func tests (**init**.py)
- Simplified input memory creation for native concepts (Text, Image, PDF) in pipeline execution
- Added Pipeline requests link to GitHub issue template config

### Changed

- Updated pipeline execution documentation and examples to use input_memory instead of working_memory
- Renamed pipeline from 'extract_page_contents_from_pdf' to 'ocr_page_contents_from_pdf'
- Renamed pipeline from 'extract_page_contents_and_views_from_pdf' to 'ocr_page_contents_and_views_from_pdf'
- Updated cocode dependency from version 0.0.6 to 0.0.9

### Fixed

- Fixed typo in pipeline description ('aspage views' to 'as full page views')

### Removed

- Removed WorkingMemoryFactory and StuffFactory imports from pipeline execution examples
- Removed working memory creation code from pipeline examples

## [v0.6.9] - 2025-07-26

### Changed

Simplified input memory:

- The concept code can now be provided with arg named `concept` in addition to `concept_code`
- You can pass a simple string to create a `Text` stuff

## [v0.6.8] - 2025-07-25

### Added

- New method `make_stuff_using_concept_name_and_search_domains` in `StuffFactory` for creating stuff using concept names and search domains.
- New method `make_stuff_from_stuff_content_using_search_domains` in `StuffFactory` for creating stuff from stuff content using search domains.
- New method `make_from_implicit_memory` in `WorkingMemoryFactory` for creating working memory from implicit memory.
- New method `create_mock_content` in `WorkingMemoryFactory` for creating mock content for requirements.

### Changed

- Refactored `PipeInput` to use `InputRequirement` and `TypedNamedInputRequirement` classes instead of plain strings for input specifications.
- Updated `WorkingMemoryFactory` to handle `PipelineInputs` instead of `CompactMemory`.
- Replaced `ExecutePipelineException` with `PipelineInputError` in `execute_pipeline` function.
- Updated `PipeBatch`, `PipeCondition`, `PipeParallel`, `PipeSequence`, `PipeFunc`, `PipeImgGen`, `PipeCompose`, `PipeLLM`, and `PipeExtract` classes to use `InputRequirement` for input handling.
- Updated `PipeInput` creation in various test files to use `make_from_dict` method.
- Updated `pyproject.toml` to exclude `pypdfium2` version `4.30.1`.
- Updated `Jinja2TemplateCategory` to handle HTML and Markdown templates differently.

### Fixed

- Corrected error messages in `StuffFactory` and `StuffContentFactory` to provide more detailed information about exceptions.

## [v0.6.7] - 2025-07-24

### Removed

- Removed the `structure_classes` parameter from the `Pipelex` class.

## [v0.6.6] - 2025-07-24

### Added

- Added a new method `verify_content_type` in the `Stuff` class to verify and convert content to the expected type.
- Added `cocode==0.0.6` to the development dependencies in `pyproject.toml`.

### Changed

- Updated `Stuff` class methods to use the new `verify_content_type` method for content verification.
- Updated `vertexai.toml` to change LLM IDs from preview models to released models: `gemini-2.5-pro` and `gemini-2.5-flash`.

### Removed

- Removed `reinitlibraries`, `rl`, `v`, and `init` targets from the Makefile.

## [v0.6.5] - 2025-07-21

### Fixed

- In the documentation, fixed the use of `execute_pipeline`.

## [v0.6.4] - 2025-07-19

- Fixed the `README.md` link to the documentation

## [v0.6.3] - 2025-07-18

### Changed

- Enhanced `Stuff.content_as()` method with improved type validation logic - now attempts model validation when `isinstance` check fails

## [v0.6.2] - 2025-07-18

### Added

- New `dry-run-pipe` cli command to dry run a single pipe by its code
- New `show-pipe` cli command to display pipe definitions from the pipe library
- New `dry_run_single_pipe()` function for running individual pipe dry runs

### Changed

- Updated `init-libraries` command to accept a directory argument and create `pipelex_libraries` folder in specified location
- Updated `validate` command to use `-c` flag for the config folder path

## [v0.6.1] - 2025-07-16

- Can execute pipelines with `input_memory`: It is a `CompactMemory: Dict[str, Dict[str, Any]]`

## [v0.6.0] - 2025-07-15

### Changed

- **Enhanced `Pipelex.make()` method**: Complete overhaul of the initialization method with new path configuration options and robust validation:
  - Added `relative_config_folder_path` and `absolute_config_folder_path` parameters for flexible config folder specification
  - The `from_file` parameter controls path resolution: if `True` (default), relative paths are resolved relative to the caller's file location; if `False`, relative to the current working directory (useful for CLI scenarios)
- Renamed Makefile targets like `make doc` to `make docs` for consistency

### Added

- Added github action for inference tests
- `load_json_list_from_path` function in `pipelex.tools.misc.file_utils`: Loads a JSON file and ensures it contains a list.
- Added issue templates
- Updated Azure/OpenAI integrations, using dated deployment names systematically

## [v0.5.2] - 2025-07-11

- log a warning when dry running a `PipeFunc`
- Update Readme.md

## [v0.5.1] - 2025-07-09

## Fixed

- Fixed the `ConceptFactory.make_from_blueprint` method: Concepts defined in single-line format no longer automatically refine `TextContent` when a structure class with the same name exists
- `ConceptFactory.make_concept_from_definition` is now `ConceptFactory.make_concept_from_definition_str`

## Added

- Bumped `kajson` to `v0.3.0`: Introducing `MetaSingleton` for better singleton management
- Unit tests for `ConceptLibrary.is_compatible_by_concept_code`

## [v0.5.0] - 2025-07-01

### Highlight: Vibe Coding an AI workflow becomes a reality

**Create AI workflows from natural language without writing code** - The combination of Pipelex's declarative language, comprehensive Cursor rules, and robust validation tools enables AI assistants to autonomously iterate on pipelines until all errors are resolved and workflows are ready to run.

### Added

- **Complete Dry Run & Static Validation System** - A comprehensive validation framework that catches configuration and pipeline errors before any expensive inference operations.
- **WorkingMemoryFactory Enhancement**: New `make_for_dry_run()` method creates working memory with realistic mock objects for zero-cost pipeline testing
- **Enhanced Dry Run System**: Complete dry run support for all pipe controllers (`PipeCondition`, `PipeParallel`, `PipeBatch`) with mock data generation using `polyfactory`
- **Comprehensive Static Validation**: Enhanced static validation with configurable error handling for missing/extraneous input variables and domain validation
- **TOML File Validation**: Automatic detection and prevention of trailing whitespaces, formatting issues, and compilation blockers in pipeline files
- **Pipeline Testing Framework**: New `dry_run_all_pipes()` method enables comprehensive testing of entire pipeline libraries
- **Enhanced Library Loading**: Improved error handling and validation during TOML file loading with proper exception propagation

### Configuration

- **Dry Run Configuration**: New `allowed_to_fail_pipes` setting allows specific pipes (like infinite loop examples that fail on purpose) to be excluded from dry run validation
- **Static Validation Control**: Configurable error reactions (`raise`, `log`, `ignore`) for different validation error types

### Documentation & Development Experience

- **Cursor Rules Enhancement**: Comprehensive pipe controller documentation covering `PipeSequence`, `PipeCondition`, `PipeBatch`, and `PipeParallel`, improved PipeOperator documentation for `PipeLLM`, `PipeOCR`
- **Pipeline Validation CLI**: Enhanced `pipelex validate all -c pipelex/libraries` command with better error reporting and validation coverage
- **Improved Error Messages**: Better formatting and context for pipeline configuration errors

### Changed

- **Error Message Improvements**: Updated PipeCondition error messages to reference `expression_template` instead of deprecated `expression_jinja2`

## [v0.4.11] - 2025-06-30

- **LLM Settings Simplification**: Streamlined LLM choice system by removing complex `for_object_direct`, `for_object_list`, and `for_object_list_direct` options. LLM selection now uses a simpler fallback pattern: specific choice → text choice → overrides → defaults.
- **Image Model Updates**: Renamed `image_bytes` field to `base_64` in `PromptImageTypedBytes` for better consistency. Updated to use `CustomBaseModel` base class to benefit from bytes truncation when printing.

## [v0.4.10] - 2025-06-30

- Fixed a bad import statement

## [v0.4.9] - 2025-06-30

### Highlights

**Plugin System Refactoring** - Complete overhaul of the plugin architecture to support external LLM providers.

### Added

- **External Plugin Support**: New `LLMWorkerAbstract` base class for integrating custom LLM providers, and we don't mean only an OpenAI-SDK-based LLM with a custom endpoint, now the implementation can be anything, as long as it implements the `LLMWorkerAbstract` interface.
- **Plugin SDK Registry**: Better management of SDK instances with proper teardown handling
- **Enhanced Error Formatting**: Improved Pydantic validation error messages for enums

### Changed

- **Plugin Architecture**: Moved plugin system to dedicated `pipelex.plugins` package
- **LLM Workers**: Split into `LLMWorkerInternalAbstract` (for built-in providers) and `LLMWorkerAbstract` (for external plugins)
- **Configuration**: Plugin configs moved from main `pipelex.toml` to separate `pipelex_libraries/plugins/plugin_config.toml` (⚠️ breaking change)
- **Error Handling**: Standardized credential errors with new `CredentialsError` base class

## [v0.4.8] - 2025-06-26

- Added `StorageProviderAbstract`
- Updated the changelog of `v0.4.7`: Moved `Added StorageProviderAbstract` to `v0.4.8`

## [v0.4.7] - 2025-06-26

- Added an API serializer: introducing the `compact_memory`, a new way to encode/decode the working memory as json, for the API.
- When creating a Concept with no structure specified and no explicit `refines`, set it to refine `native.Text`
- `JobMetadata`: added `job_name`. Removed `top_job_id` and `wfid`
- `PipeOutput`: added `pipeline_run_id`

## [v0.4.6] - 2025-06-24

- Changed the link to the doc in the `README.md`: https://docs.pipelex.com

## [v0.4.5] - 2025-06-23

### Changed

- **Test structure overhaul**: Reorganized test directory structure for better organization:
  - Tests now separated into `unit/`, `integration/`, and `e2e/` directories
  - Created `tests/cases/` package for pure test data and constants
  - Created `tests/helpers/` package for test utilities
  - Cleaned up test imports and removed empty `__init__.py` files
- **Class registry refactoring**: Updated kajson from 0.1.6 to 0.2.0, adapted to changes in [Kajson](https://github.com/Pipelex/kajson)'s class registry with new `ClassRegistryUtils` (better separation of concerns)
- **Dependency updates**:
  - Added pytest-mock to dev dependencies for improved unit testing

### Added

- **Coverage commands**: New Makefile targets for test coverage analysis:
  - `make cov`: Run tests with coverage report
  - `make cov-missing` (or `make cm`): Show coverage with missing lines
- **Test configuration**: Set `xfail_strict = true` in pytest config for stricter test failure handling
- **Pydantic validation errors**: Enhanced error formatting to properly handle model_type errors

### Fixed

- **External links**: Removed broken Markdown target="\_blank" syntax from MANIFESTO.md links
- **Variable naming consistency**: Fixed redundant naming in OpenAI config (openai_openai_config → openai_config)
- **Makefile optimization**: Removed parallel test execution (`-n auto`) from codex-tests, works better now

### Tests

- **Unit tests added**: New comprehensive unit tests for:
  - `ClassRegistryUtils`
  - `FuncRegistry`
  - `ModuleInspector`
  - File finding utilities

## [v0.4.4] - 2025-06-20

### Fixed

- Changed the allowed base branch names in the GHA `guard-branches.yml`: `doc` -> `docs`
- Fixed `kajson` dependency (see [kajson v0.1.6 changelog](https://github.com/Pipelex/kajson/blob/main/CHANGELOG.md))

### Cursor rules

- Added Cursor rules for coding best practices and standards (including linting methods). Added TDD (Test Driven Development) rule on demand.
- Various changes

### Documentation

- Added documentation for referencing images in PipeLLM.
- Fixed typos

### Refactor

- Removed the `images` field from PipeLLM - images can now be referenced directly in the `inputs`
- Moved the list-pipes CLI function to the `PipeLibrary` class.

## [v0.4.3] - 2025-06-19

### Fixed

- **Removed deprecated Gemini 1.5 models**: Removed `gemini-1.5-flash` and `gemini-1.5-pro` from the VertexAI integration as they are no longer supported
- Fixed multiple import statements across the codebase

### Documentation

- **Enhanced MkDocs search**: Added search functionality to the documentation site
- **Proofreading improvements**: Fixed various typos and improved clarity across documentation

### Refactor

- Mini refactor: changed kajson dependency to `kajson==0.1.5` (instead of `>=`) to tolerate temporary breaking changes from kajson

## [v0.4.2] - 2025-06-17

- Fixed the inheritance config manager method (Undocumented feature, soon to be removed)
- Fixed the `deploy-doc.yml` GitHub Action
- Grouped the mkdocs dependencies in a single group `docs` in the `pyproject.toml` file

## [v0.4.1] - 2025-06-16

- Changed discord link to the new one: https://go.pipelex.com/discord
- Added `hello-world` example in the `cookbook-examples` of the documentation.

## [v0.4.0] - 2025-06-16

### Highlight: Complete documentation overhaul

- **MkDocs** setup for static web docs generation
  - **Material** for MkDocs theme, custom styling and navigation
  - Other plugins: meta-manager, glightbox
  - **GitHub Pages** deployment, mapped to [docs.pipelex.com](http://docs.pipelex.com)
  - Added GHA workflows for documentation deployment and validation
- **Added to docs:**
  - [**Manifesto**](https://docs.pipelex.com/manifesto/) explaining the Pipelex viewpoint
  - [**The Pipelex Paradigm**](https://docs.pipelex.com/pages/pipelex-paradigm-for-repeatable-ai-workflows/) explaining the fundamentals of Pipelex's solution
  - [\*\*Cookbook examples](https://docs.pipelex.com/pages/cookbook-examples/)\*\* presented and explained, commented code, some event with [mermaid](https://docs.pipelex.com/pages/cookbook-examples/invoice-extractor/) [flow](https://docs.pipelex.com/pages/cookbook-examples/extract-gantt/) [charts](https://docs.pipelex.com/pages/cookbook-examples/write-tweet/)
  - And plenty of details about **using Pipelex** and **developing for Pipelex,** from **structured generation** to PipeOperators (**LLM**, **Image generation**, **OCR**…) to PipeControllers (**Sequence**, **Parallel**, **Batch**, **Condition**…), workflow **optimization**, workflow static **validation** and dry run… there's still work to do, but we move fast!
- **Also a major update of Cursor rules**

### Tooling Improvements

- Pipeline tracking: restored **visual flowchart generation using Mermaid**
- Enhanced dry run configuration: added more granular control with `nb_list_items`, `nb_extract_pages`, and `image_urls`
- New feature flags: better control over pipeline tracking, activity tracking, and reporting
- Improved OCR configuration: handle image file type for Mistral-OCR, added `default_page_views_dpi` setting
- Enhanced LLM configuration: **better prompting for structured generation with automatic schema insertion** for two-step structuring: generate plain text and then structure via Json
- Better logging: Enhanced log truncation and display for large objects like image bytes (there are still cases to deal with)

### Refactor

**Concept system refactoring**

- Improved concept code factory with better domain handling, so you no longer need the `native` domain prefix for native domains, you can just call them by their names: `Text`, `Image`, `PDF`, `Page`, `Number`…
- Concept `refines` attribute can now be a string for single refined concepts (the most common case)

### Breaking Changes

- File structure changes: documentation moved from `doc/` to `docs/`
- Configuration changes: some configuration keys have been renamed or restructured
- `StuffFactory.make_stuff()` argument `concept_code` renamed to `concept_str` to explicitly support concepts without fully qualified domains (e.g., `Text` or `PDF` implicitly `native` )
- Some method signatures have been updated

### Tests

- **Added Concept refinement validation:** `TestConceptRefinesValidationFunction` and `TestConceptPydanticFieldValidation` ensure proper concept inheritance and field validation

## [v0.3.2] - 2025-06-13

- Improved automatic insertion of class structure from BaseModel into prompts, based on the PipeLLM's `output_concept`. New unit test included.
- The ReportingManager now reports costs for all pipeline IDs when no `pipeline_run_id` is specified.
- The `make_from_str` method from the `StuffFactory` class now uses `Text` context by default.

## [v0.3.1] - 2025-06-10

### Added

- New pytest marker `dry_runnable` for tests that can run without inference.
- Enhanced `make` targets with dry-run capabilities for improved test coverage:
  - `make test-xdist` (or `make t`): Runs all non-inference tests **plus inference tests** that support dry-runs - fast and resource-efficient
  - `make test-inference` (or `make ti`): Runs tests requiring actual inference, with actual inference (slow and costly)
- Parallel test execution using `pytest-xdist` (`-n auto`) enabled for:
  - GitHub Actions workflows
  - Codex test targets

### Changed

- Domain validation is now less restrictive in pipeline TOML: the `description` attribute is now `Optional`

## [v0.3.0] - 2025-06-09

### Highlights

- **Structured Input Specifications**: Pipe inputs are now defined as a dictionary mapping a required variable name to a concept code (`required_variable` -> `concept_code`). This replaces the previous single `input` field and allows for multiple, named inputs, making pipes more powerful and explicit. This is a **breaking change**.
- **Static Validation for Inference Pipes**: You can now catch configuration and input mistakes in your pipelines _before_ running any operations. This static validation checks `PipeLLM`, `PipeExtract`, and `PipeImgGen`. Static validation for controller pipes (PipeSequence, PipeParallel…) will come in a future release.
  - Configure the behavior for different error types using the `static_validation_config` section in your settings. For each error type, choose to `raise`, `log`, or `ignore`.
- **Dry Run Mode for Zero-Cost Pipeline Validation**: A powerful dry-run mode allows you to test entire pipelines without making any actual inference calls. It's fast, costs nothing, works offline, and is perfect for linting and validating pipeline logic.
  - The new `dry_run_config` lets you control settings, like disabling Jinja2 rendering during a dry run.
  - This feature leverages `polyfactory` to generate mock Pydantic models for simulated outputs.
  - Error handling for bad inputs during `run_pipe` has been improved and is fully effective in dry-run mode.
  - One limitation: currently, dry running doesn't work when the pipeline uses a PipeCondition. This will be fixed in a future release.

### Added

- **`native.Anything` Concept**: A new flexible native concept that is compatible with any other concept, simplifying pipe definitions where input types can vary.
- Added dependency on `polyfactory` for mock Pydantic model generation in dry-run mode.

### Changed

- **Refactored Cognitive Workers**: The abstraction for `LLM`, `ImgGen`, and `Ocr` workers has been elegantly simplified. The old decorator-based approach (`..._job_func`) has been replaced with a more robust pattern: a public base method now handles pre- and post-execution logic while calling a private abstract method that each worker implements.
- The `b64_image_bytes` field in `PromptImageBytes` was renamed to `base_64` for better consistency.

### Fixed

- Resolved a logged error related to the pipe stack when using `PipeParallel`.
- The pipe tracker functionality has been restored. It no longer crashes when using nested object attributes (e.g., `my_object.attribute`) as pipe inputs.

### Tests

- A new pytest command-line option `--pipe-run-mode` has been added to switch between `live` and `dry` runs (default is `dry`). All pipe tests now respect this mode.
- Introduced the `pipelex_api` pytest marker for tests related to the Pipelex API client, separating them from general `inference` or `llm` tests.
- Added a `make test-pipelex-api` target (shorthand: `make ta`) to exclusively run these new API client tests.

### Removed

- The `llm_job_func.py` file and the associated decorators have been removed as part of the cognitive worker refactoring.

## [v0.2.14] - 2025-06-06

- Added a feature flag for the `ReportingManager` in the config:

```bash
[pipelex]
[pipelex.feature_config]
is_reporting_enabled = true
```

- Moved the reporting config form the `cogt`config to the Pipelex config.

## [v0.2.13] - 2025-06-06

- Added Discord badge on the Readme. Join the community! -> https://go.pipelex.com/discord
- Added a client for the Pipelex API. Join the waitlist -> https://www.pipelex.com/signup
- Removed the `run_pipe_code` function. Replaced by `execute_pipeline` in `pipelex.pipeline.execute`.
- Added llm deck `llm_for_img_to_text`.
- Renamed `InferenceReportManager` to `ReportingManager`: It can report more than Inference cost. Renamed `InferenceReportDelegate` to `ReportingProtocol`.
- Added an injection of dependency for `ReportingManager`
- pipelex cli: fixed some bugs

## [v0.2.12] - 2025-06-03

- pipelex cli: Split `pipelex init` into 2 separate functions: `pipelex init-libraries` and `pipelex init-config`
- Fixed the inheritance config manager method
- Rename Mission to Pipeline
- Enable to start a pipeline and let in run in the background, getting it's run id, but not waiting for the output
- `Makefile`: avoid defaulting pytest to verbose. Setup target `make test-xdist` = Run unit tests with `xdist`, make it the default for shorthand `make t`. The old `make t` is now `make tp` (test-with-prints)
- Added `mistral-small-3.1` and `qwen3:8b`
- Fix template pre-processor: don't try and substitute a dollar numerical like $10 or @25
- Refactor with less "OpenAI" naming for non-openai stuff that just uses the OpenAI SDK

## [v0.2.11] - 2025-06-02

- HotFix for v0.2.10 👇 regarding the new pipelex/pipelex_init.toml`

## [v0.2.10] - 2025-06-02

### Highlights

**Python Support Expansion** - We're no longer tied to Python 3.11! Now supporting Python 3.10, 3.11, 3.12, and 3.13 with full CI coverage across all versions.

**Major Model Additions** - Claude 4 (Opus & Sonnet), Grok-3, and GPT-4 image generation are now in the house.

### Pipeline Base Library update

- **New pipe** - `ocr_page_contents_and_views_from_pdf` transferred from cookbook to base library (congrats on the promotion!). This pipe extracts text, linked images, **AND** page_view images (rendered pages) - it's very useful if you want to use Vision in follow-up pipes

### Added

- **Template preprocessor** - New `@?` token prefix for optional variable insertion - if a variable doesn't exist, we gracefully skip it instead of throwing exceptions
- **Claude 4 support** - Both Opus and Sonnet variants, available through Anthropic SDK (direct & Bedrock) plus Bedrock SDK. Includes specific max_tokens limit reduction to prevent timeout/streaming issues (temporary workaround)
- **Grok-3 family support** - Full support via OpenAI SDK for X.AI's latest models
- **GPT-4 image generation** - New `gpt-image-1` model through OpenAI SDK, available via PipeImgGen. Currently saves local files (addressing in next release)
- **Gemini update** - Added latest `gemini-2.5-pro` to the lineup
- **Image generation enhancements** - Better quality controls, improved background handling options, auto-adapts to different models: Flux, SDXL and now gpt-image-1

### Refactored

- Moved subpackage `plugin` to the same level as `cogt` within **pipelex** for better visibility
- Major cleanup in the unit tests, hierarchy significantly flattened
- Strengthened error handling throughout inference flows and template preprocessing
- Added `make test-quiet` (shorthand `tq`) to Makefile to run tests without capturing outputs (i.e. without pytest `-s` option)
- Stopped using Fixtures for `pipe_router` and `content_generator`: we're now always getting the singleton from `pipelex.hub`

### Fixed

- **Perplexity integration** - Fixed breaking changes from recent updates

### Dependencies

- Added **pytest-xdist** to run unit tests in parallel on multiple CPUs. Not yet integrated into the Makefile, so run it manually with `pytest -n auto` (without inference) or `pytest -n auto -m "inference"` (inference only).
- Swapped pytest-pretty for pytest-sugar - because readable test names > pretty tables
- Updated instructor to v1.8.3
- All dependencies tested against Python 3.10, 3.11, 3.12, and 3.13

### Tests

- TestTemplatePreprocessor
- TestImgGenByOpenAIGpt
- TestImageGeneration
- TestPipeImgGen

## [v0.2.9] - 2025-05-30

- Include `pyproject.toml` inside the project build.
- Fix `ImgGenEngineFactory`: image generation (imgg) handle required format is `platform/model_name`
- pipelex cli: Added `list-pipes` method that can list all the available pipes along with their descriptions.
- Use a minimum version for `uv` instead of a fixed version
- Implement `AGENTS.md` for Codex
- Add tests for some of the `tools.misc`
- pipelex cli: Rename `pipelex run-setup` to `pipelex validate all -c pipelex/libraries`

## [v0.2.8] - 2025-05-28

- Replaced `poetry` by `uv` for dependency management.
- Simplify llm provider config: All the API keys, urls, and regions now live in the `.env`.
- Added logging level `OFF`, prevents any log from hitting the console

## [v0.2.7] - 2025-05-26

- Reboot repository

## [v0.2.6] - 2025-05-26

- Refactor: use `ActivityManagerProtocol`, rename `BaseModelTypeVar`

## [v0.2.5] - 2025-05-25

- Add custom LLM integration via OpenAI sdk with custom `base_url`

## [v0.2.4] - 2025-05-25

- Tidy tools
- Tidy inference API plugins
- Tidy WIP feature `ActivityManager`

## [v0.2.2] - 2025-05-22

- Simplify the use of native concepts
- Include "page views" in the outputs of Ocr features

## [v0.2.1] - 2025-05-22

- Added `OcrWorkerAbstract` and `MistralOcrWorker`, along with `PipeExtract` for OCR processing of images and PDFs.
- Introduced `MissionManager` for managing missions, cost reports, and activity tracking.
- Added detection and handling for pipe stack overflow, configurable with `pipe_stack_limit`.
- More possibilities for dependency injection and better class structure.
- Misc updates including simplified PR template, LLM deck overrides, removal of unused config vars, and disabling of an LLM platform id.

## [v0.2.0] - 2025-05-19

- Added OCR, thanks to Mistral
- Refactoring and cleanup

## [v0.1.14] - 2025-05-13

- Initial release 🎉
