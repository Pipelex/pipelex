---
description: "What anonymous usage statistics Pipelex collects, what it never collects, and every way to turn them off."
---

# Usage Statistics

Pipelex collects **anonymous usage statistics**: counts of commands, runs, pipe types, models and tokens, and the country your IP address maps to. The address itself is never stored. Pipelex never collects your methods, prompts, inputs, outputs, file names or pipe names. The statistics tell us which features, pipe types and models people use, so we know where to put our work.

They are on by default, and you can turn them off at any time, for one command, one project or the whole machine, as [Turning them off](#turning-them-off) explains.

The first time a Pipelex tool runs with statistics on, it prints this notice on stderr, once per machine:

> Pipelex collects anonymous usage statistics: counts of commands, runs, pipe types, models and tokens, and the country your IP address maps to; the address itself is never stored. It never collects your methods, prompts, inputs, outputs, file names or pipe names. To turn it off, run `pipelex usage-stats disable` or set DO_NOT_TRACK=1. Details: https://docs.pipelex.com/latest/setup/usage-statistics/

!!! note "Not your telemetry"
    The usage statistics are separate from the telemetry you configure in `telemetry.toml`, which goes only to analytics and monitoring systems you operate and never to Pipelex. See [Telemetry](telemetry.md).

## What is collected

Every event is a count, a yes-or-no, or a value from a closed list. No property can hold text you wrote. Each event carries:

- the tool and its version (`pipelex`, and the release), and the surface it ran from: the `pipelex` CLI, the `pipelex-agent` CLI, the API server or a Python program;
- the operating system and processor family, the Python minor version, and whether the process ran in CI or in a container;
- an anonymous **installation identifier**, a random UUID drawn once per machine and shared by every Pipelex tool on it, never derived from anything about the machine or you.

The events themselves are:

| Event | Sent | What it counts |
| --- | --- | --- |
| `command_completed` | once per command of the `pipelex` and `pipelex-agent` CLIs | the command's path in the command tree (`run bundle`, `validate pipe`, `init` and so on, a shorthand such as `pipelex validate my_pipe` counting as the command it runs; never its arguments or option values), its outcome, its duration, who could fix a failure (`input`, `config`, `runtime` or `other`), and whether it ran on the hosted API; for `init`, also where it set runs to execute and, when it set up backends on this machine, which backend kinds it enabled |
| `run_completed` | once per run, whatever started it | the outcome, live or dry, the kind of source the method came from (a local bundle, an installed method, a published address), the duration, the bundle's size and nesting depth, which language features it used (batching, parallel branches, conditions, structured outputs, image and document inputs), how many pipes of each type ran, and its inference totals: calls, failures, tokens, images, pages and cost |
| `model_used` | once per model a run used | the backend kind (`openai`, `anthropic`, `mistral`, and so on, `custom` for a backend Pipelex does not ship), the model's name in the backend tables Pipelex ships (`other` for any other), and that run's calls, failures by category, tokens, images, pages and cost for it |
| `method_validated` | once per validation of a method | the verdict, the duration, the number of errors and warnings, and the bundle's size and depth |
| `code_generated` | once per code generation | what was generated (types, input templates or structure classes), the target language, the outcome, the duration and the bundle's size |

A run's token totals come from the run's own usage events: when you turn tracing or cost reporting off, the run reports that its usage is unknown and no `model_used` is sent. The statistics never turn tracing on.

### What is never collected

No event carries a method or its MTHDS source; a pipe code, concept name, domain name, class name or any other identifier you wrote; a prompt, input, output or generated content; a file name, path, URL or repository address; a method name, catalog id or run id; an error message, stack trace or exception; a command argument or option value; an environment variable's value; a hostname, user name or e-mail address; an IP address or any location finer than the country; the order in which a run's pipes executed.

A test in Pipelex runs, validates and generates code from a method whose every name, prompt, input and error message holds a unique marker, and fails if the marker appears anywhere in what would be sent.

## Turning them off

Statistics are on unless any of these says off, and nothing can turn them back on over another switch that says off:

| Switch | How to set it | Scope |
| --- | --- | --- |
| `DO_NOT_TRACK` | set to anything but empty, `0` or `false`, the [Console Do Not Track](https://consoledonottrack.com/) convention | the process, and every process it starts |
| `PIPELEX_USAGE_STATS` | set to `0`, `false`, `no` or `off`; an unrecognised value also turns statistics off | the process, without silencing the rest of your tools the way `DO_NOT_TRACK` does |
| The machine's choice | `pipelex usage-stats disable` | every Pipelex tool on the machine: pipelex, `plxt`, the VS Code extension and the `mthds` CLI |
| The `mthds` CLI's former opt-out | `DISABLE_TELEMETRY=1` in `~/.mthds/config`, which `mthds telemetry disable` wrote before these statistics existed | every Pipelex tool on the machine: the first tool that runs turns it into the machine's choice |
| The project setting | `[usage_stats] enabled = false` in the project's `.pipelex/pipelex.toml` | everyone working in the project, once the file is committed |
| The packaged default | `[usage_stats] enabled = false` in the `pipelex.toml` Pipelex is packaged with, for a distribution or a corporate image | every user of that installation |
| The `pytest` integration mode | Pipelex booted with `IntegrationMode.PYTEST`, as test suites do | the test process: no test suite reports |

The project setting can only turn statistics off: `enabled = true` has no effect. It fails closed: a `.pipelex/pipelex.toml` that cannot be read, is not valid TOML, or holds an `enabled` that is not a boolean turns them off. Pipelex reads it from the project's own file, found from the working directory the way Pipelex finds its project configuration, and never from your home configuration in `~/.pipelex/`.

```toml
# .pipelex/pipelex.toml
[usage_stats]
enabled = false
```

Turning statistics off creates nothing and sends nothing: a process with statistics off writes nothing to the shared state, except when it turns the `mthds` CLI's former opt-out into the machine's choice.

## The `usage-stats` commands

`pipelex usage-stats` shows and changes the statistics of every Pipelex tool on the machine, `pipelex-agent` included, which has no group of its own. These commands never send anything, never print the notice, and exit with `0` unless they could not do what they say.

| Command | What it does |
| --- | --- |
| `pipelex usage-stats status` | Prints whether statistics are on, every switch that turns them off, the installation identifier and the notice version seen. It changes nothing |
| `pipelex usage-stats status --format json` | The same as one JSON object on stdout, the form other tools read |
| `pipelex usage-stats disable` | Turns statistics off for every Pipelex tool on the machine and deletes every event still waiting to be sent |
| `pipelex usage-stats enable` | Turns the machine's choice back on, and names any other switch that still keeps statistics off |
| `pipelex usage-stats reset-id` | Deletes every event waiting to be sent and the installation identifier, draws a new one and prints it |

```json
{
  "tool": "pipelex",
  "enabled": false,
  "off_by": ["machine_choice"],
  "installation_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "notice_version": 1,
  "internal": false,
  "ci": false,
  "container": false,
  "state_dir": "/home/alice/.mthds/usage-stats"
}
```

`off_by` names the switches that say off, in the order of the table above: `do_not_track`, `tool_variable`, `machine_choice`, `legacy_mthds_choice`, `project_setting`, `packaged_default`, `integration_mode`, and `invalid_endpoint_override` for the test-only endpoint variable below.

## Where it is kept and where it goes

Every Pipelex tool on a machine shares one directory, `~/.mthds/usage-stats/` (`%USERPROFILE%\.mthds\usage-stats\` on Windows), created with owner-only permissions. It holds the installation identifier, the machine's choice, a marker per notice version shown, and each tool's queue of events waiting to be sent, under `spool/`. A file there is created or deleted whole, so two tools running at once never undo each other's choice. When Pipelex cannot look into that directory, statistics stay off rather than risk ignoring a choice stored there, and your command runs as usual.

Events go straight to PostHog's EU region, to a project that holds nothing but these statistics. PostHog discards the IP address after deriving the country from it, and keeps no finer location. No person profile is ever created. PostHog keeps the events for its retention period, and we delete the events of an installation on request, as our [Privacy Policy](https://go.pipelex.com/privacy-policy) explains: send us the identifier `pipelex usage-stats status` prints, after turning statistics off or running `pipelex usage-stats reset-id`.

How an event leaves depends on the process:

- **A CLI command** writes its events to its queue when it ends and starts a small detached sender process, then exits at once; the sender posts the queue within ten seconds. The sender is a single file that needs nothing but Python itself, so it delivers whichever way Pipelex was installed and never loads Pipelex. An event that cannot be sent, because you are offline for instance, stays queued for the next command's sender. In CI or in a container, where a detached process would be killed, the command posts its events itself within one second before exiting, followed within that second by what earlier commands left queued.
- **A Python program, or a long-running process** such as the API server, posts from a background thread within seconds of each event, and flushes what is left when Pipelex is torn down or the program exits, within a short time budget. Each time its events get through, what earlier processes left queued goes too, within the same budget.

A send never delays you by more than these budgets, and a failure to send never changes what your command or your run does.

## For developers

- **`PIPELEX_USAGE_STATS_DEBUG`**, set to anything but empty, `0` or `false`, prints each event to stderr as one JSON line, `{"usage_stats_debug": {...}}`, instead of sending it. The switches still decide, so nothing is printed while statistics are off.
- **`PIPELEX_USAGE_STATS_ENDPOINT`**, for tests, sends the events to a loopback `http` origin such as `http://127.0.0.1:8123` instead of PostHog. Any other value turns statistics off. An event queued while it is set is only ever sent to that origin, and an event queued without it never goes there.
- **`PIPELEX_USAGE_STATS_HOST`** names the tool that embeds Pipelex, from a closed list (`cocode`, `mthds-agent`, `other`), so its runs can be told apart.
- Pipelex's own continuous integration sets `DO_NOT_TRACK=1`, and its test suites turn statistics off and keep the shared state in a temporary directory.
