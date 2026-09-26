---
title: "Model not found"
description: "Reference for the `ModelNotFoundError` Pipelex error class."
---

<!-- pipelex:authored -->

# Model not found

A model the run needs is not available: either the model handle is not in the model deck, or the provider answered that the model does not exist (HTTP 404). The provider case raises one of the subclasses per inference kind.

The message states the fact and nothing else, for instance `Model handle 'x' was not found in the model deck.`, because it reaches every surface a run failure reaches, a hosted run's stored error included. When the model belongs to a pipe of a run, the run's report is this error's, located: `Pipe 'summarize' failed (two_steps → summarize): Model handle 'x' was not found in the model deck.` A model the deployment does not serve is not the caller's fault, so the message is redacted under STRICT disclosure and the domain is `config`.

When you run a method locally with `pipelex run`, the CLI renders a panel naming the pipe, the model and the pipe stack, with the remedy for a local setup: your local model deck may be out of date, so delete the files under `.pipelex/inference/deck/` and run `pipelex init inference` to regenerate them, then check that the handle routes to an enabled backend you hold credentials for.

| Field | Value |
|---|---|
| `error_type` | `ModelNotFoundError` |
| `title` | Model not found |
| `type_uri` | `https://docs.pipelex.com/latest/errors/model-not-found-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.cogt.exceptions` |
| Parent class | [`CogtError`](cogt-error.md) |

[Back to Error Reference](index.md)
