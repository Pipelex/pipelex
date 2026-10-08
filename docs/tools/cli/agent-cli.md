---
description: "Use the pipelex-agent CLI for machine-oriented output — designed for AI agents, IDE extensions, and automation toolchains."
---

# Agent CLI (`pipelex-agent`)

The `pipelex-agent` CLI is a machine-oriented companion to the main `pipelex` CLI. It is designed for programmatic consumption by AI agents, IDE extensions, and other automation tools. Output format varies by command — markdown or JSON, raw TOML, or `plxt` passthrough — with no Rich formatting or interactive prompts. Structured commands emit errors to stderr; the error format is controlled by `--error-format`, which defaults to the value of `--format` (so `--format json` flips both, as before the split). `fmt` and `lint` pass through native `plxt` output.

It is consumed by the `mthds-agent` CLI (from the `mthds` npm package) which itself is used by Claude Code skills, the VS Code extension, and can be called directly from the command line.

It ships in the same `cli` extra as the main CLI, `uv tool install "pipelex[cli]"`: its own output carries no Rich formatting, but the command modules it shares with `pipelex` import Rich.

## Global Options

| Option | Description |
|--------|-------------|
| `--version` | Print the version handshake — the runtime version, the MTHDS Protocol version and the MTHDS standard version — and exit. Same three lines as `pipelex --version`; see the [CLI reference](index.md#the-version-handshake) |

There is no `--log-level` flag: `pipelex-agent` is machine-consumed, so logging is cut off process-wide by design.

!!! warning "`--runner api` is gone"
    The global `--runner pipelex|api` option and its MTHDS API runner path are removed. Where a run executes is now a `run` subcommand option, `--runner local|hosted`, and the hosted value runs on the hosted Pipelex API through pipelex-sdk, with the key in `PIPELEX_API_KEY` rather than `MTHDS_API_KEY`. A self-hosted runner is reached with `--runner hosted --base-url <origin>`. To target an arbitrary MTHDS runner, use the vendor-neutral `mthds-agent` CLI.

## Commands Overview

The agent CLI mirrors the main CLI's subcommand structure for `run`, `validate`, and `inputs`, each with `pipe`, `bundle`, and `method` subcommands. It also provides `fix bundle` for deterministic in-place repairs.

### Run

Execute a pipeline. Success output is markdown by default, or JSON with `--format json`. Errors follow `--error-format` (defaults to `--format`'s value).

```bash
pipelex-agent run pipe <PIPE_CODE> [OPTIONS]
pipelex-agent run bundle <PATH> [OPTIONS]
pipelex-agent run method <NAME> [OPTIONS]
```

**Common options:**

- `--inputs`, `-i` - Path to a JSON or TOML inputs file (discriminated by file extension: `.toml` → TOML, everything else → JSON). Inline JSON (a value starting with `{`) stays JSON-only.
- `--dry-run` - Dry-run without calling AI providers
- `--mock-inputs` - Use mock inputs (requires `--dry-run`)
- `--graph` / `--no-graph` - Enable/disable execution graph (enabled by default)
- `--library-dir`, `-L` - Additional library directory
- `--with-memory` - Include full working memory in output, each stuff naming its concept by ref (`"concept": "<domain>.<Code>"`); piped back into another `run` on stdin, the envelope's stuffs become that run's inputs, provided the receiving method declares the same `<domain>.<Code>` — the ref carries its domain, and a method declaring another one refuses it rather than guessing
- `--format` - Success output format: `markdown` (default) or `json`
- `--error-format` - Error output format: `markdown` or `json` (defaults to `--format`'s value)
- `--runner local|hosted` - Where the run executes: on this machine, or on the hosted Pipelex API. Defaults to `[run] execution` in `.pipelex/pipelex.toml` (see [Run Configuration](../../configuration/config-practical/run-config.md)), else `local`
- `--hosted` / `--local` - The same choice as `--runner`, spelled as the main CLI spells it. Given together, they must agree
- `--base-url <scheme://host[:port]>` - The origin a hosted run calls. Overrides `PIPELEX_BASE_URL`, which overrides `https://api.pipelex.com`; refused on a run that executes locally

For `bundle` and `method`, use `--pipe` to target a specific pipe.

#### Running on the hosted API

With `--runner hosted` (or `--hosted`, or `[run] execution = "hosted"`), the run executes on the hosted Pipelex API and nothing local is booted: no provider key or inference configuration is needed on this machine, only a Pipelex API key in `PIPELEX_API_KEY` (in the shell, or in `~/.pipelex/.env`). What the run sends is what a local run would load. `run bundle` sends the bundle, then every `.mthds` file of its library directories. `run pipe` sends its library directories' files (the installed method exporting the pipe and `-L`, else `PIPELEXPATH`) and is refused when it has none. `run method` sends an installed or local method's files, but a published address (`github.com/owner/repo[/name][@tag]`) goes as a `method_ref` and a stored method's catalog id (`mt_…`) as a `method_id`, both resolved by the hosted API, so nothing is fetched or read locally and `-L` is refused with them. A local file named at a document or image input is uploaded first (a relative path in an inputs file resolves against that file's directory, and a `file://` URI is read as its path), and the run's inputs carry its storage URI; an explicit `null`, such as an optional image left out, reaches the run as `null`. The method's signature is read only when some value of the inputs names an existing file on this machine, so inputs naming none go straight to the run, a method calling another one by its address included. Such a method cannot have a local file uploaded yet: give the file as an `https://` URL. `run bundle` on a bundle file with no `-L` sends `PIPELEXPATH`'s files too, as a local run loads them, and `run method` takes a method installed under a name spelled like a catalog id (`mt_reports`) as that method. `--dry-run` and `--mock-inputs` are refused on a hosted run.

The success envelope has the shape of a local run's. Compact, it is the main output's content. With `--with-memory`, `main_stuff.json` is that content (the hosted API renders no Markdown, so the markdown output shows the JSON), `working_memory` is the whole working memory, `pipeline_run_id` names the run on the hosted API, and `uploads` lists the files uploaded for it. A hosted run writes nothing to disk.

A run refuses an invalid bundle while loading it, before any pipe runs, with exit code `1` and an error envelope whose `error_type` is `ValidateBundleError` and whose `validation_errors` array holds the items `validate` gives for that bundle, each with its pipe, its field and its suggested fix when it has one. A refusal found while loading a library directory you pass with `-L` (or the bundle's own directory) is reported the same way, its items naming their file in `source`; a bundle file run on its own is loaded from its text, so the items of a refusal found while loading it carry no `source`, while a bundle that does not parse when `run bundle` looks for its `main_pipe` (no `--pipe`) names its file. In markdown, the items render as the same grouped prose `validate` prints.

!!! note "Stdin inputs stay JSON"
    The agent CLI can also read inputs from stdin (a flat dict or a `working_memory` envelope). Stdin inputs are **JSON-only** — the extension-based TOML discrimination applies to `--inputs` file paths only. Like the main CLI, `run bundle <dir>` auto-detects `inputs.json` / `inputs.toml` when `--inputs` is omitted, erroring if both exist. In a `working_memory` envelope each stuff must name its concept as the ref string; anything else there — the full concept object an older runtime dumped, for instance — is refused under `"error_type": "StdinEnvelopeShapeError"`, which is the label for an envelope that parsed as JSON but does not hold the shape the contract asks for, as distinct from the `JSONDecodeError` that means the JSON itself did not parse.

### Validate

Validate pipes, bundles, or methods. Success output is markdown by default, or JSON with `--format json`. Errors follow `--error-format` (defaults to `--format`'s value).

```bash
pipelex-agent validate pipe <PIPE_CODE> [OPTIONS]
pipelex-agent validate pipe --all [OPTIONS]
pipelex-agent validate bundle <PATH> [OPTIONS]
pipelex-agent validate method <NAME> [OPTIONS]
```

**Common options:**

- `--library-dir`, `-L` - Additional library directory
- `--allow-signatures` - Accept [`PipeSignature`](../../building-methods/pipes/signature-pipes.md) placeholders in the dependency graph (lenient mode)
- `--format` - Success output format: `markdown` (default) or `json`
- `--error-format` - Error output format: `markdown` or `json` (defaults to `--format`'s value)

For `bundle`, additional options are available:

- `--pipe` - Require a specific pipe in the bundle
- `--graph`, `-g` - Generate an execution graph visualization
- `--graph-format`, `-f` - Graph output format (`mermaidflow`, `reactflow`, or `both`)
- `--direction` - Graph layout direction

!!! note "Signature pipes"
    `pipelex-agent validate` is strict by default — same as `pipelex validate`. A bundle whose dependency graph reaches a `PipeSignature` is rejected unless you pass `--allow-signatures`, which dry-runs signatures as mocks.

    On a successful run, the envelope also carries `pending_signatures` — the library-wide list of pipes still declared as `PipeSignature` (unimplemented forward declarations), each namespaced by `pipe_ref` (`domain.code`). In JSON it is a `pending_signatures` array, in markdown a "Pending signatures" section. A top-down build reads it to see exactly which headers remain to implement. The envelope also carries a derived `is_runnable` boolean (`true` ⇔ `pending_signatures` is empty), and the markdown states the runnability verdict in plain English — runnable when complete, NOT yet runnable above the "Pending signatures" section otherwise. `validate bundle`, `validate method`, and `validate pipe --all` carry them and gate on them: without `--allow-signatures`, the command exits non-zero when `is_runnable` is false. Bare `validate pipe <code>` omits them, and a `--pipe` slice surfaces them for information without gating.

!!! note "Every refusal of the bundle is an invalid verdict"
    A refusal of your input raised while the bundle is loaded or validated is answered with the invalid-verdict envelope — `is_valid: false` and a `validation_errors` array — and exit code `1`, never the no-verdict envelope and exit code `2`, which is kept for failures of the tool or its environment. A pipe whose dry run fails gives one `dry_run` item per failing pipe, with `error_type: DryRunError`, the `pipe_code`, `domain_code` and `source` of the innermost pipe that failed and is not allowed to fail (its `source` whenever the pipe is in your files; a validator of submitted content beside a host's library directories names only that content's files), and a message that keeps the failure's own text only when it is caller-facing, on `validate bundle`, `validate pipe <code>` and `validate pipe --all` alike; a controller that failed because a pipe it runs failed is reported once, at that pipe. Every error found while parsing is its own item, so a misspelled field is reported beside the categorized errors as an item without an `error_type`, carrying its `pipe_code`, `source` and `field_path`. A TOML syntax error's item carries its 1-based `line` and `column`, and an `unresolved_concept` item lists the concepts the validated bundle declares in its domain in `declared_concepts`. A pipe naming a model the model deck does not define gives one `pipe_validation` item with `error_type: unknown_model`, carrying `pipe_code`, `domain_code`, `source`, `field_path` (`pipe.<code>.model`), `model_reference` (the reference as written), `model_type` and `suggestions` (the deck's close matches), plus a `rename-model` `suggested_fix` when there is exactly one suggestion. That fix's `safety` is `unsafe`, because a close name can still be a different model: `fix bundle` never applies it, and the Markdown labels it `💡 Suggested fix (unsafe, confirm before applying):` where a safe fix reads `💡 Suggested fix:`. Any other refusal of your input with no code of its own gives one item without an `error_type`, located on its pipe when it was raised while that pipe was built. A pipe factory's refusal, such as a `PipeExtract` whose input is neither an image nor a document, is one of these items, located on its pipe. See [Error Model](../../under-the-hood/error-model.md#validation_errors-structured-bundle-validation-diagnostics).

!!! note "Advisory warnings on validate"
    Whole-bundle and whole-library validate surfaces (`validate bundle`, `validate method`, `validate pipe --all`) also carry a `warnings` array — advisory optionality lints on a VALID bundle that never flip the verdict or the exit code. Each entry has the **same shape as a validation error item** (`category`, `error_type`, `pipe_code`, `domain_code`, `variable_names`, `message`) — this is a different shape from the `init`/`doctor` setup `warnings` (`{type, message}`) documented under Output Contract below. Three families ride the array, always in this order: the useless-`!` lint (`optional_force_redundant`), a `!` (force) input whose slot is guaranteed present in every analyzed flow, so the assertion can never fire; the vacuous-presence lint (`input_presence_vacuous`), an entry-pipe input that must be supplied but whose concept declares no required field, so the empty object satisfies it and a caller cannot tell what to fill in (see [Understanding Optionality](../../building-methods/pipes/understanding-optionality.md)); and the [intent-hint](../../building-methods/concepts/intent-hints.md) lints (`hint_unknown_key`, `hint_unknown_intent`, `hint_inapplicable_intent`). Every whole-bundle validate channel — this CLI, the bare CLI and the protocol validation report — assembles them from one composition point, so which advisories you see does not depend on which command you typed. Hint findings are bounded per site: a site naming many undefined keys reports the first few and then how many more there were, and a long authored key or value is elided in the message. In markdown, warnings render as a "Warnings" section. The array is empty when there is nothing to report; `validate pipe` omits it (no flow context to lint in). `validate bundle`/`validate method` with `--pipe` keep it, and it stays bundle-wide there — the slice narrows the dry run, not the validation.

### Fix

Apply deterministic safe fixes to a bundle, re-validating after each round until the bundle is valid, no applicable fix remains, or the iteration limit is reached.

```bash
pipelex-agent fix bundle <PATH> [OPTIONS]
```

**Options:**

- `--library-dir`, `-L` - Additional library directory; files in explicitly supplied directories may be fixed when an error identifies them as the source
- `--allow-signatures` - Accept `PipeSignature` placeholders during validation
- `--max-iterations` - Limit the number of validate/apply rounds
- `--select` - Apply only the named fix rule; repeat for multiple rules
- `--ignore` - Skip the named fix rule; repeat for multiple rules (`--select` and `--ignore` are mutually exclusive)
- `--format` - Success output format: `markdown` (default) or `json`
- `--error-format` - Error output format: `markdown` or `json` (defaults to `--format`'s value)

The result reports `iterations`, `fixes_applied`, `files_written`, and any `remaining_errors`. A fully valid result exits 0; a completed fix attempt that remains invalid exits 1; argument, setup, or unexpected failures exit 2.

### Inputs

Generate an example inputs template for a pipe, bundle, or method. By default the template is the **light** signature-driven shape (bare values matching the pipe's declared concepts), which is exactly what `run` accepts; `--explicit` emits the ceremonial `{concept, content}` envelope form instead.

```bash
pipelex-agent inputs pipe <PIPE_CODE> [OPTIONS]
pipelex-agent inputs bundle <PATH> [OPTIONS]
pipelex-agent inputs method <NAME> [OPTIONS]
```

**Common options:**

- `--library-dir`, `-L` - Additional library directory
- `--format` - Template serialization: `json` (default) or `toml`
- `--explicit` - Emit the ceremonial `{concept, content}` envelope form instead of the light values

For `bundle` and `method`, use `--pipe` to target a specific pipe.

The JSON success envelope names the pipe the template was generated for as `pipe_ref`, the qualified `domain.pipe_code` of the pipe that was resolved, whether you named it with a bare code, a qualified ref, or let it default to the bundle's `main_pipe`. A pipe you reached through a dependency alias keeps that alias, `alias->domain.pipe_code`, since that is the ref that selects it again:

```json
{
  "success": true,
  "pipe_ref": "my_domain.main_pipe",
  "inputs": { ... }
}
```

A pipe that declares no inputs is not an error: the envelope carries `"inputs": {}` and the command exits `0`; under `--format toml` it prints the comment `# Pipe 'my_domain.main_pipe' declares no inputs.`

!!! note "`inputs --format` is `json|toml`, not `markdown|json`"
    Unlike `run`/`validate`, the `inputs` command's `--format` selects the **template serialization**, not a presentation style. `json` (the default) emits the structured JSON success envelope; `toml` prints the raw TOML template straight to stdout (a pipe with no inputs prints a TOML comment line, which loads back as an empty dict). `inputs` has no `--error-format` — its errors stay JSON.

!!! note "`--explicit` and concept hints"
    The light `--format toml` template carries the declared concept for each key as a `# concept: ...` comment; the light `--format json` template (the default) cannot (JSON has no comments), so pass `--explicit` when you want the concept written out inline. The JSON success envelope shape (`success` / `pipe_ref` / `inputs`) is unchanged — only the `inputs` payload flips between the light values and the envelope form.

### Flat Commands

These commands do not have subcommands:

| Command | Description |
|---------|-------------|
| `init` | Initialize configuration non-interactively from `--config`: `execution` (`hosted` or `local`), `backends`, `primary_backend`; see [Non-Interactive Init](init.md#non-interactive-init-pipelex-agent-init) (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `fmt` | Format a `.mthds`/`.toml`/`.plx` file in-place (delegates to `plxt`) |
| `lint` | Lint a `.mthds`/`.toml`/`.plx` file for errors (delegates to `plxt`) |
| `models` | List available model presets, aliases, and waterfalls (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `check-model` | Check a model reference for a model category (`check-model <reference> --type <category>`, the category being `llm`, `extract`, `img_gen`, `search`, `judgment` or `doc_gen`) and suggest alternatives when it is not valid. It applies the rule a validation applies, as [`GET /v1/models/check`](../../api-server/models.md#check-a-model-reference) does: a sigiled reference names that kind of binding, and a bare name is valid when it is a model of the category, an alias of the category, or a waterfall of the category while model fallback is on; a `handle:` reference writes a bare name without reading a sigil, so `handle:@best-gpt` is the bare name `@best-gpt`, not the alias `best-gpt`. `--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value |
| `doctor` | Check config, credentials, and model health; a hosted setup (`[run] execution = "hosted"`) is judged by its Pipelex API key, reported in `checks.pipelex_api_key`, with `execution` at the top level and the provider credentials and models rows marked `informational` (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |

## Output Contract

Commands use different stdout formats depending on their purpose:

- **Markdown or JSON**: `run`, `validate`, `fix`, `init`, `models`, `check-model`, `doctor`, `migrate`, `codegen types`, `codegen check` — markdown by default, JSON with `--format json`. Error format follows `--error-format` (defaults to `--format`'s value, so `--format json` flips both).
- **JSON or raw TOML**: `inputs` — structured JSON via `agent_success()` by default (`--format json`), or the raw TOML template printed directly to stdout with `--format toml`
- **Passthrough**: `fmt`, `lint` — raw `plxt` output

**JSON success** — written to stdout:

```json
{
  "success": true,
  "target_dir": "/path/to/.pipelex",
  "backends_enabled": ["openai"]
}
```

JSON commands return the result object directly. They are not wrapped in a `status` or `data` envelope.

**Error** — written to stderr:

```json
{
  "error": true,
  "error_type": "specific_error_type",
  "message": "Human-readable description",
  "error_domain": "input",
  "hint": "Suggested fix or next step",
  "retryable": false
}
```

For the structured commands, exactly one such object is written to stderr per failure, so the stream parses as a single JSON document.

**A failed run** (`run pipe`, `run bundle`, `run method`) reports `"error_type": "PipelineExecutionError"` and adds four fields: `pipe_code` and `pipe_stack` name the pipe that failed and its path from the entry pipe, and `cause_type` and `cause_message` give the class and own message of the root fault, the innermost Pipelex error behind the failure. The `message` is that root fault's message prefixed with the failing pipe and its path (`Pipe 'summarize' failed (two_steps → summarize): …`), and the classification fields are the root fault's, so branch on `cause_type` to tell, say, a model that is not available from a failure to combine a parallel's results.

**A run the hosted API refuses** (`--runner hosted`, when the hosted API answers with a non-2xx status) reports what its problem document says, in the same envelope and the same markdown. `error_type` is the runner's error class: `ValidateBundleError` for a bundle refused before any pipe ran, as a local run reports it, or the root fault of a run that failed, such as `ModelNotFoundError` or `StuffFactoryError`, which a local run reports as `cause_type` under the `error_type` `PipelineExecutionError`. There is no `cause_type` on this path, so a consumer of a refused hosted run branches on `error_type`, which is `ApiResponseError` when the answer names no class, as a gateway's error page does not. The `message` quotes the request, the status and the runner's reason (`API POST /v1/start failed (422): Pipe 'condense_article' failed (digest_article → condense_article): …`), so on a failed run it names the failing pipe and its path. The `hint` is the runner's next step; `error_domain`, `error_category` and `retryable` are the runner's own; `validation_errors` holds the runner's items, rendered in markdown as the same grouped prose `validate` prints; `pipe_code` and `pipe_stack` appear when the problem document carries them; `error_code` is the problem's `code`, the stable code the hosted plane gives the refusals it authors itself (`rate_limited`, `unauthorized`); `retry_after_seconds` is the delay of a `Retry-After` header; and `http_status` and `request_id` are what to quote when the fault is the runner's. When the answer advised no next step, the `hint` follows its status, never the local advice kept for the runner's class: a 401 or a 403 points at `PIPELEX_API_KEY` and `pipelex login`; a 404 points at the method's address or id and at the origin (`--base-url`, else `PIPELEX_BASE_URL`, else `https://api.pipelex.com`, with no path such as `/v1`); a 429 says to wait and run again and marks the error `retryable` unless the answer said otherwise; a 503 says to wait too but warns that running again can repeat a paid run, because the service in front of the runner can answer it after the run completed, so it is `retryable` only when the answer says so; any other 4xx says to change what the message names; and any other status says to report the `request_id`, or the `http_status` when there is none.

**A hosted run that started and failed** reports its stored error report: `error_type` is the runner's class, `message` says the run's final status and reason, `hint` is the runner's next step, `error_domain`, `error_category`, `retryable`, `model`, `provider` and `validation_errors` are the report's when it carries them, and `pipeline_run_id` and `run_status` name the run. `retryable` is the runner's verdict whenever it gave one, `false` included, never the local default for its class. **A hosted run that failed on the way** carries its own class as `error_type`, with a next step for each: `ApiUnreachableError` (the network or the origin, `"error_domain": "config"`, only for a failure before the run request left this machine), `HostedRunOutcomeUnknownError` (the connection failed after the run request was sent, so a run may exist with no id returned: check the run history before running again), `RunTimeoutError` (the run keeps going on the hosted API past the wait), `PipelineExecuteTimeoutError` (a server that keeps no runs cut the blocking route before the result came back; the run may still be going, so it is `"retryable": false` and its hint points at the proxy's timeout or a base URL that keeps runs), `MissingMainStuffError` (the run completed and delivered no main output), `HostedRunPollingError` (the run started, then reading its result failed; it may still be running and is paid for, so look it up rather than run again), `HostedMethodInvalidError` (the method does not load, refused before any run starts when the inputs name a local file, its `validation_errors` naming each faulty file in `source`), `HostedLocalFileUploadUnavailableError` (the inputs name a local file and the method calls another one by its address: give the file as an `https://` URL), `InvalidLocalSourceError` (a local file in the inputs cannot be read), `UploadTransportError` (`config` when the upload never reached the hosted API, `runtime` when the hosted API failed it), `UploadAuthenticationError`, `RejectedAssetError` and the other upload failures, and `HostedBaseUrlError` for a base URL that is not an origin, refused before anything is sent. Every failure met once the hosted API acknowledged the run carries its `pipeline_run_id`. **An interrupted hosted run** (Ctrl-C) exits with `130` and the envelope `HostedRunInterruptedError`, whose `pipeline_run_id` names the run the hosted API had acknowledged: the run keeps going and is paid for. Interrupted before the acknowledgement, the envelope has no `pipeline_run_id` and its hint says to check the run history before running again. A configuration that cannot be read while deciding where the run executes gives the hint a failed local boot gives, and any other failure still leaves as this envelope, with the exception's class as `error_type`.

**`migration`** — a configuration error (`"error_domain": "config"`) carries an extra `migration` object when, and only when, a scan of this machine's configuration directories found something. Its presence says the migration history has something to report about these files; **`would_write` says whether a command repairs them.** The object holds `remedy` (the command that fixes what can be fixed), `would_write` (whether running it would rewrite any of these files), `needs_attention` (whether something there is a person's decision rather than the tool's), and `plans` — one per file, in the same shape [`pipelex-agent migrate`](migrate.md) emits under its own `plans` key. On `would_write: true` the loop is `pipelex-agent migrate --dry-run --format json`, show the user what would change, then `--yes`. On `would_write: false` there is nothing to run: the plans carry a path no ledger entry explains, or an entry blocked before anything applied, and the command would visit the files, write nothing and leave the same error standing — so read the plans and correct what they name. Never answer either one by re-initializing a configuration file — that discards every setting the migration would have kept.

`TelemetryConfigValidationError` carries it too, on the same terms: absent means the `telemetry.toml` is wrong and the fields the message names are what to correct, present with `would_write: true` means it is old, and present with `would_write: false` means it is both reported on and unrepairable by the command.

**`FormerReleaseConfigError`** — a boot on a configuration set up by a release that ran on the Pipelex Gateway, with its backend enabled or one of its routing profiles active, is refused with this error, which names what stops it with its file and carries no `migration` object: what is there is no stale shape but what that release left. The loop is the same, `pipelex-agent migrate --dry-run --format json`, whose `former_release` key lists each file the cleanup rewrites or removes and its changes, show the user, then `--yes`. On every run, `former_release.still_blocking` lists, one sentence each, whatever would still stop the boot once the cleanup is done: after `--yes`, read off the files written, and in a dry run, off the files as they would be written, so the plan already says when the cleanup alone will not be enough. When it is not empty, `needs_attention` is true and `is_clean` false, even with no file left to clean, and the machine is not fixed yet.

**A failure is not the only way to learn this, and for an agent it is not even the reliable one.** A configuration the migration history explains boots with a warning rather than an error — and `pipelex-agent` silences logging process-wide before anything can emit one, so no error arrives and the machine is still stale. `pipelex-agent doctor` is the channel that always answers: its `checks.pending_migrations` row carries a `finding` (`up_to_date`, `pending`, `needs_attention`, `unavailable`), the `migratable_files` a migration would rewrite, the `attention_files` it will not repair on its own, and the `former_release_files` its first step cleans up, with `former_release_blocks_boot` saying whether they stop this machine's boot, read off the files the boot merges in the current directory rather than off each directory alone. When the cleanup's own check finds that a boot would still not start once it has run, the row says so in its `message` and `recommended_actions` names `pipelex migrate --dry-run`, which says why; with nothing left to clean its `finding` is `needs_attention`, and that action is the row's only one. Branch on `finding`; `unavailable` means the check could not run and is not a claim that the machine is current. The row answers for both configuration directories even under `--global`, because it describes `pipelex migrate`, which has no such flag.

`fmt` and `lint` are raw passthroughs to the `plxt` binary and bypass the JSON output contract, producing native `plxt` output instead.

## Graph Visualization

Graph visualization is available through the `validate bundle` subcommand with the `--graph` flag, and through `run` subcommands where it is enabled by default. Use `--no-graph` on `run` to disable it.

A `run` with the graph on writes, beside its bundle, the ReactFlow viewer (`dry_run.html` or `live_run.html`) and the graph itself: `graphspec.json` on a dry run, `live_run_graph.json` on a live run. Beside the graph, under their canonical names whatever the graph file is called, sit the three files that describe its data: `pipe_io_contracts.json`, `input_form.json` and `output_form.json`, the same artifacts `validate` reports under those names, keyed by namespaced `pipe_ref`. A graph viewer resolves them from the graph file's directory, not from its name. With `--with-memory`, the JSON envelope's `graph_files` object names every one of these paths (`graph_html`, `graph_spec` on a live run, `pipe_io_contracts`, `input_form`, `output_form`).
