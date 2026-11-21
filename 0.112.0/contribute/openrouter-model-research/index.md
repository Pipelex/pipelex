# Research OpenRouter models

From a Pipelex development checkout, run `make install` to provision `.venv`, then use its development CLI:

```bash
.venv/bin/pipelex-dev openrouter list-models -f claude
.venv/bin/pipelex-dev openrouter list-models -f claude --json
.venv/bin/pipelex-dev openrouter list-models --sort context_length
.venv/bin/pipelex-dev openrouter list-models -f flux --save
```

It needs no hosted credentials or Pipelex boot. `OPENROUTER_API_KEY` is optional: when present, it is sent as a bearer token; otherwise the catalog request is anonymous. No inference calls are made.

The command reads the [public models API](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties) with `output_modalities=all`, including image models, and follows catalog pagination. It does not use the frontend API. `--category` forwards OpenRouter's category filter. `--filter` matches a substring of the name or ID, ignoring case. `--sort` accepts `name`, `created` (newest first) and `context_length` (largest **context window** first); the table explicitly calls that column context tokens.

Markdown is the default. `--json` emits an envelope with `ok`, `models`, `saved_to` and `skipped_model_ids`, without a banner. Every model retains the catalog's supplied metadata. Expected failures emit `ok: false` and `error` on stderr in JSON mode, or Markdown on stderr otherwise. An empty lookup is a successful result with no models; attempting to save it is refused.

`--save` writes `generated/openrouter_models.toml` relative to the current directory. Category and name filters add sanitized suffixes, such as `generated/openrouter_models_claude.toml`. Existing files are never overwritten. JSON mode can be combined with saving; `saved_to` reports the generated path.

Exports are disabled draft entries. Review each entry before changing `enabled` to true. The exporter uses the current runtime's backend document validator, quotes model names safely and converts known token prices into USD per million tokens. Missing, negative or nonfinite prices remain absent; absent costs do not imply free inference. Non-token charges, image pricing, routing, reasoning configuration and provider restrictions require manual review. Context length is never exported as `max_tokens`: that field comes only from `top_provider.max_completion_tokens`. Tool support alone never implies structured output; only explicit `structured_outputs` metadata adds that capability. Export includes only models whose outputs are text or images. Unsupported output modalities are skipped and explicitly listed in `skipped_model_ids` in JSON or below the Markdown result; all matched models remain in the lookup. If no matched model is exportable, saving is refused.

Provider documentation remains the primary authority. OpenRouter is a cross-check and may lag a new model. When the development CLI is unavailable, fetch the public catalog directly and filter its `data` list:

```bash
curl -fsS 'https://openrouter.ai/api/v1/models?output_modalities=all'
```

Adding a hosted model remains a change to the hosted plane's own catalog; this tool never publishes models or modifies backend files automatically.
