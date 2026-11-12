---
description: "Configure how Pipelex fetches the documents and images a method points at — the SSRF guard that refuses private destinations, the cap on how many bytes a download reads, and when a self-hosted deployment changes them."
---

# Network Configuration

Configuration section: `[runtime.network]`

## Overview

A method's values can carry `http://` and `https://` URLs: an image input, a PDF to extract, a document a model reads, a file an image-generation provider hands back. When a model or an extractor needs the bytes rather than the link, Pipelex downloads them itself, following redirects. Since a method, a model's structured output or a function can produce any URL, the download is guarded: Pipelex refuses to connect to any destination that is not a public internet address, and it refuses to read more than a set number of bytes from any of them.

```toml
[runtime.network]
is_fetch_ssrf_guard_enabled = true
max_fetch_bytes = 100_000_000
```

The values above are the defaults.

## What the guard refuses

With `is_fetch_ssrf_guard_enabled = true`, every download of a value's URL is checked when the connection opens, on the first request and on every redirect hop to a new host. The host is resolved, and the connection is refused when the name is `localhost` or a cloud metadata alias, or when any address it resolves to is not globally routable: private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback, link-local (including the `169.254.169.254` metadata endpoint), carrier-grade NAT, multicast, reserved and unspecified addresses, in IPv4 and IPv6. Pipelex then connects to the address it checked, so a DNS record that changes between the check and the connection cannot slip through.

A refusal raises `SsrfBlockedError`, with the code `security.input_url_refused`, and fails the pipe that needed the bytes. It is not treated as a failed download: where Pipelex would otherwise keep a generated image's remote URL after a download error, a refused URL fails the pipe instead. The error message names neither the host that was requested, which is part of the run's data or of the caller's callback URL, nor the address it resolved to.

A URL passed to a provider as a URL, for a model that fetches images itself, is not downloaded by Pipelex and is not checked by this guard.

## When to turn it off

Keep the guard on unless your deployment needs one of these:

- **Documents on a private network.** A self-hosted deployment inside a company network may exist precisely to read documents from an intranet host, which resolves to a private address.
- **An image-generation server on your own machine or network.** A self-hosted model server that answers with a link to the image on `localhost` or a private address has that link refused when Pipelex downloads the image, which it does while `[runtime.storage] is_fetch_remote_content_enabled` is on.
- **Egress through an HTTP proxy.** The guard connects directly and ignores `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY`: through a proxy, the proxy makes the connection, and the guard would only ever see the proxy's own address. If a proxy is your only way out, remote downloads fail until the guard is off.

Turning it off restores a plain HTTP client, which honours the proxy variables and follows redirects without checking where they lead:

```toml
[runtime.network]
is_fetch_ssrf_guard_enabled = false
```

Do not turn it off on a server that runs methods from people you do not trust with your network.

## How much a download reads

`max_fetch_bytes` is the most bytes Pipelex reads from any URL it downloads, 100 MB by default. It must be at least 1, and there is no setting that turns the cap off. Whoever chooses the URL also chooses how large the file behind it is, so without a cap a single URL serving several gigabytes, or a small compressed body that expands to that size, could exhaust the memory of the process running the method, and every run that process was serving would fail with it.

The download is read as a stream. Pipelex follows redirects itself and closes each redirect's response without reading its body, so only the body of the final response is ever read, and that body is checked twice:

1. **The declared size.** When the response is not compressed and its `Content-Length` already passes the cap, the download is refused before any of the body is read. A compressed response's `Content-Length` is its compressed size, which says nothing certain about the size it decodes to, so it is held to the compressed bound described below instead, and one that declares more than that bound is refused unread too. A missing `Content-Length`, or one that is not a number, skips this check.
2. **The bytes actually read.** As the body arrives, Pipelex counts the bytes it has received and stops reading as soon as they pass the cap. A compressed body is counted after decompression, and the decompression itself is bounded: each step is asked for no more than the bytes the cap still allows, so a `gzip` body that is small on the wire but enormous once decoded is refused one byte past the cap, without ever being expanded in memory. The compressed bytes are bounded too: a compressed body may not pass the cap by more than 64 KiB on the wire, the compressed bound, so a body that keeps arriving without decoding to anything, such as empty compressed blocks or an endless `gzip` header, is refused rather than read for as long as the server keeps sending. No real compressed body comes near that margin, since data that cannot be compressed grows by only a few bytes per 64 KiB.

Pipelex asks for `gzip` and `deflate` only, and reads a body in one of those codings or in none. A response in any other content coding, such as `br` or `zstd`, or with several codings stacked on one another, is refused before its body is read with `input.file_unreadable`, whose reason says the server answered in a content encoding the runtime does not read. A compressed body that does not decode is refused the same way, and so is one that stops before its compressed stream ends, as when the connection closes mid-body, or that carries anything after the end of a `deflate` stream. A `gzip` body may hold several members one after another, which are read in turn under the same cap, as the `gzip` format allows, and NUL bytes after a member are skipped as padding, as Python's own `gzip` module skips them, though they still count toward the compressed bound. A `deflate` body may be zlib-wrapped or raw, since servers send both under that name: Pipelex reads it as zlib-wrapped and, when that fails before any output, reads every byte received so far again as raw deflate, so the outcome does not depend on how the network split the body. An empty body labelled as compressed reads as empty.

A refusal raises `RemoteFileTooLargeError` and fails the pipe that needed the bytes, with the code `input.too_large`, whose `limit` and `size` are in the unit of the bound that fired, which the error records as its `bound`. For the decoded bound, `limit` is the cap and `size` the declared length or the number of decoded bytes read when the read stopped; for the compressed bound, `limit` is the compressed bound, the cap plus 64 KiB, and `size` the compressed length declared or received, and the message says the body is compressed. The error is not retried, since the same URL would serve the same file. Its message names those two numbers and never the URL. A file an image-generation provider pointed at is the provider's answer rather than the caller's input, so a refusal there is coded `provider.response_invalid`, and where Pipelex would otherwise keep a generated image's remote URL after a failed download, it keeps the URL here too rather than storing a very large object.

A step with a limit of its own downloads under the smaller of that limit and `max_fetch_bytes`: a step's limit can tighten the cap, never loosen it. The conversion of an Office file to PDF downloads a source at a URL under the smaller of its `max_source_bytes`, described in [Document conversion](document-conversion-config.md), and `max_fetch_bytes`, and reports a source past it as a conversion that is too large, naming the limit that applied and, in its message and in the advice a local run prints, the setting that set it.

Raise the cap on a self-hosted deployment whose methods read larger files from sources you trust:

```toml
[runtime.network]
max_fetch_bytes = 500_000_000
```

Every download holds its whole body in memory, and most are then encoded once more to be sent to a model, so leave the process room for several downloads of that size at once.

## What the switch does not cover

- **Webhook delivery** is always guarded, whatever this switch says: a run's callback URL on a private address is refused.
- **Local paths and storage keys** (`pipelex-storage://`) are not network fetches; what a run may read from them is governed by the run's read scope, described in [Distributed content generation](../../under-the-hood/distributed-content-generation.md#what-a-leaf-may-read-the-read-scope).
