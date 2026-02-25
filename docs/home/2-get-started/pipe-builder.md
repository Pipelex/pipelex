---
title: "Generate Methods with Pipe Builder"
---

![Pipelex Banner](https://d2cinlfp2qnig1.cloudfront.net/banners/pipelex_banner_docs_v2.png)

## Install

```bash
pip install pipelex
```

```bash
pipelex init
```

During the second step of the initialization, we recommend, for a quick start, to use the Pipelex Gateway. Get your API key at [app.pipelex.com](https://app.pipelex.com/) with free credits (no credit card required, limited time offer). If you have questions, join our [Discord](https://go.pipelex.com/discord).

If you want to bring your own API keys, see [Configure AI Providers](../../home/5-setup/configure-ai-providers.md) for details.

# Generate methods with Pipe Builder

The fastest way to create production-ready AI methods is with the Pipe Builder. Just describe what you want, and Pipelex generates complete, validated pipelines.

```bash
pipelex build pipe "Take a CV and Job offer in PDF, analyze if they match and generate 5 questions for the interview"
```

The pipe builder generates three files in a numbered directory (e.g., `results/pipeline_01/`):

1. **`bundle.mthds`** - Complete production-ready script in our Pipelex language with domain definition, concepts, and pipe steps
2. **`inputs.json`** - Template describing the **mandatory** inputs for running the pipe
3. **`run_{pipe_code}.py`** - Ready-to-run Python script that you can customize and execute

!!! tip "Pipe Builder Requirements"
    For now, the pipe builder requires access to **Claude 4.5 Sonnet**, either through Pipelex Inference, or using your own key through Anthropic, Amazon Bedrock or BlackboxAI. Don't hesitate to join our [Discord](https://go.pipelex.com/discord) to get a key, otherwise, you can also create the methods yourself, following our [documentation guide](./write-methods-manually.md).

!!! info "Learn More"
    Want to understand how the Pipe Builder works under the hood? See [Pipe Builder Deep Dive](../9-tools/pipe-builder.md) for the full explanation of its multi-step generation process.

## Run your pipeline

**Option 1: CLI**

```bash
pipelex run results/cv_match.mthds --inputs inputs.json
```

The `--inputs` file should be a JSON dictionary where keys are input variable names and values are the input data. Learn more on how to provide the inputs of a pipe: [Providing Inputs to Pipelines](../../home/6-build-reliable-ai-workflows/pipes/provide-inputs.md)

**Option 2: Python**

This requires having the `.mthds` file or your pipe inside the directory where the Python file is located.

```python
import json
from pipelex.pipeline.runner import PipelexRunner
from pipelex.pipelex import Pipelex

# Initialize Pipelex
Pipelex.make()

# Load the inputs from the JSON file
with open("inputs.json", "r", encoding="utf-8") as json_file:
    inputs = json.load(json_file)

# Execute the pipeline
runner = PipelexRunner()
response = await runner.execute_pipeline(
    pipe_code="analyze_cv_and_prepare_interview",
    inputs=inputs
)
pipe_output = response.pipe_output

print(pipe_output.main_stuff)

```

## IDE Support

We **highly** recommend installing our own extension for MTHDS files into your IDE of choice. You can find it in the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex) and download it directly using [this link](https://open-vsx.org/api/Pipelex/pipelex/0.2.1/file/Pipelex.pipelex-0.2.1.vsix). It's coming soon to the VS Code marketplace too and if you are using Cursor, Windsurf or another VS Code fork, you can search for it directly in your extensions tab.

## Examples

[Cookbook Examples](../../home/4-cookbook-examples/index.md) - Real-world patterns and use cases

---

## Next Steps

Now that you know how to generate methods with the Pipe Builder, explore these resources:

**Learn how to Write Methods yourself**

- [:material-pencil: Write Methods Manually](./write-methods-manually.md){ .md-button .md-button--primary }
- [:material-book-open-variant: Build Reliable AI Methods](../6-build-reliable-ai-workflows/kick-off-a-methods-project.md){ .md-button .md-button--primary }

**Explore Examples:**

- [Cookbook Examples](../../home/4-cookbook-examples/index.md) - Real-world patterns and use cases

**Configure Your Setup:**

- [Configure AI Providers](../../home/5-setup/configure-ai-providers.md) - API keys, local AI, model providers
- [Project Organization](../../home/5-setup/project-organization.md) - Structure your Pipelex projects
