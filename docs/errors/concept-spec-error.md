---
title: "Concept spec (removed)"
description: "The `ConceptSpecError` Pipelex error class no longer exists."
---

<!-- pipelex:authored -->

# Concept spec (removed)

**`ConceptSpecError` is no longer raised.** It reported a malformed concept spec, the JSON authoring format that `pipelex-agent concept` and the `POST /v1/build/concept` route converted into MTHDS TOML. The command, the route and the concept spec are all gone: a concept is written in MTHDS directly, in a `[concept.<Code>]` section, and checked with `pipelex validate bundle` or [`POST /v1/validate`](../api-server/pipe-validate.md).

This page stays at the URL the error's `type_uri` published, so a link recorded from an earlier response still resolves.

[Back to Error Reference](index.md)
