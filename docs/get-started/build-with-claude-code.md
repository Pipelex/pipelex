---
title: "Build with Claude Code"
description: "Build and run Pipelex methods using Claude Code and the MTHDS skills plugin."
---

# Build with Claude Code

Install the `mthds` CLI:

```bash
npm install -g mthds
```

Launch Claude Code and tell it to install the MTHDS plugin:

```
/plugin marketplace add mthds-ai/mthds-plugins
```

```
/plugin install mthds@mthds-ai-mthds-plugins
```

then exit Claude Code and reopen it:

```
/exit
```

Reopen Claude Code, and build your first method:

```
/mthds-build A method to analyze a Job offer to build a scorecard, then batch process CVs to score them
```

Run it:

```
/mthds-run
```

That's it — Claude writes the `.mthds` file, creates inputs, and runs the method for you. See the [Claude Code Skills Plugin](../features/claude-code-skills-plugin.md) documentation for the full list of commands (`/mthds-edit`, `/mthds-check`, `/mthds-fix`, `/mthds-explain`, and more).

See [Configure AI Providers](./configure-ai-providers.md) for other options: bring your own keys, local AI, etc.

![Claude Code + Pipelex + MTHDS](https://raw.githubusercontent.com/Pipelex/pipelex/main/.github/assets/Claude-Code-Pipelex-MTHDS-Cursor.png)
