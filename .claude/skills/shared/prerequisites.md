# CLI Prerequisites

Check `pipelex-agent` availability before running commands:

1. Try `pipelex-agent --version`
2. If not found, try `uv run pipelex-agent --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works for all subsequent commands.

There is also a `pipelex` CLI for human use — agents should not call it themselves, but can suggest it to the user when helpful:

- `pipelex doctor` — interactive config diagnostics (richer than `pipelex-agent doctor`)
- `pipelex show <pipe_or_concept>` — visual inspection of a pipe or concept
- `pipelex init config` — interactive first-time setup
