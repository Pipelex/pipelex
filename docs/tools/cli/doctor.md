---
description: "Check the health of your Pipelex configuration, see what your setup needs for where its runs execute, and fix what can be fixed."
---

# Doctor Command

`pipelex doctor` checks your Pipelex configuration and says what to fix. It reads your configuration files and your environment, and it changes nothing unless you pass `--fix`.

```bash
pipelex doctor
pipelex doctor --fix
```

## What It Checks

The doctor checks the configuration a command run in the current directory would use: the project's `.pipelex/` when the project around the working directory has one, else the home configuration directory (`~/.pipelex/`, or the directory `PIPELEX_HOME` names; see [Configuration](../../configuration/index.md#the-home-configuration-directory-pipelex_home)). The report opens with an overall status, then gives one row per check:

- **Configuration Location** - Which configuration directory is used, the project's or the global one.
- **Configuration Files** - Whether every configuration file the kit ships is present, and whether `pipelex.toml` is valid.
- **Configuration Migrations** - What [`pipelex migrate`](migrate.md) would change: the files a migration would bring up to the current schema, the files that need a look from you, and what a former release left for the Pipelex Gateway, which the migration cleans up first. This row covers the home configuration directory and the project's `.pipelex/` together, as `pipelex migrate` does.
- **Telemetry Configuration** - Whether `telemetry.toml` is present and valid.
- **Plugins**, **Secrets Provider** and **Log Sink** - Whether the plugins, the secrets provider and the log sink your configuration names can be set up. These rows appear once the configuration loads.
- **Pipelex API Key** - Whether hosted runs have a key to send. This row appears only when your runs execute on the hosted Pipelex API, as described below.
- **Backend Credentials** - Whether the provider keys of the enabled inference backends are set. When some are missing, the row says how to set them, how to disable a backend you do not need, and that a run on the hosted Pipelex API needs none of them.
- **Models** - Whether the inference backends and the models they declare load.
- **Model Deck** - Whether the model deck and `backends/internal.toml` match the installed pipelex version; [`pipelex update`](update.md) refreshes them.

## Where Your Runs Execute

What a setup needs depends on where its runs execute, so the doctor reads the effective `[run] execution` setting (see [Run Configuration](../../configuration/config-practical/run-config.md)), and takes `"local"` when the configuration does not load.

- **On this machine** (`"local"`), every row counts toward the overall status.
- **On the hosted Pipelex API** (`"hosted"`), a run boots nothing on this machine and uses no provider key. The **Pipelex API Key** row appears and counts: it is healthy when a Pipelex API key is set, in `PIPELEX_API_KEY` or saved in the home `.env` by [`pipelex login`](login.md), and starts with `plx_sk_`; otherwise it names `pipelex login`. The row looks at the key only, without calling the hosted API, and never prints it. The **Backend Credentials** and **Models** rows are then shown as information, needed only for runs you start with `--local`, and they count neither toward the overall status nor toward the exit code.

## Fix Mode

```bash
pipelex doctor --fix
```

With `--fix` (`-f`), the doctor offers each fix it can make, one question at a time, with yes as the default answer:

- **Missing configuration files** are installed by running `pipelex init config` without its confirmation and without asking where runs execute. It never moves runs off this machine: it keeps the `[run] execution` the target `pipelex.toml` already sets, and a `pipelex.toml` that sets none stays on this machine. Only a brand-new home, with no `pipelex.toml` yet, takes the hosted Pipelex API, and it then prints `pipelex login` rather than opening a browser.
- **Configuration migrations** run the write pass of `pipelex migrate`: the cleanup of what a former release left, then the migration of the files that can be brought up to date, each file backed up beside itself first.
- **A missing telemetry configuration** is set up through `pipelex init telemetry`.
- **An outdated model deck or `backends/internal.toml`** is refreshed through `pipelex update`.
- **A backend file in an outdated format** is replaced by the kit's template, for a backend the kit ships, when your runs execute on this machine.

What no command can fix is listed under **Manual Fixes Required**: a missing or malformed Pipelex API key (run `pipelex login`, or `pipelex login --paste` on a machine without a browser), a `pipelex.toml` or `telemetry.toml` that does not validate, and, when your runs execute on this machine, the provider keys to set, shown as `.env` lines and as shell commands. A variable set in a `.env` file Pipelex loads wins over one exported in your shell (see [Running on the Hosted API](run.md#running-on-the-hosted-api)).

The report is measured before the fixes run, so run `pipelex doctor` again to see where things stand.

## Exit Codes

- `0`: every row that counts is healthy.
- `1`: something needs fixing. This is also the exit code of a `--fix` run that found something to fix, whatever it fixed.

## Machine-Readable Output

`pipelex-agent doctor` runs the same checks and answers in Markdown or JSON: `execution` at the top level, the Pipelex API key under `checks.pipelex_api_key` with a `finding` of `set`, `not_a_pipelex_key` or `missing`, and `informational: true` on the provider credentials and models rows of a hosted setup. See [Agent CLI](agent-cli.md).

## Related Documentation

- [Init](init.md): the first-run setup, and what `pipelex doctor --fix` runs to install missing files
- [Migrate](migrate.md): bring configuration files up to the current schema
- [Update](update.md): refresh the model deck and `backends/internal.toml`
- [Login](login.md): get the Pipelex API key a hosted setup needs
- [Init CLI Flows](../../under-the-hood/init-cli-flows.md): how the setup and the health check work inside
