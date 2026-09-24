<!--
Adapted from the onboarding source's front-door assembly, last re-read against the rendered file at
Pipelex/.github@81a3728 (onboarding/rendered/front-door.md). Every paragraph and every command is a
block's own words, so a change lands in the blocks first and is then carried here. Step 3 takes the
longer first-run/agent.md rather than the assembly's agent-short.md, and the webapp and API sections
take first-run/webapp.md, key.md, first-run/api-http.md, first-run/api-typescript.md and
first-run/api-python.md, where the assembly only links to them. This page's own are the headings, the
content tabs standing in for the assembly's <details> wrappers, the Node.js sentence in step 2 (the
blocks do not say it yet, and it goes once they do), the sentences pointing at other pages (the SDK references are the links-tail blocks), and the closing section, since the assembly's
last block describes the runtime repository that carries it. The Python sample's inputs dict is
wrapped by this repository's ruff format, which formats Python fences in Markdown; the code is the
block's.
-->

# Quick Start

Pipelex lets you build AI methods with your coding agent and run them anywhere — from your agent or your chatbot via MCP, as a webapp, or via API in any software.

## 1. Sign up

Sign up at [app.pipelex.com](https://app.pipelex.com).

## 2. Install the Pipelex plugin in your coding agent

The plugin is how you build methods: it gives your agent the skills that write and run them, a hook that checks every edit, and the Pipelex tools. The plugin's hook and the Pipelex tools run on Node.js, so you need Node.js on your `PATH`.

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

What the plugin holds, skill by skill, is on the [Pipelex Plugin](../features/pipelex-plugin.md) page.

## 3. Ask your agent for the method you want

> Design a method that reads an invoice PDF and returns the supplier, the total and the line items. Then run it on `~/Downloads/invoice.pdf` and save it to my Pipelex account.

`/pipelex-design` writes the method, the hook checks it on every edit, `/pipelex-inputs` gets your file ready, and `/pipelex-run` starts it and prints a run id. Come back to that id for the status, the results or the files it produced, days later if you want. `/pipelex-catalog` saves the method to your account, where your chatbot can run it too.

## Run your methods from your chatbot

The Pipelex MCP is a connector for your chatbot (ChatGPT, Claude): it gives it access to the Pipelex service, so it can list the methods saved in your account and run them right in the conversation. Your methods become your chatbot's tools. To build a method, use the Pipelex plugin in a coding agent such as Claude Code or Codex, as in steps 2 and 3 above.

Add the Pipelex MCP in your chatbot's settings by the address below — in Claude, that is **Add custom connector** — then sign in with your Pipelex account when asked. Nothing to install and no key: the Pipelex MCP runs on your signed-in session.

```
https://mcp.pipelex.com/mcp
```

Then ask your chatbot:

> What methods do I have?
>
> Run the invoice method on https://example.com/invoice.pdf

You get a run id straight away, and you can ask for its status, its results or the files it produced at any time.

Give the file as a URL the Pipelex MCP can reach. In ChatGPT you can attach it to the conversation instead and ask for a run on it; Claude has no way yet to hand the Pipelex MCP a file you attached.

## The other two ways

### As a webapp

Turn the method into a webapp with the [method-app template](https://github.com/Pipelex/pipelex-method-apps):

```bash
src=$(mktemp -d)
git clone --depth 1 https://github.com/Pipelex/pipelex-method-apps.git "$src"
mkdir -p my-app && cp -R "$src/webapp-js/." my-app/
cd my-app && git init

export PIPELEX_API_KEY=plx_sk_...
make create METHOD=path/to/my_method.mthds
make dev
```

The app calls Pipelex from its own server code, so it needs a key of its own — create one in your console at [app.pipelex.com](https://app.pipelex.com). `METHOD` is a `.mthds` file, a directory of them, a method id from your catalog (`mt_…`), or a published address. The form and the result view are rendered from the method's own contract, so adding a method writes no form fields.

### Via API

Use the method via API in any software through `POST /v1/start` — in TypeScript with [`@pipelex/sdk`](https://www.npmjs.com/package/@pipelex/sdk), in Python with [`pipelex-sdk`](https://pypi.org/project/pipelex-sdk/), or with any HTTP client.

Create an API key in your console at [app.pipelex.com](https://app.pipelex.com) and give it to your program as `PIPELEX_API_KEY` — the only thing to configure, since `PIPELEX_BASE_URL` already points at the hosted API.

```bash
export PIPELEX_API_KEY=plx_sk_...
```

=== "HTTP"

    ```bash
    curl -s https://api.pipelex.com/v1/start \
      -H "Authorization: Bearer $PIPELEX_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{
        "method_ref": "github.com/Pipelex/methods/invoice_extraction@v0.1.1",
        "inputs": {"document": {"url": "https://raw.githubusercontent.com/Pipelex/pipelex-cookbook/main/assets/extract_proof_of_purchase/restaurant_invoice.pdf", "mime_type": "application/pdf"}}
      }'
    # 202 → {"pipeline_run_id": "..."}

    RUN_ID=...     # the pipeline_run_id the start returned
    curl -s https://api.pipelex.com/v1/runs/$RUN_ID/results \
      -H "Authorization: Bearer $PIPELEX_API_KEY"
    ```

    The start returns immediately and the run is durable — poll the results route, or fetch them hours later by the same id.

=== "TypeScript"

    ```bash
    npm install @pipelex/sdk
    ```

    ```ts
    import { PipelexApiClient } from "@pipelex/sdk";

    const client = new PipelexApiClient({ apiKey: process.env.PIPELEX_API_KEY });

    const result = await client.startAndWaitForResult({
      method_ref: "github.com/Pipelex/methods/invoice_extraction@v0.1.1",
      inputs: {
        document: { url: "https://raw.githubusercontent.com/Pipelex/pipelex-cookbook/main/assets/extract_proof_of_purchase/restaurant_invoice.pdf", mime_type: "application/pdf" },
      },
    });

    console.log(result.main_stuff);
    ```

    More in the [`@pipelex/sdk` reference](https://github.com/Pipelex/pipelex-sdk-js/tree/main/docs).

=== "Python"

    ```bash
    pip install pipelex-sdk
    ```

    ```python
    import asyncio

    from pipelex_sdk.client import PipelexAPIClient


    async def main() -> None:
        async with PipelexAPIClient() as client:
            result = await client.start_and_wait(
                method_ref="github.com/Pipelex/methods/invoice_extraction@v0.1.1",
                inputs={
                    "document": {
                        "url": "https://raw.githubusercontent.com/Pipelex/pipelex-cookbook/main/assets/extract_proof_of_purchase/restaurant_invoice.pdf",
                        "mime_type": "application/pdf",
                    }
                },
            )
            print(result.main_stuff)


    asyncio.run(main())
    ```

    More in the [`pipelex-sdk` reference](https://github.com/Pipelex/pipelex-sdk-python/tree/main/docs).

**Next:** [what Pipelex is](https://go.pipelex.com/product) · [documentation](https://go.pipelex.com/docs) · [your console](https://app.pipelex.com) · [Discord](https://go.pipelex.com/discord)

## Prefer to run it yourself?

The Pipelex runtime runs your methods on your own machine, against the model providers you choose. [Run It Yourself](./run-it-yourself.md) installs it, and [The MTHDS Language Tutorial](./mthds-language-tutorial.md) walks through writing a method by hand.
