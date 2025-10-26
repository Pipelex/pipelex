---
title: "Open-source AI workflows"
---

![Pipelex Banner](https://d2cinlfp2qnig1.cloudfront.net/banners/pipelex_banner_docs_v2.png)

# Build reliable AI workflows in minutes

## Install

```bash
pip install pipelex
pipelex init
```

## Set your API key(s)

```bash
# Linux/MacOS
export PIPELEX_INFERENCE_API_KEY=###
# Windows PowerShell
$env:PIPELEX_INFERENCE_API_KEY="###"
# Windows CMD
set PIPELEX_INFERENCE_API_KEY=###

# Note: Pipelex automatically loads environment variables from `.env` files, that works too.
```

**Where to get an API key:**

- The `PIPELEX_INFERENCE_API_KEY` key provides access to all the AI models. To get your key, join our Discord community: [https://go.pipelex.com/discord](https://go.pipelex.com/discord), then request your **free API key** (no credit card required, limited time offer) in the [🔑・free-api-key](https://discord.com/channels/1369447918955921449/1418228010431025233) channel.
- You can also use other AI routing services like [BlackBox AI](https://docs.blackbox.ai/), or you can bring your own API keys (OpenAI, Anthropic, Google, Mistral,etc.), or run local AI (no key needed).
See [Configure AI Providers](pages/setup/configure-ai-providers.md) for details. If you are using non-standard APIs, that's OK too, don't hesitate to join our [Discord](https://go.pipelex.com/discord) for guidance.

## Generate your first pipe

```bash
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch"
```

**Other useful use-cases for business:**

```bash
pipelex build pipe "Given an expense report, apply company rules" --output results/expense.plx
pipelex build pipe "Take a resume PDF, a Job offer text, and analyze if they match" --output results/resume_match.plx
pipelex build pipe "Take a theme, write a joke about it, then roast the joke" --output results/self_roaster.plx
```

Each of these commands generates a complete production-ready script in our Pipelex language, saved as `.plx` file including domain definition, concepts, and the multiple _pipe_ steps to take to achieve the goal.

## Run your pipeline

**CLI:**

```bash
# Run a pipe by code
pipelex run results/resume_match.plx --inputs inputs.json
pipelex run results/self_roaster.plx --inputs '{"theme": "the prisoner dilemma"}'
```

The `--inputs` file should be a JSON dictionary where keys are input variable names and values are the input data. For native concepts like Text, you can use strings directly. For structured types, provide objects matching the expected structure.

Learn more: [Executing Pipelines with Inputs](pages/build-reliable-ai-workflows-with-pipelex/executing-pipelines-with-inputs.md)

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

Now, thanks to our Pipelex language, you can easily edit the pipeline, even if you're not a coder. Better yet, you can get assisted in making changes with the help of your favorite AI coding assistant. To that end, we have prepared comprehensive guides for the most popular AI coding assistants and you can install them with one call:

```bash
pipelex kit rules
```

This installs Pipelex rules for Cursor, Claude Code, OpenAI Codex, GitHub Copilot, Windsurf, and Blackbox AI.

Now refine your pipeline with natural language:

- "Include confidence scores between 0 and 100 in the match analysis"
- "Write a recap email at the end"

## IDE Support

By the way, we **highly** recommend installing our own extension for PLX files into your IDE of choice. You can find it in the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex). It's coming soon to the VS Code marketplace too and if you are using Cursor, Windsurf or another VS Code fork, you can search for it directly in your extensions tab.

## Examples

Visit the 
[![GitHub](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/): you can clone it, fork it, play with it 


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

