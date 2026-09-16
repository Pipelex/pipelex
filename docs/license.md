---
title: License
description: "How Pipelex reads its source-available license, the Elastic License 2.0, above all its limitation on hosted services — followed by the license in full."
hide:
- feedback
---

# License

## How we read the Elastic License 2.0

This section explains how we, the maintainers of Pipelex, read the license, so that you can tell whether your use is fine. The license itself follows, in full, [at the end of this page](#full-text-of-the-elastic-license-20).

### What does the license cover?

The Elastic License 2.0 is a source-available license: you may use, copy, distribute, modify and build on the software, within the limitations and conditions it sets. It applies to `pipelex` (the Python runtime), `pipelex-api` (the runner API server) and `@pipelex/mcp` (the MCP server), for every version released after 2026-09-14. Every earlier version of them stays under the MIT license it was released with.

The other Pipelex repositories, such as the SDKs, the starters and the plugins, keep their own licenses, and so does the MTHDS language standard.

### What can I do with Pipelex?

Nearly everything you would want to. For instance, all of these uses are fine:

- Embedding `pipelex` in your own product, including a service you offer to others whose features run your methods behind the scenes, such as a contract-review product that runs your methods on the documents its customers upload.
- Using Pipelex in your internal tools.
- Running `pipelex-api` or the MCP server for your own team or company, on your own infrastructure or in your own cloud account.

### What is not allowed?

One thing: using our software to host a service that runs any method for anyone. For instance, these uses are not allowed:

- Offering third parties a hosted API or runner that executes methods, whether they send the methods themselves or pick them from a catalog you make available.
- Offering third parties a remote MCP server through which they run the methods of their choice, their own or a catalog's.
- Offering a managed "Pipelex as a service", where your customers get Pipelex itself, operated by you.

The difference from the uses above is what your customers come for. In your own product, they come for what the product does, and your methods are how it does it: the customers of a contract-review product get their contracts reviewed, however many methods run behind it. In a service that runs methods, whether sent to it or picked from a catalog, running methods is what they come for, and what they get is Pipelex itself.

This is how the license says it:

> You may not provide the software to third parties as a hosted or managed service, where the service provides users with access to any substantial set of the features or functionality of the software.

### What else does the license ask of me?

- You must not remove, alter or obscure the licensing, copyright or other notices in the software.
- Anyone who gets a copy of any part of the software from you must also get a copy of the license.
- If you modify the software, your modified copies must carry prominent notices saying that you modified it.

The license text below, which each project ships as its `LICENSE` file, gives the exact terms.

### What is this page?

Apart from the license text at its end, this page is an explanation of how Pipelex reads the Elastic License 2.0. It does not modify the license, add to it or grant any rights of its own: the license, as written in `LICENSE`, governs. If you have a question about your use, write to [oss@pipelex.com](mailto:oss@pipelex.com).

## Full text of the Elastic License 2.0

<div class="license-text" markdown>

--8<-- "LICENSE"

</div>
