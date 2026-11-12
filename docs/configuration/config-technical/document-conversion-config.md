---
description: "Configure whether and how Pipelex converts an Office file to PDF when a step needs one: the backend, the size limit, and the Gotenberg and soffice settings."
---

# Document Conversion Configuration

Configuration section: `[runtime.document_conversion]`

## Overview

When a step's model cannot read a Word, Excel or PowerPoint file, or the step asks for page views, Pipelex can hand the step the file's PDF instead. This section says whether it does, and with which converter. Conversion is off by default. What converting changes for a run, which steps convert and what a conversion drops are described in [Office File Conversion](../../features/office-file-conversion.md).

```toml
[runtime.document_conversion]
backend = "none"
max_source_bytes = 50_000_000

[runtime.document_conversion.gotenberg]
url = ""
timeout_seconds = 360
budget_seconds = 120

[runtime.document_conversion.soffice]
binary = "soffice"
timeout_seconds = 120
```

The values above are the defaults.

## `[runtime.document_conversion]`

| Key | Default | Meaning |
|---|---|---|
| `backend` | `"none"` | Which converter makes the PDF: `"none"` converts nothing, `"gotenberg"` posts the file to a Gotenberg container, and `"soffice"` runs LibreOffice on this machine. With `"none"`, every check and every step behaves as if conversion did not exist. |
| `max_source_bytes` | `50_000_000` | The largest file, in bytes, handed to the converter. A larger one fails the step with `input.too_large`: a file in storage is sized and refused without being read, a file at an `http(s)` URL is downloaded under this limit, refused before its body is read when the server declares a larger size and as soon as the bytes read pass it otherwise, and a local file or a data URL is refused before it is sent. It must be at least 1. |

## `[runtime.document_conversion.gotenberg]`

Read only when `backend = "gotenberg"`.

| Key | Default | Meaning |
|---|---|---|
| `url` | `""` | The container's base URL, such as `"http://localhost:3000"`. It must be an absolute `http` or `https` URL naming a host; empty or anything else stops Pipelex at startup with `runtime.misconfigured`. Nothing is contacted at startup, so a container that is down then is the converter being unavailable later, not a misconfiguration. |
| `timeout_seconds` | `360` | How long the client waits for the container's answer to one conversion. It must be greater than 0 and greater than `budget_seconds`. A hostile file was measured holding a connection for about six minutes before Gotenberg closed it, which is why the default allows for more. |
| `budget_seconds` | `120` | Gotenberg's own budget for one conversion, queue included: set it to the container's `--api-timeout`. A connection that ends without an answer after this many seconds is the file outrunning its budget, `input.too_large`, never retried; one that ends before it is the converter going away, retried and then `runtime.unavailable`. It must be greater than 0. |

There is no version to set. A PDF this backend makes is stamped, as its `converter-version` metadata, with the version Gotenberg names in the `Gotenberg-Version` header of the answer that carried it, which Gotenberg sends from 8.39.0 on: the backend needs **Gotenberg 8.39.0 or later**, and a conversion whose answer names no version fails with `runtime.misconfigured` (see [Office File Conversion](../../features/office-file-conversion.md#the-backends)).

A `timeout_seconds` that does not exceed `budget_seconds` is refused when the configuration loads, with `pipelex.config.invalid`: the client would stop waiting before the converter's budget ran out, and would read every slow file as a converter gone away.

## `[runtime.document_conversion.soffice]`

Read only when `backend = "soffice"`. This backend is for a developer's machine and for tests, never for a server converting other people's files: `soffice` runs with the rights of the process running Pipelex and isolates nothing.

| Key | Default | Meaning |
|---|---|---|
| `binary` | `"soffice"` | The `soffice` executable: a name looked up on the `PATH`, or a path to it. One that is not found stops Pipelex at startup with `runtime.misconfigured`. |
| `timeout_seconds` | `120` | How long one conversion may run before its whole process group is killed, which fails the step with `input.too_large`. It must be greater than 0. |

## Examples

A developer's machine with LibreOffice installed:

```toml
[runtime.document_conversion]
backend = "soffice"
```

A server with a Gotenberg container beside it, whose `--api-timeout` is the default two minutes:

```toml
[runtime.document_conversion]
backend = "gotenberg"

[runtime.document_conversion.gotenberg]
url = "http://gotenberg:3000"
```

On a distributed deployment, set the same values in every process: the process running a step decides whether it reads a PDF, and the process running the step's leaves converts.
