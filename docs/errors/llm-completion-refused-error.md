---
title: "LLM completion refused"
description: "Reference for the `LLMCompletionRefusedError` Pipelex error class."
---

<!-- pipelex:authored -->

# LLM completion refused

A text completion the model declined to write, or that a provider's safety filter stopped.

A provider answers such a completion as a success, often with no text at all and sometimes with the beginning of one, and a stop value saying why it ended: `content_filter` on OpenAI chat completions and on an `incomplete` Responses API answer, `refusal` on Anthropic, `content_filtered` and `guardrail_intervened` on Bedrock, and on Gemini `SAFETY`, `RECITATION`, `PROHIBITED_CONTENT`, `BLOCKLIST`, `SPII` and their kin. The worker raises this error instead of handing the text back, so the pipe fails rather than passing an empty or cut text for a result.

The message names the model by its deck handle, the pipe and the stop value, then the next step:

```text
The model 'claude-5-sonnet' declined to finish the text of pipe 'ui_designer', or a content filter stopped it (stop reason 'content_filtered'), so the text cannot be used. Revise the pipe's prompt or its input.
```

A run reports it located at the failing pipe, `Pipe 'ui_designer' failed (flow → ui_designer): The model …`. The partial text and the provider's body never appear in it.

**What to do.** Revise the pipe's prompt or its input: rephrase what triggered the refusal, or remove the content the filter stopped on. Another model, whose policy or filter differs, may also answer.

**For an agent.** Branch on the report's fields: `error_type` is `LLMCompletionRefusedError`, `error_category` is `content`, `error_domain` is `input` (an HTTP surface answers 422), `retryable` is `false`, since the same request is refused the same way, and `user_action.kind` is `change_input`. The message is caller-facing, so it survives STRICT disclosure.

| Field | Value |
|---|---|
| `error_type` | `LLMCompletionRefusedError` |
| `title` | LLM completion refused |
| `type_uri` | `https://docs.pipelex.com/latest/errors/llm-completion-refused-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.cogt.exceptions` |
| Parent class | [`LLMCompletionError`](llm-completion-error.md) |

[Back to Error Reference](index.md)
