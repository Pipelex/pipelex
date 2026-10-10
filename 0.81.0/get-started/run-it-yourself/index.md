# Run It Yourself

The Pipelex runtime is the Python package that reads a `.mthds` file and runs it. Install it and run methods from your terminal, either on the hosted Pipelex API, with no provider account of your own, or on your own machine, against the model providers you choose. If you would rather not install anything, the [Quick Start](./quick-start.md) builds methods with your coding agent and runs them on the hosted API.

## Install

```bash
uv tool install "pipelex[cli]"
pipelex init
pipelex doctor
```

`pipelex init` writes your `~/.pipelex` configuration, offers to install the editor extension, and asks where your runs execute:

- **On the hosted Pipelex API**, the default that Enter takes: no provider account is needed. `pipelex init` signs you in through your browser and saves a Pipelex API key to `~/.pipelex/.env`. [`pipelex login`](../tools/cli/login.md) does that again on its own, and `pipelex login --paste` takes a key on a machine without a browser.
- **On this machine, with your own provider keys**: you choose your AI providers and enter their keys, or point Pipelex at a local model.

`pipelex doctor` reports what is configured and what is missing. The `cli` extra installs Rich, which the `pipelex` and `pipelex-agent` commands render their output through.

Some providers and features need an extra:

- `cli`: Rich, for the `pipelex` and `pipelex-agent` commands, the `console` log sink and the `rich` pretty-print mode. Install it wherever Pipelex runs in a terminal; a server leaves it out and selects the `json` log sink with the `poor` or `silent` pretty-print mode (see [Rich Imports](../contribute/rich-imports.md))
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
uv tool install "pipelex[cli,anthropic,google,google-genai,mistralai,bedrock,fal,linkup,docling]"
```

## Configure AI access

- **The hosted API** — Choose it in `pipelex init`, which writes `[run] execution = "hosted"` and signs you in, to run on the hosted Pipelex API with no provider key on this machine. On a machine set up for local runs, `pipelex login` and `--hosted` send one run there. See [Running on the Hosted API](../tools/cli/run.md#running-on-the-hosted-api).
- **Bring Your Own Keys** — Use existing API keys from OpenAI, Anthropic, Google, Mistral, etc. See [Configure AI Providers](./configure-ai-providers.md).
- **Local AI** — Ollama, vLLM, LM Studio, or llama.cpp — no API keys required. See [Configure AI Providers](./configure-ai-providers.md).

A single run can always go the other way: `--hosted` sends it to the hosted API, `--local` keeps it on this machine.

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

On the hosted Pipelex API, it runs as it is. On this machine, the method names no model, so it runs on the deck's `default-general` alias, which `pipelex init` points at an OpenAI model. With a provider other than OpenAI or Azure OpenAI, point that alias at one of your provider's models first, by adding it to `~/.pipelex/inference/deck/x_custom_llm_deck.toml` — the models each provider serves are listed under `~/.pipelex/inference/backends/`:

```toml
[llm.aliases]
default-general = "claude-5-sonnet"     # an Anthropic model, for example
```

Then run it, where `pipelex init` set your runs to execute:

```bash
pipelex run bundle summarize.mthds --inputs inputs.json
```

The result is written under `results/`. From here, [The MTHDS Language Tutorial](./mthds-language-tutorial.md) builds a method step by step, and [CV batch screening, step by step](./cv-batch-screening.md) runs a method with several steps, typed concepts and a batch, from the CLI and from Python.

## Editor extension

`.mthds` syntax highlighting and flowchart visualization: the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=pipelex.pipelex), or the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex) for Cursor, Windsurf and other VS Code forks. `pipelex init` offers to install it when it detects your IDE.
