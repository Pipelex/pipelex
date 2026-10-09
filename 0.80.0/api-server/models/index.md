# Models

Two routes tell a client about the models a method may name on this runner: the deck it routes to, and whether one model reference resolves on it. A client asks them rather than keeping its own table of providers, its own parser of model references or its own copy of the deck.

## List the deck

**Endpoint:** `GET /v1/models`

The MTHDS Protocol's `models` operation, tagged `x-mthds-protocol` in the [OpenAPI artifact](openapi/pipelex-api.openapi.yaml). It answers the protocol's model deck: a flat `models` list of the deck's presets, each a `{name, type}` entry whose `type` is one of the protocol's model categories, plus this implementation's routing extensions, `aliases` and `waterfalls`, keyed by category because the same alias name exists in several categories.

The optional `type` query parameter filters the deck to one category: `llm`, `extract`, `img_gen`, `search` or `judgment`. It takes a single value, so a repeated `type` is a `422` `ValidationError`, and an unknown or empty one is a `422` `InvalidModelCategory`.

## Check a model reference

**Endpoint:** `GET /v1/models/check`

Answers whether one model reference resolves on this runner, as what kind of reference, to which model, and, when it does not, what the caller most likely meant. It reads the runner's deck and the models the runner can call, and runs no inference.

It is a **Pipelex API extension**, not an MTHDS Protocol route: it is not tagged `x-mthds-protocol`. The answer comes from pipelex's own reference parser and the deck lookups a validation runs, so a reference the check finds resolved in a category is one a pipe of that category may name in its `model` field, and one it finds not found is one a validation refuses. A client therefore needs no grammar of its own to read a reference.

### Request

| Query parameter | Required | Meaning |
|---|---:|---|
| `reference` | yes, once | The reference as a method's `model` field writes it: `$preset`, `@alias`, `~waterfall`, a bare model handle, or one of the spelled-out namespaces `preset:`, `alias:`, `waterfall:` and `handle:`. Leading and trailing whitespace is ignored, and the trimmed reference holds at most 199 characters. |
| `type` | no, at most once | The category to check in. When it is absent, the check is made in every category it covers. |

The check covers the protocol's model categories, in the protocol's order (`llm`, `extract`, `img_gen`, `search`, `judgment`), then `doc_gen`, the family of `PipeDocGen`. The protocol defines no category for `doc_gen`, so `GET /v1/models` leaves it out, but a method names a `doc_gen` model like any other, so the check answers in it. Every list the check returns that is ordered by category follows this order.

### Resolution

The reference is parsed as a method's `model` field is: a sigil first (`$` preset, `@` alias, `~` waterfall), then a spelled-out namespace, and otherwise a bare handle. `alias:best-gpt` and `@best-gpt` are the same reference. `handle:` is the bare kind's own namespace: it writes a bare name without reading a sigil, so `handle:@best-gpt` is the bare name `@best-gpt`, not the alias `best-gpt`, and `handle:best-gpt` is the bare name `best-gpt`. Like any bare name, it resolves as a model of that name, then an alias, then a waterfall of that name: where the runner serves a model `@best-gpt`, the check resolves to it and a run calls it, and where the deck holds nothing of that name, a validation refuses it as the check finds it `not_found`. A suggestion naming a handle spelled like a reference writes it with the namespace, `handle:@best-gpt`, so it can be written back as it is.

A reference **resolves in a category** when the runner holds its name there:

- a preset, an alias or a waterfall, when the deck defines that name in the category;
- a bare handle, as a run reads it: when the runner can call a model of that name in the category, among every model it can call and not only those the deck names; failing that, when the category defines an alias of that name, or a waterfall of that name while model fallback is on. A model of that name in another category does not make it resolve, so an LLM handle checked as `img_gen` is `not_found`, as a validation refuses it in a `PipeImgGen`.

The reference is `resolved` when it resolves in at least one category in scope, and `not_found` otherwise. Both values are definitive: a client that reads a value it does not know treats the reference as unresolved.

Resolution is a matter of names, like a validation. A preset, an alias or a waterfall the deck defines resolves even when its binding reaches no model the runner can call (a target on a backend the runner has not enabled, a waterfall none of whose usable steps it serves, a binding that leads back to itself through aliases and waterfalls), and its match says so with a `resolves_to` of `null`. A sigiled reference resolves by its sigil, in the check and in a run alike: `~best-gpt` is the waterfall even where an alias or a model is also named `best-gpt`. A waterfall step that leads back to an alias or a waterfall being resolved is a step no model serves, and so is a step reaching another waterfall none of whose models the runner serves, so the waterfall goes on to its next step. The check reads the deck as a run would and leaves no trace: it logs nothing, and the one-time notice a run logs when a waterfall falls back is left to that run. A run through such a reference fails where a validation passes, so a client shows it as a warning rather than as an unknown name.

