---
title: "Open-source AI workflows"
---

![Pipelex Banner](https://d2cinlfp2qnig1.cloudfront.net/banners/pipelex_banner_docs_v2.png)

# Build reliable AI workflows in minutes

## Install

```bash
pip install pipelex
pipelex init config
```

## Set your API key

```bash
# Linux/MacOS
export PIPELEX_INFERENCE_API_KEY=###

# Windows PowerShell
$env:PIPELEX_INFERENCE_API_KEY="###"

# Windows CMD
set PIPELEX_INFERENCE_API_KEY=###
```

**Where to get an API key:** The `PIPELEX_INFERENCE_API_KEY` key provides access to all the AI models, you can get a free key from [our Discord](https://go.pipelex.com/discord). You can also use another AI routing service like [BlackBox AI](https://docs.blackbox.ai/), or bring your own API keys (OpenAI, Anthropic, Google, etc.), or run local AI (no key needed). See [Configure AI Providers](pages/setup/configure-ai-providers.md) for details. If you are using non-standard APIs, that's OK too, don't hesitate to join our [Discord](https://go.pipelex.com/discord) for guidance.

## Generate your first pipe

```bash
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch"
```

**Other useful use-cases for business:**

```bash
pipelex build pipe "Given an expense report, apply company rules"
pipelex build pipe "Take a CV in a PDF file, a Job offer text, and analyze if they match"
```

Each of these commands generates a complete production-ready script in our Pipelex language, saved as `.plx` file including domain definition, concepts, and the multiple _pipe_ steps to take to achieve the goal.

## Run your pipeline

**CLI:**

```bash
# Run a pipe by code
pipelex run <pipe_code>

# Run with inputs (JSON file containing input_memory dict)
pipelex run <pipe_code> --inputs input.json

# Run a bundle's main_pipe (auto-detected from .plx extension)
pipelex run bundle.plx --inputs input.json

# Customize output location
pipelex run <pipe_code> --output results/output.json
```

The `--inputs` file should be a JSON dictionary where keys are input variable names and values are the input data. For native types like Text, use strings directly. For structured types, provide objects matching the expected structure.

**Python:**

```python
import asyncio
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipelex import Pipelex

async def run_pipeline():
    pipe_output = await execute_pipeline(pipe_code="your_pipe_code")
    print(pipe_output.main_stuff_as_str)

Pipelex.make()
asyncio.run(run_pipeline())
```

## Easily iterate on your pipe

Now, thanks to our Pipelex language, and its high level of abstraction, you can directly edit the pipeline. It's pretty easy even for non-technical users. Better yet, you can get assisted in making changes with the help of your favorite AI coding assistant. To that end, we have prepared comprehensive guides for the most popular AI coding assistants and you can install them with one call:

```bash
pipelex kit rules
```

This installs Pipelex rules for Cursor, Claude Code, OpenAI Codex, GitHub Copilot, Windsurf, and Blackbox AI.

Now refine your pipeline with natural language:

- "Include confidence scores between 0 and 100 in the match analysis"
- "Write a recap email at the end"

---

## What is Pipelex?

Pipelex is an open-source Python framework for building **repeatable AI workflows**. Instead of cramming everything into one complex prompt, you break tasks into focused steps, each pipe handling one clear transformation.

Each pipe processes information using **Concepts** (typing with meaning) to ensure your pipelines make sense. The Pipelex language (`.plx` files) is simple and human-readable, even for non-technical users.

Each step can be structured and validated, so you benefit from the reliability of software, and the intelligence of AI.

---

## Next Steps

**Learn More:**

- [Full Tutorial](pages/quick-start/index.md) - Complete guide with examples
- [Cookbook Examples](pages/cookbook-examples/index.md) - Real-world patterns
- [Build Reliable AI Workflows](pages/build-reliable-ai-workflows-with-pipelex/kick-off-a-knowledge-pipeline-project.md) - Deep dive

**Understand the Philosophy:**

- [:material-book-open: Read the Manifesto](manifesto.md){ .md-button .equal-width }
- [:material-lightbulb: Explore the Paradigm](pages/pipelex-paradigm-for-repeatable-ai-workflows/index.md){ .md-button .equal-width }

**Configure:**

- [Configure AI Providers](pages/setup/configure-ai-providers.md) - API keys, local AI, model providers
- [Project Organization](pages/setup/project-organization.md) - Structure your Pipelex projects

[![Cookbook](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/)


