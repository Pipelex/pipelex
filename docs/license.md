---
title: License
description: "Pipelex's source-available license, the Elastic License 2.0, in full — and how Pipelex reads it, above all its limitation on hosted services."
hide:
- feedback
---

# License

```
--8<-- "LICENSE"
```

## How we read the Elastic License 2.0

The text above is the license itself. This section explains how we, the maintainers of Pipelex, read it, so that you can tell whether your use is fine.

### What does the license cover?

The Elastic License 2.0 is a source-available license: you may use, copy, distribute, modify and build on the software, within the limitations and conditions it sets. It applies to `pipelex` (the Python runtime), `pipelex-api` (the runner API server) and `@pipelex/mcp` (the MCP server), for every version released after 2026-09-14. Every earlier version of them stays under the MIT license it was released with.

The other Pipelex repositories, such as the SDKs, the starters and the plugins, keep their own licenses, and so does everything in the MTHDS standard's organization.

### Which limitation matters?

Of the limitations in the license, this is the one most users need to think about:

> You may not provide the software to third parties as a hosted or managed service, where the service provides users with access to any substantial set of the features or functionality of the software.

Most cases turn on the words "a substantial set of the features or functionality". To us, a service falls under them when its value to its users is Pipelex's own capability — running, building or validating MTHDS methods, or exposing them over MCP — and it is offered to third parties. A product that uses Pipelex behind the scenes to deliver something of its own is not such a service.

### What is allowed?

These uses are fine:

- Embedding `pipelex` in your own product or in your internal tools.
- Running `pipelex-api` or the MCP server for your own team or company, on your own infrastructure or in your own cloud account.
- Building an application whose end users benefit from the methods you run behind it, such as a contract-review product that runs your methods on the documents its customers upload.

### What is not allowed?

These uses are not allowed:

- Offering third parties a hosted API or runner whose service is executing MTHDS methods.
- Offering third parties a remote MCP server whose service is exposing Pipelex's capabilities.
- Offering a managed "Pipelex as a service", where your customers get Pipelex itself, operated by you.

### What else does the license ask of me?

- You must not remove, alter or obscure the licensing, copyright or other notices in the software.
- Anyone who gets a copy of any part of the software from you must also get a copy of the license.
- If you modify the software, your modified copies must carry prominent notices saying that you modified it.

The license text above, which each project ships as its `LICENSE` file, gives the exact terms.

### What is this page?

Apart from the license text itself, this page is an explanation of how Pipelex reads the Elastic License 2.0. It does not modify the license, add to it or grant any rights of its own: the license, as written in `LICENSE`, governs. If you have a question about your use, write to [oss@pipelex.com](mailto:oss@pipelex.com).
