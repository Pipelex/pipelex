---
title: "LLM completion"
description: "Reference for the `LLMCompletionError` Pipelex error class."
---

<!-- pipelex:authored -->

# LLM completion

An LLM call answered, but its answer cannot be used as the pipe's output: the provider returned no choice, no text or a content type the worker does not read, or a structured generation failed for a reason no provider classified. Its category, and so whether it is retried, depends on the case, and its `user_action` gives the next step.

Two subclasses report the answers a provider returns as a success although the model did not finish its text. Every LLM worker reads its response's stop signal before it returns any text, so a text cut at its limit, refused or filtered fails its pipe instead of passing for a result:

- [`LLMCompletionTruncatedError`](llm-completion-truncated-error.md): the model was cut off before it finished, at its output limit (`max_tokens`) or at its context window. Raise the pipe's `max_tokens`, or shorten its input.
- [`LLMCompletionRefusedError`](llm-completion-refused-error.md): the model declined to write the text, or a provider's safety filter stopped it. Revise the pipe's prompt or its input.

Both are content errors in the `input` domain: they are not retryable, since the same request stops the same way, an HTTP surface answers them with 422, and their message survives STRICT disclosure. The message is one sentence naming the model by its deck handle, the pipe when the job knows it, the provider's stop value and, for a truncation, the output tokens used and the limit sent, then the next step; it never carries the partial text or the provider's body. An agent branches on the report's fields rather than the prose: `error_type`, `error_category` (`content`), `error_domain` (`input`), `retryable` (`false`) and `user_action`, whose kind is `change_input`.

The stop values each worker reads are those of its provider's SDK, read as one vocabulary so that a gateway passing each provider's own value through the OpenAI completions shape is read too: OpenAI's `finish_reason`, Anthropic's `stop_reason`, Bedrock Converse's `stopReason`, Gemini's `finish_reason`, Mistral's `finish_reason`, and the Responses API's `incomplete` status with its reason. A stop value the classifier does not know is logged at warning level with the model and taken as normal, so a value a provider adds later fails no call. Two signals are never normal, whatever reason comes with them: an `incomplete` Responses API answer is a truncation when its reason is missing or unknown, and a Gemini answer with no candidate whose prompt feedback names a block reason is a refusal. Structured generation is not read this way: its configured re-asks are left as they are.

A structured generation on an Anthropic model holds `max_tokens` to what its structured-output timeout lets the model produce. When that lowers the limit, an error the call raises ends with a sentence saying the limit was lowered and to what; a `max_tokens` the pipe set and the call lowers is also logged at warning level.

| Field | Value |
|---|---|
| `error_type` | `LLMCompletionError` |
| `title` | LLM completion |
| `type_uri` | `https://docs.pipelex.com/latest/errors/llm-completion-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.cogt.exceptions` |
| Parent class | [`CogtError`](cogt-error.md) |

[Back to Error Reference](index.md)
