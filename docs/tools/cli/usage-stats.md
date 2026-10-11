---
title: "CLI Usage Stats"
description: "See and change Pipelex's anonymous usage statistics for every Pipelex tool on the machine with `pipelex usage-stats`."
---

# Usage Stats

`pipelex usage-stats` shows and changes Pipelex's anonymous usage statistics for every Pipelex tool on the machine: pipelex and `pipelex-agent`, `plxt`, the VS Code extension and the `mthds` CLI, which all read the same state in `~/.mthds/usage-stats/`. [Usage Statistics](../../setup/usage-statistics.md) says what is collected and every other way to turn the statistics off.

These commands never send anything and never print the notice. They exit with `0` unless they could not do what they say, such as a state directory that cannot be written, and then print why on stderr and exit with `1`.

## status

```bash
pipelex usage-stats status
pipelex usage-stats status --format json
```

Prints whether statistics are on, every switch that turns them off, the installation identifier, the notice version seen on the machine, whether it is marked as one of the Pipelex team's, whether the process is in CI or in a container, and the shared state directory. It changes nothing: it creates no identifier and turns no former `mthds` opt-out into the machine's choice.

With `--format json`, it prints one JSON object on stdout, the form other tools read:

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

`off_by` lists the switches that say off, in the order [Turning them off](../../setup/usage-statistics.md#turning-them-off) gives, and is empty when statistics are on. `installation_id` is `null` until a tool has drawn one.

## disable

```bash
pipelex usage-stats disable
```

Turns statistics off on this machine for every Pipelex tool, and deletes every event any tool still had waiting to be sent.

## enable

```bash
pipelex usage-stats enable
```

Turns the machine's choice back on, including after a former `mthds telemetry disable`, and names every other switch that still keeps statistics off, such as `DO_NOT_TRACK` in your environment or a project's `[usage_stats] enabled = false`.

## reset-id

```bash
pipelex usage-stats reset-id
```

Deletes every event waiting to be sent and the installation identifier, draws a new one and prints it on stdout. Events made under the old identifier are never sent afterwards.
