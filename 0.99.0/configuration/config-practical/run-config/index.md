# Run Configuration

The `[run]` section says where `pipelex run` and `pipelex-agent run` execute a method when the command does not say.

## Configuration Options

```python
class RunExecution(StrEnum):
    LOCAL = "local"
    HOSTED = "hosted"


class RunConfig(ConfigModel):
    execution: RunExecution
```

### Fields

- `execution`: where a run executes when the command passes neither `--hosted` nor `--local` (nor `--runner` on the agent CLI).
    - `"local"`, the package default that applies when no configuration file sets `execution`, runs on this machine, with the inference backends configured in `.pipelex/inference/` and your own provider keys.
    - `"hosted"` runs on the hosted Pipelex API, with the Pipelex API key in `PIPELEX_API_KEY`, at the origin in `PIPELEX_BASE_URL` (`https://api.pipelex.com` when unset). Nothing is booted locally, so no provider key or inference configuration is needed on this machine.

A flag on the command always wins: with `execution = "hosted"`, `pipelex run … --local` still runs on this machine, and with `"local"`, `--hosted` sends that one run to the hosted API.

[`pipelex init`](../../tools/cli/init.md#where-your-runs-execute) writes this setting from your answer to "Where should your runs execute?", whose default answer is `"hosted"`, and `pipelex-agent init` from the `execution` of its `--config`, `"local"` when the config names none.

## Example Configuration

```toml
[run]
execution = "hosted"
```

Put it in your project's `.pipelex/pipelex.toml` to make hosted runs the default for one project, or in `~/.pipelex/pipelex.toml` for every project on the machine; the project's file wins over the global one.

## The Key and the Origin

A hosted run reads its key and its origin from the environment, never from this file:

- `PIPELEX_API_KEY` holds the Pipelex API key (`plx_sk_…`). [`pipelex login`](../../tools/cli/login.md) gets one through your browser and saves it in `~/.pipelex/.env`, which Pipelex loads at startup.
- `PIPELEX_BASE_URL` overrides the origin, for a staging plane or a self-hosted Pipelex API server. `--base-url` on the command overrides it in turn. Either must be `scheme://host[:port]`, with no path such as `/v1`.

Pipelex loads `~/.pipelex/.env`, then the `.env` of the working directory, and each file replaces the variables it sets. So for either variable, the working directory's `.env` wins over `~/.pipelex/.env`, which wins over a value exported in your shell: an exported value is read only when neither file sets the variable.

## Related Documentation

- [Running on the Hosted API](../../tools/cli/run.md#running-on-the-hosted-api) — What a hosted run sends, uploads, saves and refuses
- [Running on the Hosted API from Python](../../building-methods/pipes/running-on-the-hosted-api.md) — The pipelex-sdk client, the hosted half of the Python API
- [Agent CLI](../../tools/cli/agent-cli.md) — `pipelex-agent run --runner local|hosted`
