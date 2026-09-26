---
title: "Model not found"
description: "Reference for the `ModelNotFoundError` Pipelex error class."
---

<!-- pipelex:authored -->

# Model not found

A model the run needs is not available: either the model handle is not in the model deck, or the provider answered that the model does not exist (HTTP 404). The provider case raises one of the subclasses per inference kind.

A handle missing from the model deck is reported with the fact alone, `Model handle 'x' was not found in the model deck.`, because the message reaches every surface a run failure reaches, a hosted run's stored error included. When the model belongs to a pipe of a run, the run's report is this error's, located: `Pipe 'summarize' failed (two_steps → summarize): Model handle 'x' was not found in the model deck.`

Whose fault it is depends on who named the model:

- **The caller's**, when the deck neither defines the reference nor names it in any of its own entries. Only the method being run can have named it, in an inline model setting such as `model = { model = "gpt-5.1", temperature = 0.2 }`, which the check at load does not look into. A model the deck serves only as another type, such as an LLM named in an image-generation setting, counts as undefined here, since the lookup of this type refuses it, unless one of the deck's own entries for this type names it. The error is then in the `input` domain, so an HTTP surface answers 422, and its message survives STRICT disclosure: it is the same mistake that `ModelChoiceNotFoundError` reports at load for a reference written as a string, except for a model of another type, which the check at load does not tell apart and which therefore surfaces only here.
- **The deployment's**, when the deck itself names the reference but cannot serve it: a preset, an alias target, a waterfall fallback or a default whose backend is not enabled. The domain is then `config`, the answer is 500, and the message is redacted under STRICT disclosure.

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
