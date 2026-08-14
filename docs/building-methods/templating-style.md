---
title: "Templating Style"
description: "Declare how a pipe's inputs are tagged and formatted into its prompt with templating_style — XML tags, back-tick fences, square brackets, or no tag at all."
---

# Templating Style

When you write `@article` in a prompt, Pipelex inserts the content of the `article` input — wrapped in a tag so the model can tell where your data starts and stops. **Templating style is what decides the shape of that wrapper.**

It is an authoring decision, not a property of the model you happen to run on. You declare it on the pipe; the model never changes it.

```toml
[pipe.summarize_article]
type = "PipeLLM"
description = "Summarize an article"
inputs = { article = "Text" }
output = "Text"
templating_style = "xml"
prompt = """
Summarize the article below.

@article

Keep it to one sentence.
"""
```

renders as:

```text
Summarize the article below.

<article>
Bees pollinate a third of the food we eat.
</article>

Keep it to one sentence.
```

## Two levels, and that's all

A prompt renders under exactly one style, resolved in two steps:

1. **What the pipe declares** — the `templating_style` field on the pipe.
2. **The runtime default** — when the pipe declares nothing.

There is no third level. The style is never derived from the model, the provider, or the backend: a method that renders XML on one model renders XML on all of them.

The shipped default is `xml` with `plain` text, set in `pipelex.toml`:

```toml
[pipelex.templating_config]
default_templating_style = { tag_style = "xml" }
```

Override it in your project's `.pipelex/pipelex.toml` to change the house style for every pipe that doesn't declare one.

## Two ways to write it

**Bare string** — the common case. The string is the tag style; the text format stays `plain`.

```toml
templating_style = "square_brackets"
```

**Inline table** — when you also want to set the text format.

```toml
templating_style = { tag_style = "xml", text_format = "markdown" }
```

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `tag_style` | string | How `@variable` insertions are wrapped: `xml`, `ticks`, `square_brackets`, `no_tag` | Yes |
| `text_format` | string | How values are rendered inside the prompt: `plain` (default), `markdown`, `html`, `json` | No |

## The tag styles

Each style below shows what `@article` produces for an input named `article`.

### `xml`

The default, and the best-supported shape across current models.

```text
<article>
Bees pollinate a third of the food we eat.
</article>
```

### `ticks`

A fenced code block, prefixed with the variable name.

````text
article: ```
Bees pollinate a third of the food we eat.
```
````

### `square_brackets`

BBCode-flavored delimiters.

```text
[article]
Bees pollinate a third of the food we eat.
[/article]
```

### `no_tag`

The value, bare. Nothing is added — use it when your prompt already provides its own framing, or when a wrapper would confuse the task.

```text
Bees pollinate a third of the food we eat.
```

!!! note "Tag names come from the variable"
    `@article` tags with `article`. A value with no name of its own — anything piped through `with_images`, for instance — falls back to `data`.

## What the two sigils do

The two insertion sigils are governed by different halves of the style:

- **`@variable`** on its own line inserts the whole input, wrapped per `tag_style`.
- **`$variable`** inline inserts the value formatted per `text_format`, with no wrapper.

So a pipe with `templating_style = "no_tag"` and one with `$article` instead of `@article` produce similar-looking output for different reasons — the first chose not to wrap, the second never asked for a wrapper.

## Beyond PipeLLM

- **[`PipeCompose`](pipes/pipe-operators/PipeCompose.md)** takes `templating_style` on its `[pipe.name.template]` section, for templates that use the `tag` or `format` filters directly. A compose pipe that declares nothing renders under the same runtime default.
- **`PipeImgGen` and `PipeSearch`** have no authored style of their own — their prompts render under the runtime default. Image and search prompts rarely benefit from tagging, but they do render under a real style rather than an invisible fallback.
- **Construct-mode template fields** and the built-in structuring prompts likewise resolve a real style, so a template of yours that uses `| tag` behaves the same everywhere.

!!! warning "A style is always required, and never invented"
    The Jinja2 `tag` and `format` filters have no fallback of their own. Every prompt-rendering entry point resolves a real style before rendering, so a template using `| tag` always renders in a shape somebody chose. If you build prompts through the kernel API directly and omit the style, you get a loud error rather than a silent default.

## Choosing a style

- **Stay on `xml`** unless you have a reason. It is unambiguous, it nests, and every major model family handles it well.
- **Reach for `no_tag`** when the input *is* the prompt — a single block of text that your instructions already introduce.
- **Set `text_format = "markdown"`** when the model's output quality depends on seeing structured values (tables, nested objects) rather than flattened text.
- **Declare the style on the pipe** when a specific pipe needs a shape the rest of your method doesn't; change the config default when your whole project wants a different house style.

## Related Documentation

- [PipeLLM](pipes/pipe-operators/PipeLLM.md) - The `templating_style` parameter in context
- [PipeCompose](pipes/pipe-operators/PipeCompose.md) - Templating style on composed templates
- [LLM Integration](../features/llm-integration.md) - High-level LLM capability overview
- [Optimize Cost & Quality](configure-ai-llm-to-optimize-methods.md) - Model choice and presets
