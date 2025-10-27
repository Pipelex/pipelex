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

To use AI models, you need API key(s):
- The `PIPELEX_INFERENCE_API_KEY` key provides access to all the AI models. To get your key, join our Discord community: [https://go.pipelex.com/discord](https://go.pipelex.com/discord), then request your **free API key** (no credit card required, limited time offer) in the [🔑・free-api-key](https://discord.com/channels/1369447918955921449/1418228010431025233) channel.
- You can also use other AI routing services like [BlackBox AI](https://docs.blackbox.ai/), or you can bring your own API keys (OpenAI, Anthropic, Google, Mistral, etc.), or run local AI (no key needed).
See [Configure AI Providers](pages/setup/configure-ai-providers.md) for details. If you are using non-standard APIs, that's OK too, don't hesitate to join our [Discord](https://go.pipelex.com/discord) for guidance.

## Generate your first Pipelex workflow

```bash
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch"
pipelex build pipe "Take a theme, write a joke about it, then roast the joke" --output results/self_roaster.plx
```

**Other useful use-cases for business:**

```bash
pipelex build pipe "Given an expense report, apply company rules" --output results/expense.plx
pipelex build pipe "Take a CV and Job offer in PDF, analyze if they match and generate 5 questions for the interview" --output results/cv_match.plx
```

Each of these commands generates a complete production-ready script in our Pipelex language, saved as `.plx` file including domain definition, concepts, and the multiple _pipe_ steps to take to achieve the goal.

!!! tip "Pipe Builder Requirements"
    For now, the pipe builder requires access to **Claude 4.5 Sonnet**, either through Pipelex Inference, or using your own key through Anthropic, Amazon Bedrock or BlackboxAI. Don't hesitate to join our [Discord](https://go.pipelex.com/discord) to get a key, otherwise, you can also create the workflows yourself, following our [documentation guide](pages/writing-workflows/index.md).


## Run your pipeline

**CLI:**

```bash
# Run a pipe by code
pipelex run results/cv_match.plx --inputs inputs.json
pipelex run results/self_roaster.plx --inputs '{"theme": "the prisoner dilemma"}'
```

The `--inputs` file should be a JSON dictionary where keys are input variable names and values are the input data. For native concepts like Text, you can use strings directly. For structured types, provide objects matching the expected structure.

Learn more: [Executing Pipelines with Inputs](pages/build-reliable-ai-workflows-with-pipelex/executing-pipelines-with-inputs.md)

**Python:**

```python
import asyncio
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipelex import Pipelex
import json

async def run_pipeline():
    with open("inputs.json", "r", encoding="utf-8") as json_file:
        inputs = json.load(json_file)
    pipe_output = await execute_pipeline(pipe_code="analyze_cv_and_prepare_interview", inputs=inputs)
    print(pipe_output.main_stuff)

Pipelex.make()
asyncio.run(run_pipeline())
```

## Easily iterate on your pipe

Now, thanks to our Pipelex language, you can easily edit the pipeline, even if you're not a coder. Better yet, you can get assisted in making changes with the help of your favorite AI coding assistant. To that end, we have prepared comprehensive rules meant for the most popular AI coding assistants. You can install those rules with one call:

```bash
pipelex kit rules
```

This installs Pipelex rules for Cursor, Claude Code, OpenAI Codex, GitHub Copilot, Windsurf, and Blackbox AI.

Now refine your pipeline with natural language directly in your AI assistant's chatbot:

- "Include confidence scores between 0 and 100 in the match analysis"
- "Write a recap email at the end"

## IDE Support

By the way, we **highly** recommend installing our own extension for PLX files into your IDE of choice. You can find it in the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex) and download it directly using [this link](https://open-vsx.org/api/Pipelex/pipelex/0.2.1/file/Pipelex.pipelex-0.2.1.vsix). It's coming soon to the VS Code marketplace too and if you are using Cursor, Windsurf or another VS Code fork, you can search for it directly in your extensions tab.

## Examples

Visit the 
[![GitHub](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/): you can clone it, fork it, play with it 


---

## What is Pipelex?

Pipelex is an open-source language that enables agents to build and run **repeatable AI workflows**. Instead of cramming everything into one complex prompt, you break tasks into focused steps, each pipe handling one clear transformation.

Each pipe processes information using **Concepts** (typing with meaning) to ensure your pipelines make sense. The Pipelex language (`.plx` files) is simple and human-readable, even for non-technical users.

Each step can be structured and validated, so you benefit from the reliability of software, and the intelligence of AI.

---

## Next Steps

**Learn More:**

- [Writing Workflows Tutorial](pages/writing-workflows/index.md) - Complete guide with examples
- [Cookbook Examples](pages/cookbook-examples/index.md) - Real-world patterns
- [Build Reliable AI Workflows](pages/build-reliable-ai-workflows-with-pipelex/kick-off-a-pipelex-workflow-project.md) - Deep dive

**Understand the Philosophy:**

- [:material-book-open: Read the Manifesto](manifesto.md){ .md-button .equal-width }
- [:material-lightbulb: Explore the Paradigm](pages/pipelex-paradigm-for-repeatable-ai-workflows/index.md){ .md-button .equal-width }

**Configure:**

- [Configure AI Providers](pages/setup/configure-ai-providers.md) - API keys, local AI, model providers
- [Project Organization](pages/setup/project-organization.md) - Structure your Pipelex projects

[![Cookbook](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/)

