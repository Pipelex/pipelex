<div align="center">
  <h1 align="center"><a href="https://www.pipelex.com/"><img src="https://raw.githubusercontent.com/Pipelex/pipelex/main/.github/assets/logo.png" alt="Pipelex" width="400" style="max-width: 100%; height: auto;"></a></h1>

  <h2 align="center">Turn your expertise into an AI-powered App, MCP or API</h2>
  <p align="center">Describe how the work gets done in plain English, and your coding agent builds it into a method with the Pipelex plugin. A method is a multi-step, deterministic AI procedure that chains LLMs, OCR, image generation and more. Then run it as a webapp for your team or as SaaS for your customers, as an MCP for chatbots, or via API for your software.</p>

  <div>
    <a href="https://go.pipelex.com/demo"><strong>Demo</strong></a> -
    <a href="https://docs.pipelex.com/"><strong>Documentation</strong></a> -
    <a href="https://mthds.sh"><strong>Hub</strong></a> -
    <a href="https://go.pipelex.com/discord"><strong>Discord</strong></a>
  </div>
  <br/>

  <p align="center">
    <a href="https://github.com/Pipelex/pipelex/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Elastic--2.0-blue.svg" alt="Elastic License 2.0"></a>
    <a href="https://github.com/Pipelex/pipelex/tree/main/tests"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Pipelex/pipelex/main/.badges/tests.json" alt="Tests"></a>
    <a href="https://pypi.org/project/pipelex/"><img src="https://img.shields.io/pypi/v/pipelex?logo=pypi&logoColor=white&color=blue&style=flat-square" alt="PyPI – latest release"></a>
  </p>
</div>

<!-- onboarding: front-door -->
<!-- Generated from the Pipelex onboarding source; this region is replaced from https://raw.githubusercontent.com/Pipelex/.github/main/onboarding/rendered/front-door.md — do not edit it here. -->
## Quick start

Pipelex lets you build AI methods with your coding agent and run them anywhere: as an MCP for chatbots, as a webapp for people, or via API for your software.

