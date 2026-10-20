# OpenRouter model research

Use `.venv/bin/pipelex-dev openrouter list-models -f <name> --json` from a Pipelex development checkout provisioned with `make install`. Read `ok` and the `models` list in its JSON envelope. `--save` writes disabled draft backend TOML under `generated/`, refuses overwrites and reports the path in `saved_to`.

The command reads `https://openrouter.ai/api/v1/models?output_modalities=all`, including image models, without the old frontend API or remote-config checkout. Authentication is optional; it uses `OPENROUTER_API_KEY` when supplied. If the development CLI is unavailable, fetch the same public endpoint directly and filter its `data` list by model ID or name.

Prices are per token in the response and per million tokens in Pipelex backend files. Missing prices stay unknown. Context length is distinct from the output-token limit in `top_provider.max_completion_tokens`. Explicit `structured_outputs` metadata is evidence of structured-output support; `tools` alone is not. Consult the provider's own documentation for capabilities, reasoning settings, restrictions and current prices before enabling a generated entry.

The full command and export contract is in `docs/contribute/openrouter-model-research.md`.
