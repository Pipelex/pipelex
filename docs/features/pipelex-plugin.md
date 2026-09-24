---
title: "Pipelex Plugin"
description: "The Pipelex plugin for Claude Code and Codex: skills that build and run methods, a hook that checks every edit, and the Pipelex tools."
---

<!--
The install commands and the sentences around them are adapted from the onboarding source's
front-door assembly, last re-read against the rendered file at Pipelex/.github@81a3728
(onboarding/rendered/front-door.md): the blocks install/claude-code.md and install/codex.md, copied
verbatim. The Node.js sentence is this page's own: the blocks do not say it yet, and it goes once they
do. The skills, the hook and the tools summarize the plugin's own README, which stays their
reference.
-->

# Pipelex Plugin

The Pipelex plugin is how you build methods with your coding agent, Claude Code or Codex: it gives your agent the skills that write and run them, a hook that checks every edit, and the Pipelex tools. It works against the hosted Pipelex API, so you need an account at [app.pipelex.com](https://app.pipelex.com) and an API key from your console there. The plugin's hook and the Pipelex tools run on Node.js, so you need Node.js on your `PATH`.

Its source, its full documentation and its release notes are at [github.com/Pipelex/pipelex-plugins](https://github.com/Pipelex/pipelex-plugins).

## Install

=== "Claude Code"

    ```bash
    claude plugin marketplace add Pipelex/pipelex-plugins
    claude plugin install pipelex@pipelex-plugins
    ```

    Claude Code asks for an API key when you enable the plugin, and stores it in your OS keychain — create one in your console at [app.pipelex.com](https://app.pipelex.com). The skills, the hook that checks every edit and the Pipelex tools load with it; nothing else to install.

    Claude Code also loads what you have added to your Claude account, so if the Pipelex MCP is there, turn it off in Claude Code with `/mcp`: an agent with the plugin never takes both, since they register the same tool names.

=== "Codex"

    ```bash
    codex plugin marketplace add Pipelex/pipelex-plugins
    export PIPELEX_API_KEY=plx_sk_...     # create one in your console at app.pipelex.com
    ```

    Restart Codex, run `/plugins` to install `pipelex`, and trust the plugin hook on first run. Requires Codex 0.141 or later.

Then ask your agent for the method you want, as in step 3 of the [Quick Start](../get-started/quick-start.md#3-ask-your-agent-for-the-method-you-want).

## Skills

Your agent picks the skill your request calls for, and you can also name one yourself.

| Skill | What it does |
|-------|--------------|
| `/pipelex-design` | Designs a method contract-first and writes it as `.mthds` files |
| `/pipelex-edit` | Makes an edit that keeps a method's contract, and proves it with a validation before and after |
| `/pipelex-organize` | Regroups a method's files into a layout you can browse, without changing what the method does |
| `/pipelex-explain` | Explains a method in plain language — its contract, its flow and every pipe — and writes nothing |
| `/pipelex-inputs` | Prepares a method's inputs from your files, from synthetic data or from a template |
| `/pipelex-synthetic-inputs` | Makes the test files a method needs when you have none |
| `/pipelex-run` | Runs a method on the hosted Pipelex API and follows the run to its status, its results and its files |
| `/pipelex-catalog` | Saves a method to your Pipelex account, lists what is saved there, and pulls a saved method back to disk |
| `/pipelex-lab` | Frames a use case into candidate methods, then runs, scores and fixes them round after round within a budget you agree |
| `/pipelex-integrate` | Wires a method into your TypeScript or Python code, with generated types and one typed call through an SDK |
| `/pipelex-scaffold` | Starts a new project around a method, such as a web app from the method-app template |

[Each skill in detail, and what it needs](https://github.com/Pipelex/pipelex-plugins/blob/main/docs/skills.md).

## The hook

After every edit to a `.mthds` file, the hook lints it and formats it in place on your machine, offline, then validates the whole method on the hosted Pipelex API when a key is set. A failed check returns to your agent with the line to fix. Without a key, the hook still lints and formats every edit and skips only the validation. [How the hook works](https://github.com/Pipelex/pipelex-plugins/blob/main/docs/hooks.md).

## The Pipelex tools

The tools the skills call to validate a method, prepare its inputs, run it, generate typed code and reach your saved methods start with your agent, on Node.js. [The tools, one by one](https://github.com/Pipelex/pipelex-plugins/blob/main/docs/skills.md#the-pipelex-tools).

## Related Documentation

- [Quick Start](../get-started/quick-start.md) — sign up, install the plugin and run your first method, then run it from your chatbot, as a webapp or via API
- [MTHDS Language](mthds-language.md) — the language the plugin's skills write
- [Run It Yourself](../get-started/run-it-yourself.md) — the Pipelex runtime on your own machine
