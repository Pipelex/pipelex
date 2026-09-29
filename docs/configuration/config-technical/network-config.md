---
description: "Configure how Pipelex fetches the documents and images a method points at — the SSRF guard that refuses private destinations, and when a self-hosted deployment turns it off."
---

# Network Configuration

Configuration section: `[runtime.network]`

## Overview

A method's values can carry `http://` and `https://` URLs: an image input, a PDF to extract, a document a model reads, a file an image-generation provider hands back. When a model or an extractor needs the bytes rather than the link, Pipelex downloads them itself, following redirects. Since a method, a model's structured output or a function can produce any URL, the download is guarded: Pipelex refuses to connect to any destination that is not a public internet address.

```toml
[runtime.network]
is_fetch_ssrf_guard_enabled = true
```

The value above is the default.

## What the guard refuses

With `is_fetch_ssrf_guard_enabled = true`, every download of a value's URL is checked when the connection opens, on the first request and on every redirect hop to a new host. The host is resolved, and the connection is refused when the name is `localhost` or a cloud metadata alias, or when any address it resolves to is not globally routable: private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback, link-local (including the `169.254.169.254` metadata endpoint), carrier-grade NAT, multicast, reserved and unspecified addresses, in IPv4 and IPv6. Pipelex then connects to the address it checked, so a DNS record that changes between the check and the connection cannot slip through.

A refusal raises [`SsrfBlockedError`](../../errors/ssrf-blocked-error.md) and fails the pipe that needed the bytes. It is not treated as a failed download: where Pipelex would otherwise keep a generated image's remote URL after a download error, a refused URL fails the pipe instead. The error message names the host that was requested and never the address it resolved to.

A URL passed to a provider as a URL, for a model that fetches images itself, is not downloaded by Pipelex and is not checked by this guard.

## When to turn it off

Keep the guard on unless your deployment needs one of these:

- **Documents on a private network.** A self-hosted deployment inside a company network may exist precisely to read documents from an intranet host, which resolves to a private address.
- **Egress through an HTTP proxy.** The guard connects directly and ignores `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY`: through a proxy, the proxy makes the connection, and the guard would only ever see the proxy's own address. If a proxy is your only way out, remote downloads fail until the guard is off.

Turning it off restores a plain HTTP client, which honours the proxy variables and follows redirects without checking where they lead:

```toml
[runtime.network]
is_fetch_ssrf_guard_enabled = false
```

Do not turn it off on a server that runs methods from people you do not trust with your network.

## What the switch does not cover

- **Webhook delivery** is always guarded, whatever this switch says: a run's callback URL on a private address is refused.
- **Local paths and storage keys** (`pipelex-storage://`) are not network fetches; what a run may read from them is governed by the run's read scope, described in [Distributed content generation](../../under-the-hood/distributed-content-generation.md#what-a-leaf-may-read-the-read-scope).