**1. Sign up at [app.pipelex.com](https://app.pipelex.com).**

**2. Install the Pipelex plugin in your coding agent.** The plugin gives your agent the skills that build methods, run them and put them in your software, a hook that checks every edit, and the Pipelex tools.

<details open><summary><b>Claude Code</b></summary>

```bash
claude plugin marketplace add Pipelex/pipelex-plugins
claude plugin install pipelex@pipelex-plugins
```

Claude Code asks for an API key when you enable the plugin, and stores it in your OS keychain — create one in your console at [app.pipelex.com](https://app.pipelex.com). The skills, the hook that checks every edit and the Pipelex tools load with it. The plugin's hook and the Pipelex tools run on Node.js, so you need Node.js on your `PATH`.

Claude Code also loads what you have added to your Claude account, so if you added the Pipelex MCP to Claude, Claude Code has it too. An agent with the plugin does not need the Pipelex MCP, and there is nothing to turn off: when both are present, the Pipelex MCP defers to the plugin's tools.

</details>

<details open><summary><b>Codex</b></summary>

```bash
codex plugin marketplace add Pipelex/pipelex-plugins
export PIPELEX_API_KEY=plx_sk_...     # create one in your console at app.pipelex.com
```

Restart Codex, run `/plugins` to install `pipelex`, and trust the plugin hook on first run. Requires Codex 0.141 or later. The plugin's hook and the Pipelex tools run on Node.js, so you need Node.js on your `PATH`.

</details>

**3. Ask your agent for the method you want.**

> Design a method that reads an invoice PDF and returns the supplier, the total and the line items. Then run it on `~/Downloads/invoice.pdf` and save it to my Pipelex account.

`/pipelex-design` writes the method, the hook checks it on every edit, `/pipelex-run` starts it and prints a run id you can come back to, and `/pipelex-catalog` saves it to your account, where your chatbot can run it too.

**Run your methods from your chatbot.** The Pipelex MCP is a connector for your chatbot (ChatGPT, Claude): it gives it access to the Pipelex service, so it can list the methods saved in your account and run them right in the conversation. Your methods become your chatbot's tools. To build a method, use the Pipelex plugin in a coding agent such as Claude Code or Codex, as in steps 2 and 3 above.

Add the Pipelex MCP in your chatbot's settings by the address below — in Claude, that is **Add custom connector** — then sign in with your Pipelex account when asked. Nothing to install and no key: the Pipelex MCP runs on your signed-in session.

```
https://mcp.pipelex.com/mcp
```

Then ask your chatbot:

> What methods do I have?
>
> Run the invoice method on https://raw.githubusercontent.com/Pipelex/pipelex-cookbook/main/assets/extract_proof_of_purchase/restaurant_invoice.pdf

You get a run id straight away, and you can ask for its status, its results or the files it produced at any time.

Give the file as a URL the Pipelex MCP can reach. In ChatGPT you can attach it to the conversation instead and ask for a run on it; Claude has no way yet to hand the Pipelex MCP a file you attached.

**The other two ways, built by your agent too.** Ask it for a webapp around the method, and `/pipelex-scaffold` creates a new app from the [method-app template](https://github.com/Pipelex/pipelex-method-apps) and leaves it running on your machine. Ask it to call the method from your TypeScript or Python code, and `/pipelex-integrate` generates the method's types and one typed call that runs it, through the TypeScript SDK [`@pipelex/sdk`](https://www.npmjs.com/package/@pipelex/sdk) or the Python SDK [`pipelex-sdk`](https://pypi.org/project/pipelex-sdk/). Any other software runs a method via API through `POST /v1/start`, with any HTTP client.

**Next:** [what Pipelex is](https://go.pipelex.com/product) · [documentation](https://go.pipelex.com/docs) · [your console](https://app.pipelex.com) · [Discord](https://go.pipelex.com/discord)

Prefer to run it yourself? This repository is the Pipelex runtime — its own install and configuration are below.
<!-- /onboarding -->

## Run it yourself

This repository is the Pipelex runtime: the Python package that reads a `.mthds` file and runs it. Install it and everything happens on your own machine, against the model providers you choose.

### Install

```bash
uv tool install "pipelex[cli]"
pipelex init
pipelex doctor
```

`pipelex init` writes your `~/.pipelex` configuration and offers to install the editor extension; `pipelex doctor` reports what is configured and what is missing. The `cli` extra installs Rich, which the `pipelex` and `pipelex-agent` commands render their output through.

Some providers and features need an extra:

- `cli`: Rich, for the `pipelex` and `pipelex-agent` commands, the `console` log sink and the `rich` pretty-print mode. Install it wherever Pipelex runs in a terminal; a server leaves it out and selects the `json` log sink with the `poor` or `silent` pretty-print mode, and then nothing the runtime does on the way to running a method asks for Rich. Leaving the extra out does not make the environment Rich-free: `typer` and `instructor` are core dependencies and both require Rich, so a stock install still contains it
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

### Configure AI Access

- **Bring Your Own Keys** — Use existing API keys from OpenAI, Anthropic, Google, Mistral, etc. See [Configure AI Providers](https://docs.pipelex.com/latest/setup/configure-ai-providers/).
- **Local AI** — Ollama, vLLM, LM Studio, or llama.cpp — no API keys required. See [Configure AI Providers](https://docs.pipelex.com/latest/setup/configure-ai-providers/).

### Run a method

Save the method shown under [What a method looks like](#what-a-method-looks-like), further down, as `summarize.mthds`, and its inputs as `inputs.json`:

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

The result is written under `results/`. For a method with several steps, typed concepts and a batch, run from the CLI and from Python, read [CV batch screening, step by step](https://docs.pipelex.com/latest/get-started/cv-batch-screening/).

### Editor extension

`.mthds` syntax highlighting and flowchart visualization: the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=pipelex.pipelex), or the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex) for Cursor, Windsurf and other VS Code forks. `pipelex init` offers to install it when it detects your IDE.

## See Pipelex in action

**Claude Code builds your AI method**

<a href="https://go.pipelex.com/demo">
  <img src="https://go.pipelex.com/demo-thumbnail" alt="Pipelex Demo" width="500" style="max-width: 100%; height: auto;">
</a>

## What a method looks like

A method is a reusable, typed AI procedure, written in [MTHDS](https://mthds.ai/latest/), an open standard, and saved as a `.mthds` file. Each step is explicit, each output is structured, and every run is repeatable.

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

From here, Pipelex handles model routing across providers, structured output parsing, and pipeline orchestration.

## Why methods?

| | |
|---|---|
| **Declarative** — Human-readable `.mthds` files that work across models | **Typed** — Semantic types: AI understands what you mean, every input/output connects with purpose |
| **Repeatable** — Deterministic orchestration with controlled room for AI creativity | **Composable** — Chain pipes into sequences, nest methods inside methods, share with the community |

## Run anywhere

The same `.mthds` file runs from multiple execution targets:

| Target | How |
|--------|-----|
| **CLI** | `pipelex run bundle method.mthds --inputs inputs.json` |
| **Python** | `PipelexMTHDSProtocol().execute(...)` |
| **TypeScript / Node** | [`@pipelex/sdk`](https://www.npmjs.com/package/@pipelex/sdk) against the hosted API, or [`mthds`](https://www.npmjs.com/package/mthds) against any MTHDS API |
| **REST API** | Self-host [`pipelex-api`](https://github.com/Pipelex/pipelex-api); the hosted API is the one in the Quick start above |
| **MCP** | The [Pipelex MCP](https://github.com/Pipelex/pipelex-mcp): your chatbot runs the methods saved in your account |
| **n8n** | [`n8n-nodes-pipelex`](https://github.com/Pipelex/n8n-nodes-pipelex) for workflow automation |

## The ecosystem

| | Description | Link |
|---|---|---|
| **MTHDS standard** | The open standard specification — language, package system, and typed concepts | [mthds.ai](https://mthds.ai/latest/) |
| **MTHDS Hub** | Discover and share methods — browse packages, search by signature | [mthds.sh](https://mthds.sh) |
| **Pipelex plugin** | The Pipelex plugin for Claude Code and Codex: skills that build and run methods, a hook that checks every edit, and the Pipelex tools | [github.com/Pipelex/pipelex-plugins](https://github.com/Pipelex/pipelex-plugins) |
| **Pipelex MCP** | The Pipelex MCP, which ChatGPT or Claude adds to run the methods saved in your account | [github.com/Pipelex/pipelex-mcp](https://github.com/Pipelex/pipelex-mcp) |
| **Method library** | Public methods to run by their address or to fork — `github.com/Pipelex/methods/<method_name>` | [github.com/Pipelex/methods](https://github.com/Pipelex/methods) |
| **TypeScript starter** | A Next.js app that runs methods through `@pipelex/sdk`, with worked examples to copy | [github.com/Pipelex/pipelex-starter-js](https://github.com/Pipelex/pipelex-starter-js) |

## Documentation

- [docs.pipelex.com](https://docs.pipelex.com/): the Pipelex documentation, from the MTHDS language tutorial to the CLI reference.
- [CV batch screening, step by step](https://docs.pipelex.com/latest/get-started/cv-batch-screening/): a production method with its concepts, its pipes and its flowchart, and how to run it from the CLI and from Python.
- [The cookbook](https://github.com/Pipelex/pipelex-cookbook): Pipelex's example methods, which run by their address on the hosted API with nothing to install, each with a page showing every way to use it: in your chatbot, in your coding agent, in your code, as an app, or as a method of your own.
- [The MTHDS standard](https://mthds.ai/latest/): the language a method is written in.
- [The changelog](https://docs.pipelex.com/latest/changelog/).

## Develop

To work on Pipelex itself, fork and clone the repository, then:

```bash
make install   # create .venv and install the dependencies
make check     # formatting, lint and type checks
make test      # the unit tests
```

The [contributing guide](https://github.com/Pipelex/pipelex/blob/main/CONTRIBUTING.md) says how to configure `.env`, name a branch and open a pull request.

## Community

Ask questions and share what you build on [Discord](https://go.pipelex.com/discord), report a bug in [GitHub Issues](https://github.com/Pipelex/pipelex/issues), propose an idea in [Discussions](https://github.com/Pipelex/pipelex/discussions), and watch demos on [YouTube](https://www.youtube.com/@PipelexAI).

## License

The Pipelex runtime is source-available under the Elastic License 2.0 (ELv2); see [LICENSE](https://github.com/Pipelex/pipelex/blob/main/LICENSE) for the terms, and the [license page](https://docs.pipelex.com/latest/license/) for how Pipelex reads them. Runtime dependencies are distributed under their own licenses via PyPI.

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025-2026 Evotis S.A.S.
