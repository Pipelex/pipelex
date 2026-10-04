---
title: "Pipe spec (removed)"
description: "The `PipeSpecError` Pipelex error class no longer exists."
---

<!-- pipelex:authored -->

# Pipe spec (removed)

**`PipeSpecError` is no longer raised.** It reported a malformed pipe spec, the JSON authoring format that `pipelex-agent pipe` and the `POST /v1/build/pipe-spec` route converted into MTHDS TOML. The command, the route and the pipe spec are all gone: a pipe is written in MTHDS directly, in a `[pipe.<code>]` section, and checked with `pipelex validate bundle` or [`POST /v1/validate`](../api-server/pipe-validate.md).

This page stays at the URL the error's `type_uri` published, so a link recorded from an earlier response still resolves.

[Back to Error Reference](index.md)
