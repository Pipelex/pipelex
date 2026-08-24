---
title: "Test Profile Configuration"
description: "Configure test profiles to control which AI models run in parametrized tests — iterate fast with small sets, then test comprehensively."
---

# Test Profile Configuration

Pipelex uses a flexible test profile system to control which AI models are included in parametrized tests. This allows developers to quickly iterate with a small set of models during development, while still being able to run comprehensive tests across all available models.

---

## Overview

The test profile system consists of:

1. **Profile definitions** in `.pipelex-dev/test_profiles.toml`
2. **Model collections** organized by provider/type
3. **A preprocessing command** that generates fixture files
4. **Make targets** for easy regeneration

---

## Quick Start

```bash
# Regenerate test fixtures with default (dev) profile
make regenerate-test-models

# Regenerate with a specific profile
make regenerate-test-models TEST_PROFILE=full
make regenerate-test-models TEST_PROFILE=coverage
make regenerate-test-models TEST_PROFILE=ci
```

---

## Profile Configuration File

The configuration lives in `.pipelex-dev/test_profiles.toml`:

```toml
################################################################################
# Collections - Reusable lists of models/backends
################################################################################

[collections.backends]
all = ["pipelex_gateway", "anthropic", "openai", "google", ...]

[collections.llm]
anthropic = ["claude-3-haiku", "claude-4-opus", "claude-4.5-sonnet", ...]
openai = ["gpt-4o-mini", "gpt-4o", "gpt-5", ...]
google = ["gemini-2.5-flash", "gemini-2.5-pro", ...]

[collections.img_gen]
openai = ["gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"]
fal = ["flux-pro", "flux-2", "flux-2-pro"]

[collections.extract]
from_pdf = ["pypdfium2-extract-pdf", "docling-extract-text", "mistral-ocr", ...]
from_image = ["docling-extract-text", "mistral-ocr", "deepseek-ocr", ...]

################################################################################
# Profiles
################################################################################

[profiles.dev]
description = "Quick dev testing with fast and cheap models"
backends = ["pipelex_gateway", "internal"]
llm_models = ["claude-4.5-haiku", "gpt-4o-mini", "gemini-2.5-flash-lite"]
img_gen_models = ["gpt-image-1-mini"]
extract_models = ["@from_pdf"]

[profiles.full]
description = "All available models"
include_all = true
```

---

## Model List Syntax

The profile system supports several powerful syntax options for specifying models:

| Syntax | Description | Example |
|--------|-------------|---------|
| `"model-name"` | Specific model (direct reference) | `"gpt-4o-mini"` |
| `@collection` | All models from a named collection | `"@anthropic"`, `"@from_pdf"` |
| `backend:*` | All models from a specific backend | `"openai:*"` |
| `pattern*` | Glob pattern matching | `"claude-4*"`, `"gpt-*"` |
| `*` | All available models | `"*"` |
| `!pattern` | Exclude models matching pattern | `"!*-codex"` |

### Examples

```toml
# Use all Anthropic models from the collection
llm_models = ["@anthropic"]

# Use all Claude 4.5 models (glob pattern)
llm_models = ["claude-4.5-*"]

# Use all GPT models except codex variants
llm_models = ["gpt-*", "!*-codex", "!*-codex-*"]

# Combine collection reference with specific models
llm_models = ["@anthropic", "gpt-4o-mini", "gemini-2.5-flash"]

# Use all models from the openai backend
llm_models = ["openai:*"]

# Use all backends
backends = ["@all"]
```

---

## Built-in Profiles

### `dev` (default)

Quick development testing with fast, cheap models from key providers.

```toml
[profiles.dev]
backends = ["pipelex_gateway", "internal"]
llm_models = ["claude-4.5-haiku", "gpt-4o-mini", "gemini-2.5-flash-lite"]
img_gen_models = ["gpt-image-1-mini"]
extract_models = ["@from_pdf"]
```

### `ci`

Minimal set for CI pipelines - no actual inference.

```toml
[profiles.ci]
backends = ["azure_openai"]
llm_models = ["gpt-4o-mini"]
img_gen_models = []
extract_models = []
```

### `coverage`

One model per backend for coverage testing.

```toml
[profiles.coverage]
backends = ["anthropic", "openai", "google", "mistral", "internal"]
llm_models = ["claude-4.5-haiku", "gpt-4o-mini", "gemini-2.5-flash-lite", "mistral-large"]
img_gen_models = ["gpt-image-1", "nano-banana"]
extract_models = ["pypdfium2-extract-pdf"]
```

### `full`

All available models from all backends.

```toml
[profiles.full]
include_all = true
```

### `all_backends`

Test select models across all backends.

```toml
[profiles.all_backends]
backends = ["@all"]
llm_models = ["claude-4.5-haiku", "gpt-4o-mini", "gemini-2.5-flash-lite"]
img_gen_models = ["gpt-image-1-mini"]
extract_models = ["@from_pdf"]
```

