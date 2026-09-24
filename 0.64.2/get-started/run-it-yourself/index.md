# Run It Yourself

The Pipelex runtime is the Python package that reads a `.mthds` file and runs it. Install it and everything happens on your own machine, against the model providers you choose. If you would rather not run anything yourself, the [Quick Start](./quick-start.md) builds methods with your coding agent and runs them on the hosted API.

## Install

```bash
uv tool install pipelex
pipelex init
pipelex doctor
```

`pipelex init` writes your `~/.pipelex` configuration and offers to install the editor extension; `pipelex doctor` reports what is configured and what is missing.

Some providers and features need an extra:

- `anthropic`: Anthropic/Claude support for text generation
- `google`: Google models (Vertex) support for text generation
- `google-genai`: Google Gemini API support for text and image generation
- `mistralai`: Mistral AI support for text generation and OCR
- `bedrock`: Amazon Bedrock support for text generation
- `fal`: Image generation through fal
- `linkup`: Web search with Linkup
- `docling`: OCR with Docling

Name the ones you need when you install, or take them all:

```bash
uv tool install "pipelex[anthropic,google,google-genai,mistralai,bedrock,fal,linkup,docling]"
```

## Configure AI access

- **Bring Your Own Keys** — Use existing API keys from OpenAI, Anthropic, Google, Mistral, etc. See [Configure AI Providers](./configure-ai-providers.md).
- **Local AI** — Ollama, vLLM, LM Studio, or llama.cpp — no API keys required. See [Configure AI Providers](./configure-ai-providers.md).

## Run a method

Save this method as `summarize.mthds`:

```toml
domain    = "articles"
main_pipe = "summarize_article"

[pipe.summarize_article]
type        = "PipeLLM"
description = "Summarize an article for a given audience"
inputs      = { article = "Text", audience = "Text" }
output      = "Text"
prompt      = "Summarize $article in three bullet points for $audience."
```

Save its inputs as `inputs.json`:

```json
{
  "article": "Paste the text of an article here.",
  "audience": "busy executives"
}
```

The method names no model, so it runs on the deck's `default-general` alias, which `pipelex init` points at an OpenAI model. With a provider other than OpenAI or Azure OpenAI, point that alias at one of your provider's models first, by adding it to `~/.pipelex/inference/deck/x_custom_llm_deck.toml` — the models each provider serves are listed under `~/.pipelex/inference/backends/`:

```toml
[llm.aliases]
default-general = "claude-5-sonnet"     # an Anthropic model, for example
```

Then run it:

```bash
pipelex run bundle summarize.mthds --inputs inputs.json
```

The result is written under `results/`. From here, [The MTHDS Language Tutorial](./mthds-language-tutorial.md) builds a method step by step, and [CV batch screening](../cookbook/cv-batch-screening.md) runs a method with several steps, typed concepts and a batch, from the CLI and from Python.

## Editor extension

`.mthds` syntax highlighting and flowchart visualization: the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=pipelex.pipelex), or the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex) for Cursor, Windsurf and other VS Code forks. `pipelex init` offers to install it when it detects your IDE.
