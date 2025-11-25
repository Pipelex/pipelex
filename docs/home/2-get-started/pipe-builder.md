---
title: "Generate Workflows with Pipe Builder"
---

![Pipelex Banner](https://d2cinlfp2qnig1.cloudfront.net/banners/pipelex_banner_docs_v2.png)

## Install

```bash
pip install pipelex
```
```bash
pipelex init
```

To use AI models, you need API key(s):

- The `PIPELEX_INFERENCE_API_KEY` key provides access to all the AI models. To get your key, join our [Discord community](https://go.pipelex.com/discord), then request your **free API key** (no credit card required, limited time offer) in the [🔑・free-api-key](https://discord.com/channels/1369447918955921449/1418228010431025233) channel.
- You can also use other AI routing services like [BlackBox AI](https://docs.blackbox.ai/), or you can bring your own API keys (OpenAI, Anthropic, Google, Mistral, etc.), or run local AI (no key needed).
See [Configure AI Providers](../../home/5-setup/configure-ai-providers.md) for details. If you are using non-standard APIs, that's OK too, don't hesitate to join our [Discord](https://go.pipelex.com/discord) for guidance, Pipelex provides dependency injections for the API portals, [See here for more information](../10-advanced-customizations/plugin-injection.md)

# Generate workflows with Pipe Builder

The fastest way to create production-ready AI workflows is with the Pipe Builder. Just describe what you want, and Pipelex generates complete, validated pipelines.

```bash
pipelex build pipe "Take a CV and Job offer in PDF, analyze if they match and generate 5 questions for the interview"
```

The pipe builder generates three files in a numbered directory (e.g., `results/pipeline_01/`):

1. **`bundle.plx`** - Complete production-ready script in our Pipelex language with domain definition, concepts, and pipe steps
2. **`inputs.json`** - Template describing the **mandatory** inputs for running the pipe
3. **`run_{pipe_code}.py`** - Ready-to-run Python script that you can customize and execute

!!! tip "Pipe Builder Requirements"
    For now, the pipe builder requires access to **Claude 4.5 Sonnet**, either through Pipelex Inference, or using your own key through Anthropic, Amazon Bedrock or BlackboxAI. Don't hesitate to join our [Discord](https://go.pipelex.com/discord) to get a key, otherwise, you can also create the workflows yourself, following our [documentation guide](./write-workflows-manually.md).

## Run your pipeline

**Option 1: CLI**

```bash
pipelex run results/cv_match.plx --inputs inputs.json
```

The `--inputs` file should be a JSON dictionary where keys are input variable names and values are the input data. Learn more on how to provide the inputs of a pipe: [Providing Inputs to Pipelines](../../home/6-build-reliable-ai-workflows/pipes/provide-inputs.md)

**Option 2: Python**

This requires having the `.plx` file or your pipe inside the directory where the Python file is located.

```python
import json
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipelex import Pipelex

# Initialize Pipelex
Pipelex.make()

# Load the inputs from the JSON file
with open("inputs.json", "r", encoding="utf-8") as json_file:
    inputs = json.load(json_file)

# Execute the pipeline
pipe_output = await execute_pipeline(
    pipe_code="analyze_cv_and_prepare_interview",
    inputs=inputs
)

print(pipe_output.main_stuff)

```

## Easily iterate on your pipe

Now, thanks to our Pipelex language, you can easily edit the pipeline, even if you're not a coder. Better yet, you can get assisted in making changes with the help of your favorite AI coding assistant. To that end, we have prepared comprehensive rules meant for the most popular AI coding assistants. You can install those rules with one call:

```bash
pipelex kit rules
```

This installs Pipelex rules for `Cursor`, `Claude Code`, `OpenAI Codex`, `GitHub Copilot`, `Windsurf`, and `Blackbox AI`.

Now refine your pipeline with natural language directly in your AI assistant's chatbot:

- "Include confidence scores between 0 and 100 in the match analysis"
- "Write a recap email at the end"
- "Split the first pipe into 2 more detailed pipe"

## IDE Support

We **highly** recommend installing our own extension for PLX files into your IDE of choice. You can find it in the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex) and download it directly using [this link](https://open-vsx.org/api/Pipelex/pipelex/0.2.1/file/Pipelex.pipelex-0.2.1.vsix). It's coming soon to the VS Code marketplace too and if you are using Cursor, Windsurf or another VS Code fork, you can search for it directly in your extensions tab.

## Examples

[Cookbook Examples](../../home/4-cookbook-examples/index.md) - Real-world patterns and use cases

---

## Next Steps

Now that you know how to generate workflows with the Pipe Builder, explore these resources:

**Learn how to Write Workflows yourself**

- [:material-pencil: Write Workflows Manually](./write-workflows-manually.md){ .md-button .md-button--primary }
- [:material-book-open-variant: Build Reliable AI Workflows](../6-build-reliable-ai-workflows/kick-off-a-pipelex-workflow-project.md){ .md-button .md-button--primary }

**Explore Examples:**

- [Cookbook Examples](../../home/4-cookbook-examples/index.md) - Real-world patterns and use cases

**Configure Your Setup:**

- [Configure AI Providers](../../home/5-setup/configure-ai-providers.md) - API keys, local AI, model providers
- [Project Organization](../../home/5-setup/project-organization.md) - Structure your Pipelex projects