---

## How It Works

### 1. Model Discovery

The preprocessing command discovers available models from:

- **Backend TOML files** in `inference/backends/*.toml`, resolved from the project `.pipelex/` directory if present there, otherwise from the global `~/.pipelex/` directory
- **Pipelex Gateway** remote configuration

### 2. Profile Resolution

When you run `make regenerate-test-models TEST_PROFILE=dev`:

1. Collections are loaded from `[collections.*]` sections
2. The specified profile is loaded from `[profiles.dev]`
3. Model specifiers are resolved:
    - `@collection_name` expands to the collection's models
    - `backend:*` expands to all models from that backend
    - Glob patterns (`claude-*`) are matched against known models
    - Exclusions (`!pattern`) are removed
4. Results are filtered by allowed backends

### 3. Fixture Generation

The resolved model/backend pairs are written to:

```
tests/integration/pipelex/fixtures/_generated_model_sets.py
```

This file contains:

```python
from tests.integration.pipelex.fixtures.model_combo import ModelCombo

LLM_COMBOS: list[ModelCombo] = [
    ModelCombo("claude-4.5-haiku", "pipelex_gateway"),
    ModelCombo("gemini-2.5-flash-lite", "pipelex_gateway"),
    ModelCombo("gpt-4o-mini", "pipelex_gateway"),
]

IMG_GEN_COMBOS: list[ModelCombo] = [...]
EXTRACT_COMBOS: list[ModelCombo] = [...]
SEARCH_COMBOS: list[ModelCombo] = [...]
```

---

## CLI Command

For more control, use the CLI directly:

```bash
# Preview what would be generated
pipelex-dev preprocess-test-models --profile dev

# Generate fixtures
pipelex-dev preprocess-test-models --generate-fixtures --profile dev

# Output full availability JSON
pipelex-dev preprocess-test-models --output-json --profile full

# Quiet mode (minimal output)
pipelex-dev preprocess-test-models --generate-fixtures --profile dev --quiet
```

---

## Adding a New Profile

1. Add your profile to `.pipelex-dev/test_profiles.toml`:

    ```toml
    [profiles.my_profile]
    description = "My custom profile for X testing"
    backends = ["anthropic", "openai"]
    llm_models = ["claude-4.5-*", "gpt-4o-mini"]
    img_gen_models = []
    extract_models = []
    ```

2. Regenerate fixtures:

    ```bash
    make regenerate-test-models TEST_PROFILE=my_profile
    ```

---

## Adding Models to Collections

When new models become available, add them to the appropriate collection:

```toml
[collections.llm]
# Add new model to existing manufacturer collection
anthropic = [
    "claude-3-haiku",
    "claude-4.5-sonnet",
    "claude-5-opus",  # New model
]
```

Collections serve as documentation of available models and can be referenced in any profile.

---

## Local Overrides

For personal customizations that shouldn't be committed to the repository, create a `.pipelex-dev/test_profiles_override.toml` file. This file is gitignored and will be deep-merged on top of the base configuration.

This is useful for:

- Testing with specific models not in standard profiles
- Creating personal profiles tailored to your development workflow
- Temporarily modifying collections without affecting the team

### Example Override File

```toml
# .pipelex-dev/test_profiles_override.toml

# Add a personal profile
[profiles.my_local]
description = "My local testing profile"
backends = ["pipelex_gateway"]
llm_models = ["claude-4.5-sonnet", "gpt-4o"]
img_gen_models = []
extract_models = []

# Override an existing profile
[profiles.dev]
llm_models = ["claude-4.5-opus"]  # I prefer testing with opus locally

# Extend a collection
[collections.llm]
my_favorites = ["claude-4.5-sonnet", "gpt-4o", "gemini-2.5-pro"]
```

After creating or modifying your override file, regenerate fixtures:

```bash
make regenerate-test-models TEST_PROFILE=my_local
```

!!! tip "Team Collaboration"
    Since the override file is gitignored, each developer can maintain their own testing preferences without conflicts. The base `.pipelex-dev/test_profiles.toml` remains the shared source of truth for CI and team workflows.

---

## Best Practices

1. **Use `dev` profile during development** - Fast iteration with minimal API calls
2. **Use `coverage` profile for PR testing** - Ensures all backends work
3. **Use `full` profile sparingly** - Only when testing model-specific behavior
4. **Use glob patterns for model families** - `claude-4.5-*` catches all 4.5 variants

---

## Troubleshooting

### No models in profile

If a profile shows 0 models, check:

1. The specified models exist in the backend configurations
2. The backends list includes backends that have those models
3. Collection names are spelled correctly (case-sensitive)

### Empty list vs missing key

- `llm_models = []` - No LLM models included
- Key not present - All LLM models from allowed backends included

### Glob patterns not matching

Glob patterns use `fnmatch` syntax:

- `*` matches any characters
- `?` matches single character
- Patterns are case-sensitive