### The verdict

A verdict is a `200`, whatever the resolution:

| Field | Type | Meaning |
|---|---|---|
| `reference` | string | The caller's reference, trimmed. |
| `kind` | `"preset"`, `"alias"`, `"waterfall"` or `"handle"` | What the reference names, from its parsing. |
| `name` | string | The reference without its sigil or namespace. |
| `category` | string or `null` | The `type` asked, or `null` when none was. |
| `resolution` | `"resolved"` or `"not_found"` | Whether the reference resolves in a category in scope. |
| `matches` | list | One entry per category in scope where the reference resolves, in category order. Empty on `not_found`. |
| `suggestions` | list of strings | On `not_found`, the nearest names the caller may have meant. |
| `other_kinds` | list of strings | On `not_found`, the same name under another kind, in the categories in scope. |
| `other_categories` | list of strings | On `not_found` with a `type`, the categories outside it where the same reference resolves. |

A `matches` entry says what the reference is in one category. A field that does not apply to the reference's kind is absent rather than `null`:

| Field | Present for | Meaning |
|---|---|---|
| `category` | every kind | The category the entry is about. |
| `resolves_to` | every kind | The model handle a run through the reference would call now in this category, or `null` when it would find none: a preset and an alias through their target, a waterfall through the first of its steps the runner serves (its first step alone when model fallback is off), and a handle itself, or, for a bare name that resolves through an alias or a waterfall, what that alias or waterfall resolves to. |
| `target` | preset, alias | The model the deck binds the name to, as the deck writes it, which may itself be a reference (`@default-premium`). |
| `description` | preset | The preset's description, or `null` when the deck gives it none. |
| `fallbacks` | waterfall | The waterfall's steps, in order. |
| `via` | handle | The presets, aliases and waterfalls of the category whose binding names the handle directly, each written as a reference. |

A preset, checked in its category:

```json
{
  "reference": "$writing-factual",
  "kind": "preset",
  "name": "writing-factual",
  "category": "llm",
  "resolution": "resolved",
  "matches": [
    { "category": "llm", "resolves_to": "gpt-5.6-sol", "target": "@default-premium", "description": "Factual writing with high accuracy" }
  ],
  "suggestions": [],
  "other_kinds": [],
  "other_categories": []
}
```

### Suggestions

On `not_found`, `suggestions`, `other_kinds` and `other_categories` say what the caller may have meant. They follow the rule a validation follows when it refuses an unknown model, so the check offers what a failing validation of the same reference offers, applied in each category in scope and joined in category order, a name two categories give appearing once, at its first place:

- `suggestions`: up to five names of the reference's own kind, nearest first, then, for each other kind under which the name does not exist exactly, up to three names of that kind, with a stricter threshold of nearness. For a handle, the candidates are every model the runner can call in the category.
- `other_kinds`: the same name under each other kind the category defines it as (`best-gpt` asked as a preset, found as `@best-gpt`). It is the likeliest fault, so a client shows it first.
- `other_categories`: when `type` was given, each other category where the same reference resolves (`$gen-image` asked as `llm`, found in `img_gen`).

Every name is written as a method would write it, a sigil for a preset, an alias or a waterfall and a bare name for a handle, without the kind labels a validation's report adds.

A preset name asked under the alias sigil:

```json
{
  "reference": "@writing-factual",
  "kind": "alias",
  "name": "writing-factual",
  "category": "llm",
  "resolution": "not_found",
  "matches": [],
  "suggestions": [],
  "other_kinds": ["$writing-factual"],
  "other_categories": []
}
```

### Refusals

A request the route cannot produce a verdict for is a `422` `application/problem+json` in the `input` error domain, carrying no verdict:

| Cause | `error_type` |
|---|---|
| `reference` missing or given more than once, or `type` given more than once | `ValidationError` |
| `reference` blank once trimmed, a sigil or namespace with nothing after it, or longer than 199 characters | `InvalidModelReference` |
| `type` unknown or empty | `InvalidModelCategory` |

A reference that parses and resolves nowhere is never refused: it is the `not_found` verdict, which is the successful product of the call. See [Error Responses](error-responses.md) for the problem document's shape.
