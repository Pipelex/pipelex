---
description: "Initialize Pipelex — create the .pipelex directory, choose where your runs execute (the hosted Pipelex API or this machine), set up backends, and configure telemetry destinations."
---

# Init Commands

Initialize Pipelex configuration files and choose where your methods run: on the hosted Pipelex API, with a Pipelex API key, or on this machine, with your own provider keys.

## Initialize Configuration

```bash
pipelex init [FOCUS]
pipelex init --local [FOCUS]
```

By default, `pipelex init` writes to the home configuration directory (`~/.pipelex/`, or `PIPELEX_HOME`; see [Configuration](../../configuration/index.md#the-home-configuration-directory-pipelex_home)). Use `--local` to create a project-level `.pipelex/` directory at the detected project root. Credentials always remain in the home configuration directory regardless of `--local`.

!!! note "Config updates not yet supported"
    The `pipelex init` command always performs a full reset of the configuration. Incremental config updates will be supported in a future release.

**Arguments:**

- `FOCUS` - What to initialize (optional):
    - `all` (default) - Initialize everything, asking where your runs execute
    - `config` - Only configuration files; on a first setup, where no `inference/backends.toml` exists yet, it also asks where your runs execute and sets that up
    - `credentials` - Prompt for missing credentials only
    - `inference` - Only the inference backends of runs on this machine; where runs execute is left as it is
    - `routing` - Only routing profile setup
    - `telemetry` - Only telemetry configuration

**Examples:**

```bash
# Initialize global config (recommended for first-time setup)
pipelex init

# Initialize project-local config
pipelex init --local

# Initialize only configuration files
pipelex init config

# Prompt only for missing credentials
pipelex init credentials

# Reconfigure inference backends
pipelex init inference

# Reconfigure telemetry settings
pipelex init telemetry
```

## Where Your Runs Execute

After you confirm, `pipelex init` asks one question:

```
Where should your runs execute?
  [1]  On the hosted Pipelex API, with a Pipelex API key    default
  [2]  On this machine, with your own provider keys
```

Enter takes the hosted Pipelex API. Your answer is written to `[run] execution` in the target `pipelex.toml`, the default every `pipelex run` and `pipelex-agent run` takes when the command passes neither `--hosted` nor `--local` (see [Run Configuration](../../configuration/config-practical/run-config.md)). A single run can always go the other way with one of those flags.

- **The hosted Pipelex API** writes `execution = "hosted"` and then gets you a key: it runs [`pipelex login`](login.md), which opens the Pipelex app in your browser and saves the key it returns to `~/.pipelex/.env`. When a Pipelex API key is already set, in `PIPELEX_API_KEY` or saved in that file, it is kept and nothing opens; run `pipelex login` to replace it. An empty `PIPELEX_API_KEY=` counts as no key, and a `.env` in the working directory that sets another value is named, since Pipelex loads it after the home one. No provider key is asked for, since a hosted run uses none, and the inference files are the kit's defaults: like every reset, a re-init copies the kit's backends, model deck and routing over customised ones, and on this path nothing reconfigures them afterwards. Run `pipelex init inference` to set up this machine's backends again for `--local` runs. If the login does not complete, or its key cannot be saved, the rest of the setup is kept, and `pipelex login` (or `pipelex login --paste`) gets the key later.
- **This machine** writes `execution = "local"` and runs the backend selection, routing and credential prompts described below.

`pipelex init inference` configures the backends of runs on this machine and never asks this question, so it does not change where your runs execute. To switch, run `pipelex init` again, or set `[run] execution` yourself.

## What Gets Initialized

This command creates or resets a Pipelex config directory with:

- **pipelex.toml** - Main configuration file for logging, reporting, where runs execute, etc.
- **inference/** - AI backend and routing configuration
    - `backends.toml` - Backend provider settings
    - `routing_profiles.toml` - Model routing rules
    - `backends/` - Individual backend configuration files, of which [`pipelex update`](update.md) keeps `internal.toml` current
    - `deck/` - AI model aliases and presets, which [`pipelex update`](update.md) keeps current
- **telemetry.toml** - Telemetry and observability settings
- **.gitignore** - Keeps Pipelex's own transient copies out of your `git status` — the timestamped `.bak` files [`pipelex migrate`](migrate.md) leaves beside each file it rewrites. Commit it so your teammates get the same. It is written only when the directory has no `.gitignore`; one already there is never modified.

!!! warning "Init writes a fresh file — it does not update one"
    Every `init` target replaces the file with the template, so whatever was in it is gone. If a configuration file has simply fallen behind the current schema, [`pipelex migrate`](migrate.md) is the command: it rewrites the file in place and keeps every setting — your PostHog key, your Langfuse credentials, your exporters. `pipelex doctor` tells you which of the two you have.

## Interactive Setup Flow

When you run `pipelex init`, Pipelex can guide you through:

1. **What a former release left** - On a machine set up by a release that ran models through the Pipelex Gateway, the cleanup that release's files need, offered first (see [below](#a-machine-a-former-release-set-up))
2. **Config reset** - Recreate the selected config files
3. **Where your runs execute** - The hosted Pipelex API (the default) or this machine
4. On the hosted Pipelex API: **sign-in** - [`pipelex login`](login.md) gets a Pipelex API key, unless one is already set. It runs last, once every file is written
5. On this machine:
    1. **Backend selection** - Choose which AI providers to enable. The prompt pre-selects OpenAI, whose one key serves every default language-model and image-generation tier of the shipped model deck
    2. **Routing configuration** - Set up how models are routed to backends
    3. **Credential prompts** - Fill in missing keys when relevant
6. **Telemetry setup** - Configure observability and analytics

## A Machine a Former Release Set Up

Releases up to v0.72 ran models through the Pipelex Gateway, and offered Pipelex Manifold as a private beta. Neither exists any more, and Pipelex refuses to start on the files those releases wrote: a `pipelex_gateway` backend left enabled, or a routing profile such as `all_pipelex_gateway` left active.

`pipelex init` looks for what such a release left, in the home configuration directory and in the project's `.pipelex/`, before it asks anything else. When it finds some, it shows what stops Pipelex from starting and which files it is in, and asks:

```
Clean it up now? [y/n] (y):
```

Yes runs the cleanup that [`pipelex migrate`](migrate.md#a-configuration-a-former-release-set-up) runs: the retired backends, routing profiles and files are removed, a copy of each file it changes or removes is kept beside it, and an active routing profile of that release's moves to `all_enabled_backends`. Then the setup goes on to the question of where your runs execute. No leaves the files as they are and goes on with the setup, which replaces the target directory's inference files but not the files beside them nor those of the other directory; `pipelex migrate` cleans them up whenever you are ready.

`pipelex doctor --fix`, which runs `pipelex init` with nobody there to answer, cleans up without asking.

`pipelex init config` on an existing setup resets `pipelex.toml` without asking the question again, so it keeps the `[run] execution` it found, and asks for no provider key when that is `"hosted"`.

`pipelex doctor --fix` installs missing configuration files with nobody there to answer, and never moves runs off this machine. On a first setup it keeps the `[run] execution` the target `pipelex.toml` already sets; a `pipelex.toml` that sets none, such as one written before the setting existed, runs on this machine, as the package default says, and stays there. Only a brand-new home, with no `pipelex.toml` yet, takes the hosted Pipelex API, writing `execution = "hosted"` and printing `pipelex login` instead of opening a browser.

**A project can override the global choice.** A project's `.pipelex/pipelex.toml` wins over the one in `~/.pipelex/`, and the one `pipelex init --local` copies sets `execution = "local"`. When you set up the home configuration from inside a project whose own file sets the other value, `pipelex init` warns you, naming that file: runs started in that project execute where it says, until you change it there or pass `--hosted` or `--local` on a run.

## Non-Interactive Init (`pipelex-agent init`)

For automated or agent-driven setups, use the `pipelex-agent` CLI:

```bash
pipelex-agent init [--config/-c JSON] [--global/-g]
```

It never opens a browser: a hosted setup reads its key from `PIPELEX_API_KEY`, which a person gets with `pipelex login`.

**Target directory:**

- **Default:** project-level `.pipelex/` at the detected project root (looks for `.git`, `pyproject.toml`, etc.). Errors out if no project root is found.
- **`--global`/`-g`:** forces the home configuration directory (`~/.pipelex/`, or `PIPELEX_HOME`).

**Config JSON schema:**

```json
{
  "execution": "local",
  "backends": ["openai", "anthropic"],
  "primary_backend": "openai"
}
```

All fields are optional:

| Field | Type | Description |
|-------|------|-------------|
| `execution` | `"hosted"` or `"local"` | Where runs execute by default, written to `[run] execution`. `"hosted"` configures no backend or routing, leaves the kit's inference files as written, and cannot be combined with `backends` or `primary_backend`. `"local"`, or no `execution` at all, configures the backends below. |
| `backends` | `list[str]` | Backend keys to enable (e.g. `openai`, `anthropic`, `openrouter`). Omit to keep the template's enabled backends and its routing profile, which sends each model to the first of them that serves it. |
| `primary_backend` | `str` | Required when 2+ backends are named. Named without `backends`, it routes the template's backends to it first. |

**Output:** `success`, `target_dir`, `config_files_copied` and `execution`. A local setup adds `backends_enabled` and `routing_profile`; a hosted one adds `api_key_set`, whether a Pipelex API key is set in `PIPELEX_API_KEY` or saved in `~/.pipelex/.env`, never the key itself. A `warnings` list is added when the project around the working directory sets another `[run] execution` in its own `.pipelex/pipelex.toml`, which wins over the one just written.

Telemetry is not configured via `--config`: init seeds a `telemetry.toml` from a template (a global init writes an active one; a project init drops a commented-out one).

**Examples:**

```bash
# Initialize with OpenAI backend (project-level)
pipelex-agent init --config '{"backends": ["openai"]}'

# Initialize globally with OpenAI, whose one key serves every default language-model and image-generation tier of the model deck
pipelex-agent init -g --config '{"backends": ["openai"]}'

# Run on the hosted Pipelex API by default, with the key in PIPELEX_API_KEY
pipelex-agent init -g --config '{"execution": "hosted"}'
```

## Related Configuration

- [Login](login.md)
- [Run Configuration](../../configuration/config-practical/run-config.md)
- [Configure AI Providers](../../get-started/configure-ai-providers.md)
- [Inference Backend Configuration](../../configuration/config-technical/inference-backend-config.md)
- [Telemetry Configuration](../../configuration/config-practical/telemetry-config.md)

