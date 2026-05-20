---
title: "Reasoning Controls"
description: "Control LLM reasoning effort and budget across providers — a unified abstraction for chain-of-thought and extended thinking."
---

# Reasoning Controls

Pipelex provides a unified abstraction for controlling LLM reasoning (chain-of-thought / extended thinking) across providers. This page describes how reasoning parameters flow from user configuration through to provider-specific SDK calls.

---

## How to Use Reasoning

There are two ways to enable reasoning on a `PipeLLM` pipe: set `reasoning_effort` (a symbolic level) or `reasoning_budget` (an explicit token count). They are mutually exclusive — see [Mutual Exclusivity](#mutual-exclusivity) for details.

### Inline LLM Setting

Add reasoning directly in the `model` table of a pipe definition:

```toml
[pipe.analyze_contract]
type = "PipeLLM"
model = { model = "claude-4.5-sonnet", temperature = 0.1, reasoning_effort = "high" }
```

### LLM Preset

Define a reusable preset in your LLM deck, then reference it with the `$` prefix:

```toml
# In .pipelex/inference/deck/1_llm_deck.toml
[llm.presets]
deep-analysis = { model = "@default-premium", temperature = 0.1, reasoning_effort = "high" }
```

```toml
# In a .mthds file
[pipe.analyze_contract]
type = "PipeLLM"
model = "$deep-analysis"
```

### Using reasoning_budget

Instead of a symbolic effort level, you can specify an explicit token budget:

```toml
model = { model = "claude-4.5-sonnet", temperature = 0.1, reasoning_budget = 16384 }
```

`reasoning_budget` is supported by Anthropic and Google. OpenAI and Mistral raise `LLMCapabilityError`.

### Model-Specific Examples

Different models use different thinking modes under the hood. Pipelex handles the translation automatically — you always use `reasoning_effort` or `reasoning_budget`.

**Claude 4.6 Opus — adaptive mode**

The provider's SDK dynamically adjusts reasoning depth. `reasoning_effort` controls how aggressively it reasons:

```toml
# Adaptive: the SDK decides how many tokens to spend on reasoning
model = { model = "claude-4.6-opus", temperature = 0.1, reasoning_effort = "high" }
```

You can also override with an explicit budget, which forces `enabled` mode:

```toml
model = { model = "claude-4.6-opus", temperature = 0.1, reasoning_budget = 16384 }
```

**Gemini 2.5 Pro — manual mode**

Effort is translated to a `thinking_budget` token count:

```toml
# Manual: effort "medium" -> thinking_budget = 5000 tokens
model = { model = "gemini-2.5-pro", temperature = 0.3, reasoning_effort = "medium" }
```

**Gemini 3.0 Pro — adaptive mode**

Effort maps to a `ThinkingLevel` enum sent to the Google SDK:

```toml
# Adaptive: effort "high" -> ThinkingLevel.HIGH
model = { model = "gemini-3.0-pro", temperature = 0.3, reasoning_effort = "high" }
```

**GPT-5.2 — manual mode**

Effort maps directly to OpenAI's `reasoning_effort` parameter:

```toml
# Manual: effort "max" -> reasoning_effort = "xhigh" in the SDK call
model = { model = "gpt-5.2", temperature = 0.1, reasoning_effort = "max" }
```

!!! note "Structured Generation"
    Reasoning parameters are not supported for structured generation. See [Structured Generation](#structured-generation) for details.

!!! tip "Test Coverage"
    These examples are exercised in `tests/integration/pipelex/cogt/test_llm_reasoning.py`.

---

## Core Concepts

### ReasoningEffort

The `ReasoningEffort` enum (`pipelex/cogt/llm/llm_job_components.py`) defines the following levels:

| Level | Value | Description |
|-------|-------|-------------|
| `NONE` | `"none"` | Disable reasoning entirely |
| `MINIMAL` | `"minimal"` | Lowest reasoning effort |
| `LOW` | `"low"` | Light reasoning |
| `MEDIUM` | `"medium"` | Moderate reasoning |
| `HIGH` | `"high"` | Heavy reasoning |
| `XHIGH` | `"xhigh"` | Above `HIGH`, below `MAX`; maps to provider-specific xhigh value where supported (e.g. OpenAI) |
| `MAX` | `"max"` | Maximum reasoning budget |

### ThinkingMode

The `ThinkingMode` enum (`pipelex/cogt/llm/thinking_mode.py`) defines how a model handles reasoning at the SDK level:

| Mode | Meaning |
|------|---------|
| `none` | Model does not support reasoning. Attempting to use reasoning params raises `LLMCapabilityError`. |
| `manual` | Pipelex translates effort to a provider-specific value (token budget, effort string, or prompt mode). |
| `adaptive` | The provider's SDK dynamically adjusts reasoning depth. Only Anthropic and Google (Gemini 3) support this today. |

Each model spec in the backend TOML files declares a `thinking_mode`. This is a required field on `InferenceModelSpec` — models without reasoning capabilities set `thinking_mode = "none"` (or inherit it from `[defaults]`).

### Mutual Exclusivity

`reasoning_effort` and `reasoning_budget` are mutually exclusive. Both `LLMSetting` and `LLMJobParams` enforce this via a `model_validator`:

- **`reasoning_effort`** — A symbolic level (`NONE` through `MAX`). Pipelex resolves it to the provider-specific format.
- **`reasoning_budget`** — A raw token count passed directly to providers that accept it (Anthropic, Google). OpenAI and Mistral reject this with `LLMCapabilityError`.

---

## Data Flow

```mermaid
---
config:
  layout: dagre
  theme: base
---
flowchart TB
    A["LLMSetting<br>(MTHDS talent or API)"] -->|make_llm_job_params| B["LLMJobParams<br>reasoning_effort / reasoning_budget"]
    B --> C{Provider Worker}

    C -->|OpenAI Completions| D["_resolve_reasoning_effort()<br>-> effort string"]
    C -->|OpenAI Responses| D2["_resolve_reasoning()<br>-> Reasoning dict"]
    C -->|Anthropic| E["_build_thinking_params()<br>-> _ThinkingParams"]
    C -->|Google| F["_build_thinking_config()<br>-> ThinkingConfig"]
    C -->|Mistral| G["_resolve_prompt_mode()<br>-> prompt_mode"]
    C -->|Bedrock (aioboto3)| H["_validate_no_reasoning_params()<br>-> LLMCapabilityError if set"]
```

---

## Provider Mappings

Each provider has an `effort_to_level_map` configured in its provider subconfig within `pipelex.toml`. These maps translate `ReasoningEffort` values to provider-specific level strings. The special value `"disabled"` means reasoning should be skipped entirely (the accessor returns `None`).

### OpenAI (Completions & Responses)

OpenAI models use `thinking_mode = "manual"` and map `ReasoningEffort` to the `reasoning_effort` parameter via `openai_config.effort_to_level_map`:

```toml
[cogt.llm_config.openai_config.effort_to_level_map]
none = "none"
minimal = "minimal"
low = "low"
medium = "medium"
high = "high"
xhigh = "xhigh"
max = "xhigh"
```

| ReasoningEffort | OpenAI value |
|-----------------|-------------|
| `NONE` | `"none"` |
| `MINIMAL` | `"minimal"` |
| `LOW` | `"low"` |
| `MEDIUM` | `"medium"` |
| `HIGH` | `"high"` |
| `XHIGH` | `"xhigh"` |
| `MAX` | `"xhigh"` |

!!! note
    OpenAI's `"none"` is a valid API value (sent to the SDK), not disabled. This is different from the `"disabled"` convention used by other providers.

OpenAI does not support `reasoning_budget` or `thinking_mode = "adaptive"`. Both raise `LLMCapabilityError`.

When reasoning is active, `temperature` is omitted from the SDK call (OpenAI requires this).

### Anthropic

Anthropic supports both `manual` and `adaptive` thinking modes. The effort mapping is configured via `anthropic_config.effort_to_level_map`:

```toml
[cogt.llm_config.anthropic_config.effort_to_level_map]
none = "disabled"
minimal = "low"
low = "low"
medium = "medium"
high = "high"
xhigh = "xhigh"
max = "max"
```

| ReasoningEffort | Anthropic level |
|-----------------|----------------|
| `NONE` | `None` (thinking disabled) |
| `MINIMAL` | `"low"` |
| `LOW` | `"low"` |
| `MEDIUM` | `"medium"` |
| `HIGH` | `"high"` |
| `XHIGH` | `"xhigh"` |
| `MAX` | `"max"` |

Both modes first check `anthropic_config.effort_to_level_map` to gate reasoning. If the map returns `"disabled"` (e.g., for `NONE` effort), thinking is disabled entirely — no `thinking` parameter is sent to the SDK.

**ADAPTIVE mode** uses `{"type": "adaptive"}` with an `OutputConfigParam(effort=...)` where the effort value comes from the level map.

**MANUAL mode** resolves effort to a token budget via the `effort_to_budget_maps` config (keyed by `prompting_target`), then sends `{"type": "enabled", "budget_tokens": N}`. The budget is capped to `min(budget, max_tokens - 1)` to satisfy Anthropic's API constraint.

**`reasoning_budget`** (explicit) always uses `{"type": "enabled", "budget_tokens": N}` regardless of thinking mode. The same `min(budget, max_tokens - 1)` cap is applied.

!!! note
    `MINIMAL` and `LOW` both map to `"low"` in the level map. In ADAPTIVE mode they produce identical behavior. In MANUAL mode they are differentiated by the budget map (512 vs 1024 tokens). This matches the granularity that each mode supports.

When thinking is active, `temperature` is suppressed (Anthropic requires `temperature=1` or omission with thinking).

### Google Gemini

Google models use either `thinking_mode = "manual"` (Gemini 2.5 series) or `thinking_mode = "adaptive"` (Gemini 3 series). Both modes use `google_config.effort_to_level_map` as a gate:

```toml
[cogt.llm_config.google_config.effort_to_level_map]
none = "disabled"
minimal = "low"
low = "low"
medium = "medium"
high = "high"
xhigh = "high"
max = "high"
```

If the level map returns `"disabled"` (e.g., for `NONE` effort), thinking is disabled with `thinking_budget=0` regardless of mode.

!!! note
    `MAX` maps to `"high"` because Google's `ThinkingLevel` enum tops out at `HIGH` — there is no higher level.

**ADAPTIVE mode** (Gemini 3) sends a `thinking_level` value (e.g., `ThinkingLevel.LOW`, `ThinkingLevel.MEDIUM`, `ThinkingLevel.HIGH`) mapped from the `effort_to_level_map`. The Google SDK dynamically adjusts reasoning depth based on this level. No `thinking_budget` is set in adaptive mode.

!!! note
    `MINIMAL` and `LOW` both map to `"low"` in the level map. In ADAPTIVE mode they both produce `ThinkingLevel.LOW`. In MANUAL mode they are differentiated by the budget map (512 vs 1024 tokens).

**MANUAL mode** (Gemini 2.5) resolves effort to a `thinking_budget` (token count) via the `effort_to_budget_maps` config:

| ReasoningEffort | thinking_budget |
|-----------------|----------------|
| `NONE` | `0` (disabled via level map) |
| `MINIMAL` | `512` |
| `LOW` | `1024` |
| `MEDIUM` | `5000` |
| `HIGH` | `16384` |
| `XHIGH` | `32768` |
| `MAX` | `65536` |

**`reasoning_budget`** (explicit) passes through directly as `thinking_budget`. When `max_tokens` is known, the budget is capped to `min(budget, max_tokens - 1)`.

!!! note
    An explicit `reasoning_budget` always produces a `thinking_budget`-based config, even when the model uses `thinking_mode = "adaptive"`. This overrides the `thinking_level` approach that adaptive mode normally uses.

Temperature is passed normally to the Google API regardless of reasoning mode.

!!! note "VertexAI Backend"
    Reasoning controls are not implemented for Gemini models on the VertexAI backend because Google favors the newer Gen-AI SDK. The VertexAI backend uses `sdk = "openai"` (the OpenAI-compatible endpoint), which routes through the OpenAI worker and does not expose Google's native thinking controls (`thinking_budget` / `thinking_level`). For Gemini reasoning support, use the `google` backend with the native Gen-AI SDK. Or better yet, use the Pipelex Gateway.

### Mistral

Mistral models use `thinking_mode = "manual"`. The effort mapping is configured via `mistral_config.effort_to_level_map`:

```toml
[cogt.llm_config.mistral_config.effort_to_level_map]
none = "disabled"
minimal = "reasoning"
low = "reasoning"
medium = "reasoning"
high = "reasoning"
xhigh = "reasoning"
max = "reasoning"
```

| ReasoningEffort | Mistral behavior |
|-----------------|-----------------|
| `NONE` | `prompt_mode` omitted (no reasoning) |
| `MINIMAL` through `MAX` | `prompt_mode = "reasoning"` |

Mistral does not support `reasoning_budget` or `thinking_mode = "adaptive"`. Both raise `LLMCapabilityError`.

Temperature is passed normally to the Mistral API regardless of reasoning mode.

### Bedrock (aioboto3 native models)

Bedrock native models using the `bedrock_aioboto3` SDK do not support reasoning parameters. Any `reasoning_effort` or `reasoning_budget` raises `LLMCapabilityError`.

!!! note
    Claude models accessed through Bedrock use the `bedrock_anthropic` SDK variant and go through the Anthropic worker, which does support reasoning.

### Gateway and Proxy Backends

Gateway and proxy backends (Azure OpenAI, Portkey, BlackBoxAI, Pipelex Gateway) route API calls through an intermediary but use the same provider worker classes as direct backends. Their reasoning capabilities depend on the `sdk` field in each model's backend TOML, which determines which worker handles the request.

- **Azure OpenAI** uses `sdk = "azure_openai_responses"`, routing through the OpenAI Responses worker. Reasoning models declare `thinking_mode = "manual"` and use OpenAI-style `reasoning_effort`.
- **Portkey** uses `portkey_completions` or `portkey_responses` SDKs, both routing through OpenAI workers. All models — including Anthropic and Google models proxied via Portkey — follow OpenAI reasoning semantics.
- **BlackBoxAI** uses `sdk = "openai"` or `"openai_responses"`. Proxied models follow OpenAI reasoning semantics.

!!! note
    When a provider's models are accessed through a gateway using an OpenAI-compatible SDK, the reasoning controls follow OpenAI semantics (`reasoning_effort`) rather than the provider's native semantics. For native reasoning controls (e.g., Anthropic thinking budgets, Google thinking levels), use the direct provider backend.

---

## Effort-to-Level Configuration

Each provider has an `effort_to_level_map` in its subconfig within `pipelex.toml` that maps `ReasoningEffort` values to provider-specific level strings. Every `ReasoningEffort` key must be present in each map (enforced by a validator).

The special value `"disabled"` causes the accessor to return `None`, signaling that reasoning should be skipped. OpenAI uses `"none"` as a valid API value instead (not `"disabled"`).

The level is resolved at runtime via `<ProviderConfig>.get_reasoning_level()` in each plugin's config module (e.g., `pipelex/plugins/openai/openai_config.py`). Each config class returns the provider's native SDK type.

## Effort-to-Budget Configuration

For providers that use token budgets (Anthropic MANUAL, Google MANUAL), `ReasoningEffort` is resolved to a token count via the `effort_to_budget_maps` in `pipelex.toml`:

```toml
[cogt.llm_config.effort_to_budget_maps.anthropic]
none = 0
minimal = 512
low = 1024
medium = 5000
high = 16384
xhigh = 32768
max = 65536

[cogt.llm_config.effort_to_budget_maps.gemini]
none = 0
minimal = 512
low = 1024
medium = 5000
high = 16384
xhigh = 32768
max = 65536
```

The map is keyed by `prompting_target` (from the model spec). A validated mapping must contain entries for all `ReasoningEffort` values (including `none`, even though it is unreachable at runtime — the level map gates `NONE` as disabled before the budget lookup).

The budget is resolved at runtime via `LLMConfig.get_reasoning_budget()` (`pipelex/cogt/config_cogt.py`).

---

## Backend TOML Configuration

Each model declares its reasoning capability via `thinking_mode` in the backend TOML:

```toml
# Model that supports reasoning
[claude-4-sonnet]
thinking_mode = "manual"

# Model with adaptive reasoning
["claude-4.6-opus"]
thinking_mode = "adaptive"

# Google Gemini 3 with adaptive reasoning
["gemini-3.0-pro"]
thinking_mode = "adaptive"

# Model without reasoning (or inherited from defaults)
[gpt-4o-mini]
thinking_mode = "none"
```

Backends that have no reasoning-capable models set a default:

```toml
[defaults]
thinking_mode = "none"
```

---

## Structured Generation

Reasoning parameters (`reasoning_effort` and `reasoning_budget`) are not supported for structured generation (`_gen_object`). If either parameter is set when calling structured generation, an `LLMCapabilityError` is raised with the message "does not support reasoning parameters for structured generation".

This applies to all providers (OpenAI, Anthropic, Google, Mistral). Bedrock native models already reject all reasoning parameters before reaching `_gen_object`.

## NONE Semantics

The behavior of `ReasoningEffort.NONE` varies by provider:

- **OpenAI**: Sends `reasoning_effort="none"` to the API, which is a valid API value that minimizes reasoning.
- **Anthropic**: Disabled via `effort_to_level_map` gate — no `thinking` parameter is sent.
- **Google**: Disabled via `effort_to_level_map` gate, sets `thinking_budget=0`.
- **Mistral**: Omits `prompt_mode` (no reasoning).

---

## Error Handling

All reasoning-related errors use `LLMCapabilityError` (`pipelex/cogt/exceptions.py`):

| Scenario | Error |
|----------|-------|
| `reasoning_effort` on a `thinking_mode = "none"` model | "does not support reasoning" |
| `reasoning_budget` on a provider that doesn't support it | "does not support reasoning_budget" |
| `thinking_mode = "adaptive"` on OpenAI or Mistral | "adaptive ... not supported" |
| Any reasoning param on Bedrock (aioboto3) models | "does not support reasoning parameters" |
| Reasoning params during structured generation | "does not support reasoning parameters for structured generation" |
| Both `reasoning_effort` and `reasoning_budget` set | `ValueError` / `LLMSettingValueError` (mutual exclusivity) |

---

## File Reference

| File | Purpose |
|------|---------|
| `pipelex/cogt/llm/llm_job_components.py` | `ReasoningEffort` enum, `LLMJobParams` with mutual exclusivity validator |
| `pipelex/cogt/llm/thinking_mode.py` | `ThinkingMode` enum |
| `pipelex/cogt/llm/reasoning_config_base.py` | Shared helpers: `EffortToLevelMap`, `validate_effort_to_level_map()`, `get_reasoning_level_str()` |
| `pipelex/cogt/llm/llm_setting.py` | `LLMSetting` with reasoning fields and `make_llm_job_params()` |
| `pipelex/cogt/config_cogt.py` | `LLMConfig` with `get_reasoning_budget()` and effort-to-budget map validation |
| `pipelex/plugins/openai/openai_config.py` | `OpenAIConfig` with `get_reasoning_level()` returning `ChatCompletionReasoningEffort \| None` |
| `pipelex/plugins/anthropic/anthropic_config.py` | `AnthropicConfig` with `get_reasoning_level()` returning `AnthropicEffortLevel \| None` |
| `pipelex/plugins/google/google_config.py` | `GoogleConfig` with `get_reasoning_level()` returning `genai_types.ThinkingLevel \| None` |
| `pipelex/plugins/mistral/mistral_config.py` | `MistralConfig` with `get_reasoning_level()` returning `MistralPromptMode \| None` |
| `pipelex/cogt/model_backends/model_spec.py` | `InferenceModelSpec.thinking_mode` field |
| `pipelex/plugins/openai/openai_completions_llm_worker.py` | OpenAI Completions reasoning resolution |
| `pipelex/plugins/openai/openai_responses_llm_worker.py` | OpenAI Responses reasoning resolution |
| `pipelex/plugins/anthropic/anthropic_llm_worker.py` | Anthropic thinking params builder |
| `pipelex/plugins/google/google_llm_worker.py` | Google thinking config builder |
| `pipelex/plugins/mistral/mistral_llm_worker.py` | Mistral prompt mode resolution |
| `pipelex/plugins/bedrock/bedrock_llm_worker.py` | Bedrock reasoning validation |
| `pipelex/pipelex.toml` | Default effort-to-budget maps and effort-to-level maps |

---

## Next Steps

- [Architecture Overview](./architecture-overview.md) — Understand the two-layer design
- [Test Profile Configuration](./test-profile-configuration.md) — Configure model sets for testing
