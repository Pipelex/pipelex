---
title: "LLM completion truncated"
description: "Reference for the `LLMCompletionTruncatedError` Pipelex error class."
---

<!-- pipelex:authored -->

# LLM completion truncated

A text completion stopped before the model finished it: it hit its output limit, or its context window.

A provider answers such a completion as a success, with whatever text the model had written, empty or partial, and a stop value saying why it ended. The error tells the two limits apart, since they are lifted differently, and carries the one hit as its `truncation_limit`:

- **The output limit** (`max_tokens`): `length` on OpenAI and Mistral, `max_tokens` on Anthropic and Bedrock, `MAX_TOKENS` on Gemini, and an `incomplete` Responses API answer whose reason is `max_output_tokens`, missing or unknown (the status alone says the text is unfinished; the error names the reason as its stop value when the answer gives one, and `incomplete` when it gives none).
- **The context window** (`context_window`), which the input and the output filled together: `model_context_window_exceeded` on Anthropic and Bedrock, and `model_length` on Mistral.

The worker raises this error instead of handing the text back, so the pipe fails rather than passing a truncated contract, summary or JSON for a result.

The message names the model by its deck handle, the pipe, the stop value, the output tokens used and the `max_tokens` the request sent, or that it sent none, then the next step, which depends on the limit hit:

```text
The model 'claude-5-sonnet' was cut off before it finished the text of pipe 'ui_designer' (stop reason 'max_tokens', 4096 output tokens used, max_tokens set to 4096), so the text is incomplete. Raise the pipe's max_tokens, or shorten its input.
```

```text
The model 'gpt-5' was cut off before it finished the text of pipe 'ui_designer' (stop reason 'length', 16384 output tokens used, no max_tokens sent), so the text is incomplete. Set the pipe's max_tokens up to the model's limit, lower its reasoning effort, or shorten its input.
```

```text
The model 'claude-5-sonnet' filled its context window before it finished the text of pipe 'ui_designer' (stop reason 'model_context_window_exceeded', 812 output tokens used, max_tokens set to 4096), so the text is incomplete. Shorten the pipe's input, lower its reasoning effort, or choose a model with a larger context window.
```

A run reports it located at the failing pipe, `Pipe 'ui_designer' failed (flow → ui_designer): The model …`. The partial text and the provider's body never appear in it.

**What to do.** At the output limit, raise the pipe's `max_tokens`, for instance `model = { model = "claude-5-sonnet", max_tokens = 16384 }`, or shorten its input. When the request sent no `max_tokens`, the pipe's setting being left to the provider, the provider's own default cut the text, so there is no limit of the pipe's to raise: set the pipe's `max_tokens`, up to the model's limit, lower its reasoning effort, or shorten its input. When the model thinks before it writes, its thinking counts against the same limit, so a lower reasoning effort also leaves more room for the text. At the context window, a higher `max_tokens` cannot help, since the input and the output already filled the window: shorten the pipe's input, lower its reasoning effort, or choose a model with a larger context window.

**For an agent.** Branch on the report's fields: `error_type` is `LLMCompletionTruncatedError`, `error_category` is `content`, `error_domain` is `input` (an HTTP surface answers 422), `retryable` is `false`, since the same request stops at the same limit, and `user_action.kind` is `change_input`, its `detail` the next step for the limit hit. The message is caller-facing, so it survives STRICT disclosure.

| Field | Value |
|---|---|
| `error_type` | `LLMCompletionTruncatedError` |
| `title` | LLM completion truncated |
| `type_uri` | `https://docs.pipelex.com/latest/errors/llm-completion-truncated-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.cogt.exceptions` |
| Parent class | [`LLMCompletionError`](llm-completion-error.md) |

[Back to Error Reference](index.md)
