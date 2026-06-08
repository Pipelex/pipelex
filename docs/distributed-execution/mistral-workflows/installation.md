---
title: "Installation & Preview Status"
description: "Install the preview pipelex-mistralai-workflows package (Python 3.12+) and understand what 'preview' means for the Mistral Workflows backend."
---

# Installation & Preview Status

!!! warning "Preview"
    `pipelex-mistralai-workflows` is not yet a stable release. Its public surface may change between versions, and there is no separate published documentation site for it yet — this guide is the reference for now.

## Prerequisites

Before installing, make sure you have:

- **Python 3.12 or later.** Mistral Workflows requires 3.12+. Pipelex core supports 3.10+, but this orchestration path needs 3.12 because of the Workflows SDK.
- **A Mistral Workflows setup** — a workspace and API key from the [Mistral Console](https://console.mistral.ai/), and the `mistralai-workflows` SDK. Follow Mistral's own Workflows installation and first-workflow guides for the worker, console, and `.env` setup; this guide does not duplicate them.
- **A Pipelex method to run** — a `.mthds` bundle available on your `PIPELEXPATH`, or passed at call time as a library crate (see [Execution Modes](execution-modes.md)).

## Install

```bash
pip install pipelex-mistralai-workflows
```

This pulls in `pipelex` automatically. If your project uses `uv`, the equivalent is `uv add pipelex-mistralai-workflows`.

The package depends on the Mistral Workflows SDK (`mistralai-workflows`). If you are scaffolding a new Workflows project, install the SDK as Mistral documents it (`uv add mistralai-workflows`) and add `pipelex-mistralai-workflows` alongside it.

## Verify

Confirm both pieces import in your environment:

```bash
python -c "import mistralai.workflows; import pipelex_mistralai_workflows; print('ready')"
```

<!-- ILLUSTRATIVE: the importable top-level module name `pipelex_mistralai_workflows` matches the package's Python distribution name; confirm the exact public import path against the released package. -->

!!! note "Preview verify"
    The exact public import surface of `pipelex_mistralai_workflows` is still settling. If the import above fails after a successful install, check the package's release notes for the current module layout.

## What "preview" means

- The API may change between releases without a deprecation window.
- Some examples in this guide are marked illustrative — confirm them against the installed package before relying on them in production.
- Watch the changelog and release notes for breaking changes.

## Next

Continue to **[Your First Pipelex Workflow](your-first-pipelex-workflow.md)**.
