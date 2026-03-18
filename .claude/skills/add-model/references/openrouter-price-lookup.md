# OpenRouter Price Lookup — API Reference

Use this reference to look up model costs when the user doesn't have them handy.
OpenRouter aggregates pricing across providers, making it a convenient single
source for input/output token costs.

## Quick lookup via WebFetch

The fastest way to get a model's pricing is to fetch from the OpenRouter API and
filter by name. No API key is required for basic lookups.

### LLM models

```
GET https://openrouter.ai/api/v1/models
```

Response: `{"data": [<model>, ...]}` where each model has:

```json
{
  "id": "anthropic/claude-sonnet-4",
  "name": "Claude Sonnet 4",
  "pricing": {
    "prompt": "0.000003",
    "completion": "0.000015"
  },
  "architecture": {
    "input_modalities": ["text", "image", "file"],
    "output_modalities": ["text"]
  },
  "supported_parameters": ["tools", "temperature", "top_p", ...]
}
```

### Image generation models

```
GET https://openrouter.ai/api/frontend/models?category=image-generation
```

Response uses a different schema with flat fields:

```json
{
  "slug": "openai/gpt-image-1",
  "name": "GPT Image 1",
  "per_input_token": 0.00001,
  "per_output_token": 0.00004,
  "input_modalities": ["text", "image"],
  "output_modalities": ["image"]
}
```

## Converting prices to our format

OpenRouter prices are **per token**. Our backend TOMLs use **per million tokens**.

```
cost_per_million = float(openrouter_price) * 1_000_000
```

Example: `"prompt": "0.000003"` -> `input = 3.0` in our TOML.

For image gen models from the frontend API, the prices are already floats (not
strings): `per_input_token: 0.00001` -> `input = 10`.

## Modality mapping

OpenRouter uses different names for modalities than we do:

| OpenRouter input | Our input |
|-----------------|-----------|
| `text` | `text` |
| `image` | `images` |
| `file` | `pdf` |

| OpenRouter output | Our output |
|------------------|-----------|
| `text` | `text` |
| `image` | `image` |

If `"tools"` is in `supported_parameters`, the model supports structured output
-> add `"structured"` to outputs in our TOML.

## Filtering for a specific model

The API returns all models at once. Filter client-side by matching on `id` or
`name`. The `id` field is provider-scoped (e.g., `openai/gpt-5.4`,
`anthropic/claude-4.6-opus`).
