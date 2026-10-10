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
deep-analysis = { model = "@default-premium", temperature = 1, reasoning_effort = "high" }
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

**Gemini 3.1 Pro — adaptive mode**

Effort maps to a `ThinkingLevel` enum sent to the Google SDK:

```toml
# Adaptive: effort "high" -> ThinkingLevel.HIGH
model = { model = "gemini-3.1-pro", temperature = 0.3, reasoning_effort = "high" }
```

**GPT-5.4 — manual mode**

Effort maps directly to OpenAI's `reasoning_effort` parameter:

```toml
# Manual: effort "max" -> reasoning_effort = "xhigh" in the SDK call
model = { model = "gpt-5.4", temperature = 0.1, reasoning_effort = "max" }
```

!!! note "Structured Generation"
    Reasoning parameters apply to structured outputs as they do to text. See [Structured Generation](#structured-generation) for how each provider carries them.

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
| `manual` | Pipelex translates effort to a provider-specific value (a token budget or an effort string). |
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
    C -->|Mistral| G["_resolve_reasoning_effort()<br>-> reasoning_effort"]
    C -->|Bedrock (aiobotocore)| H["check_request()<br>-> LLMCapabilityError if set"]
```

---

## Provider Mappings

Each provider has an `effort_to_level_map` configured in its provider subconfig within `pipelex.toml`. These maps translate `ReasoningEffort` values to provider-specific level strings. The special value `"disabled"` means reasoning should be skipped entirely (the accessor returns `None`).

### OpenAI (Completions & Responses)

OpenAI models use `thinking_mode = "manual"` and map `ReasoningEffort` to the `reasoning_effort` parameter via `inference.llm.openai.effort_to_level_map`:

```toml
[inference.llm.openai.effort_to_level_map]
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

Anthropic supports both `manual` and `adaptive` thinking modes. The effort mapping is configured via `inference.llm.anthropic.effort_to_level_map`:

```toml
[inference.llm.anthropic.effort_to_level_map]
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

Both modes first check `inference.llm.anthropic.effort_to_level_map` to gate reasoning. If the map returns `"disabled"` (e.g., for `NONE` effort), thinking is disabled entirely — no `thinking` parameter is sent to the SDK.

**ADAPTIVE mode** uses `{"type": "adaptive"}` with an `OutputConfigParam(effort=...)` where the effort value comes from the level map.

**MANUAL mode** resolves effort to a token budget via the `effort_to_budget_maps` config (keyed by the worker-owned reasoning family — `"anthropic"` for the Anthropic worker), then sends `{"type": "enabled", "budget_tokens": N}`. The budget is fitted inside `max_tokens` as described in [Fitting a Budget Inside max_tokens](#fitting-a-budget-inside-max_tokens): a quarter of `max_tokens` is kept for the answer, and a budget below Anthropic's minimum of 1,024 tokens, which the kit's Anthropic models declare as their `min_thinking_budget`, is raised to it.

**`reasoning_budget`** (explicit) uses `{"type": "enabled", "budget_tokens": N}` on a manual-mode model, fitted the same way. An adaptive-mode model refuses an explicit budget with `LLMCapabilityError`, since adaptive thinking takes an effort.

!!! note
    `MINIMAL` and `LOW` both map to `"low"` in the level map. In ADAPTIVE mode they produce identical behavior. In MANUAL mode the budget map gives `MINIMAL` 512 tokens, which the 1,024 minimum raises to the budget `LOW` has, so they also behave alike there.

When thinking is active, `temperature` is suppressed (Anthropic requires `temperature=1` or omission with thinking).

### Google Gemini

Google models use either `thinking_mode = "manual"` (Gemini 2.5 series) or `thinking_mode = "adaptive"` (Gemini 3 series). Both modes use `inference.llm.google.effort_to_level_map` as a gate:

```toml
[inference.llm.google.effort_to_level_map]
none = "disabled"
minimal = "minimal"
low = "low"
medium = "medium"
high = "high"
xhigh = "high"
max = "high"
```

If the level map returns `"disabled"` (e.g., for `NONE` effort), thinking is disabled with `thinking_budget=0` regardless of mode. Some Gemini models always think and refuse a budget of 0 with a 400 error, among them Gemini 2.5 Pro and 3.1 Pro: such a model lists the `thinking_cannot_be_disabled` constraint in its backend file, and `NONE` on it is refused with an `LLMCapabilityError` before the call is sent.

!!! note
    `MAX` maps to `"high"` because Google's `ThinkingLevel` enum tops out at `HIGH` — there is no higher level.

**ADAPTIVE mode** (Gemini 3) sends a `thinking_level` value (e.g., `ThinkingLevel.LOW`, `ThinkingLevel.MEDIUM`, `ThinkingLevel.HIGH`) mapped from the `effort_to_level_map`. The Google SDK dynamically adjusts reasoning depth based on this level. No `thinking_budget` is set in adaptive mode.

!!! note
    `MINIMAL` and `LOW` map to distinct levels in the level map (`"minimal"` and `"low"`). In ADAPTIVE mode they produce different results — `ThinkingLevel.MINIMAL` vs `ThinkingLevel.LOW`. In MANUAL mode they are further differentiated by the budget map (512 vs 1024 tokens).

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

**`reasoning_budget`** (explicit) is sent as `thinking_budget`, fitted as described in [Fitting a Budget Inside max_tokens](#fitting-a-budget-inside-max_tokens): a quarter of `max_tokens` is kept for the answer when the request sets one, and the budget is held within the range the model accepts, which each Gemini 2.5 model declares in its spec (`gemini-2.5-pro` takes 128 to 32,768, `gemini-2.5-flash` at most 24,576 and `gemini-2.5-flash-lite` 512 to 24,576). The same fitting applies to a budget resolved from an effort, so `MAX` effort's 65,536 tokens are cut to the model's maximum even when no `max_tokens` is set.

!!! note
    An explicit `reasoning_budget` always produces a `thinking_budget`-based config, even when the model uses `thinking_mode = "adaptive"`. This overrides the `thinking_level` approach that adaptive mode normally uses.

Temperature is passed normally to the Google API regardless of reasoning mode.

!!! note "VertexAI Backend"
    Reasoning controls are not implemented for Gemini models on the VertexAI backend because Google favors the newer Gen-AI SDK. The VertexAI backend uses `sdk = "openai"` (the OpenAI-compatible endpoint), which routes through the OpenAI worker and does not expose Google's native thinking controls (`thinking_budget` / `thinking_level`). For Gemini reasoning support, use the `google` backend with the native Gen-AI SDK.

### Mistral

Mistral models use `thinking_mode = "manual"`. The effort mapping is configured via `inference.llm.mistral.effort_to_level_map`:

```toml
[inference.llm.mistral.effort_to_level_map]
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
| `NONE` | `reasoning_effort` omitted (no reasoning) |
| `MINIMAL` through `MAX` | `reasoning_effort = "high"` |

Mistral's reasoning models have one reasoning setting, on or off: their `reasoning_effort` parameter accepts only `"none"` and `"high"`, so the `reasoning` level turns reasoning on as `reasoning_effort = "high"`. The older `prompt_mode = "reasoning"` parameter is refused by every current Mistral model.

Mistral does not support `reasoning_budget` or `thinking_mode = "adaptive"`. Both raise `LLMCapabilityError`.

Temperature is passed normally to the Mistral API regardless of reasoning mode.

### Bedrock (aiobotocore native models)

Bedrock native models using the `bedrock_aioboto` SDK do not support reasoning parameters. Any `reasoning_effort` or `reasoning_budget` raises `LLMCapabilityError`.

!!! note
    Claude models accessed through Bedrock use the `bedrock_anthropic` SDK variant and go through the Anthropic worker, which does support reasoning.

### Gateway and Proxy Backends

Gateway and proxy backends (Azure OpenAI, Portkey, BlackBoxAI, OpenRouter) route API calls through an intermediary but use the same provider worker classes as direct backends. Their reasoning capabilities depend on the `sdk` field in each model's backend TOML, which determines which worker handles the request.

- **Azure OpenAI** uses `sdk = "azure_openai_responses"`, routing through the OpenAI Responses worker. Reasoning models declare `thinking_mode = "manual"` and use OpenAI-style `reasoning_effort`.
- **Portkey** uses `portkey_completions` or `portkey_responses` SDKs, both routing through OpenAI workers. All models — including Anthropic and Google models proxied via Portkey — follow OpenAI reasoning semantics.
- **BlackBoxAI** uses `sdk = "openai"` or `"openai_responses"`. Proxied models follow OpenAI reasoning semantics.
- **OpenRouter** uses `sdk = "openai"` for its language models, which declare `thinking_mode = "none"`, so the kit's OpenRouter models take no reasoning controls.

Whether a server behind the OpenAI chat-completions SDK accepts a reasoning effort beside the function tool a structured output uses is that server's decision; see [Structured Generation](#structured-generation).

!!! note
    When a provider's models are accessed through a gateway using an OpenAI-compatible SDK, the reasoning controls follow OpenAI semantics (`reasoning_effort`) rather than the provider's native semantics. For native reasoning controls (e.g., Anthropic thinking budgets, Google thinking levels), use the direct provider backend.

---

## Effort-to-Level Configuration

Each provider has an `effort_to_level_map` in its subconfig within `pipelex.toml` that maps `ReasoningEffort` values to provider-specific level strings. Every `ReasoningEffort` key must be present in each map (enforced by a validator).

The special value `"disabled"` causes the accessor to return `None`, signaling that reasoning should be skipped. OpenAI uses `"none"` as a valid API value instead (not `"disabled"`).

The level is resolved at runtime via `<ProviderConfig>.get_reasoning_level()` in each plugin's config module (e.g., `pipelex/providers/openai/openai_config.py`). Each config class returns the provider's native SDK type.

## Effort-to-Budget Configuration

For providers that use token budgets (Anthropic MANUAL, Google MANUAL), `ReasoningEffort` is resolved to a token count via the `effort_to_budget_maps` in `pipelex.toml`:

```toml
[inference.llm.effort_to_budget_maps.anthropic]
none = 0
minimal = 512
low = 1024
medium = 5000
high = 16384
xhigh = 32768
max = 65536

[inference.llm.effort_to_budget_maps.gemini]
none = 0
minimal = 512
low = 1024
medium = 5000
high = 16384
xhigh = 32768
max = 65536
```

The map is keyed by the reasoning family each worker owns (`reasoning_budget_family`, a class attribute: `"anthropic"` on the Anthropic worker, `"gemini"` on the Google worker) — the model spec plays no part in the lookup. A validated mapping must contain entries for all `ReasoningEffort` values (including `none`, even though it is unreachable at runtime — the level map gates `NONE` as disabled before the budget lookup).

The budget is resolved at runtime via `LLMConfig.get_reasoning_budget()` (`pipelex/cogt/config_cogt.py`).

### Fitting a Budget Inside max_tokens

Anthropic and Gemini count the thinking budget against `max_tokens`, so a budget that fills it leaves the answer, a tool call on a structured output, nothing to be written in. Every manual budget, resolved from an effort or set explicitly, is therefore fitted by `fit_thinking_budget()` (`pipelex/cogt/llm/thinking_budget.py`) before it is sent:

- The budget is held within the range the provider accepts for the model, which the model's spec declares as two valued constraints, `min_thinking_budget` and `max_thinking_budget`, both inclusive and both optional. The kit's Anthropic models declare Anthropic's minimum of 1,024, and its Gemini 2.5 models declare their ranges. A server reached through the `anthropic` SDK that is not Anthropic, such as MiniMax, declares no minimum and gets none.
- When the request sets `max_tokens`, a quarter of it, and never less than one token, is reserved for the answer, so the budget is cut to at most `max_tokens` minus that reserve.
- When `max_tokens` cannot hold the model's minimum beside the reserve, or a single thinking token for a model that declares no minimum, the call is refused with an `LLMCapabilityError` naming `max_tokens`, the reserve and the minimum, rather than sent to fail at the provider.

On the Anthropic structured path, `max_tokens` is first capped by the number of tokens the structured-output timeout (`inference.llm.anthropic.structured_output_timeout_seconds`) leaves time to generate, so a `MAX` effort's budget is fitted inside that cap rather than inside the model's own output limit.

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
["gemini-3.1-pro"]
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

Reasoning parameters apply to structured generation (`_gen_object`) exactly as they do to text: each worker resolves them with the same helper its text path uses, so a model refuses on a structured output only what it refuses on text, with the same message. A pipe whose model setting carries a reasoning effort, a deck preset such as `$deep-analysis` included, generates its structured output with that effort when it names no `model_to_structure`.

How each provider carries the setting beside its structuring path:

- **OpenAI Responses** (`openai_responses`, `azure_openai_responses`, `portkey_responses` and the hosted gateway) sends `reasoning={"effort": …}` beside the function tool and drops `temperature`, as on text.
- **OpenAI chat completions** sends `reasoning_effort` beside the tool or JSON schema and drops `temperature`. Whether the server accepts a reasoning effort beside a function tool is its own decision: OpenAI's own chat-completions endpoint refuses it on GPT-5 models ("Function tools with reasoning_effort are not supported"), and accepts it with the `instructor/json_schema` structure method or on the Responses SDK, which every OpenAI model in the kit uses. Gemini's OpenAI-compatible endpoint accepts it beside a function tool.
- **Anthropic** sends `thinking` (and `output_config` for adaptive models). On the tool structure methods it leaves the tool choice to the model whenever thinking is on, with parallel tool use disabled and a system line steering it to the tool call. A forced tool choice cannot carry thinking: Anthropic refuses it beside manual thinking, and under adaptive thinking it accepts it and the model silently does not think. The same request is what `instructor/anthropic_reasoning_tools` sends without thinking, for a model that refuses a forced choice outright. `instructor/anthropic_json` defines no tool, so its request carries thinking and nothing about a tool choice.
- **Google** passes the same `ThinkingConfig` as on text, under both `instructor/genai_structured_outputs` and `instructor/genai_tools`.
- **Mistral** sends `reasoning_effort` beside its tool call, as on text. A reasoning reply carries its answer in a list of content chunks beside the thinking, which instructor's JSON parsers cannot read, so a model whose structure method is `instructor/mistral_structured_outputs` refuses a reasoning setting on a structured output with an `LLMCapabilityError` naming `instructor/mistral_tools`.

Bedrock native models (`bedrock_aioboto`) refuse every reasoning parameter on text, and have no structured path at all: their worker refuses every structured output.

Reasoning spends the same output budget as the answer, so a structured output on a high effort needs room for both; see [Fitting a Budget Inside max_tokens](#fitting-a-budget-inside-max_tokens) for the budget-based providers.

## NONE Semantics

The behavior of `ReasoningEffort.NONE` varies by provider:

- **OpenAI**: Sends `reasoning_effort="none"` to the API, which is a valid API value that minimizes reasoning.
- **Anthropic**: Disabled via `effort_to_level_map` gate — no `thinking` parameter is sent.
- **Google**: Disabled via `effort_to_level_map` gate, sets `thinking_budget=0`.
- **Mistral**: Omits `reasoning_effort` (no reasoning).

---

## Checked When the Method Loads

Every refusal below is raised by a worker's `check_request` classmethod, which reads only the model's spec and the job params and builds no SDK client. The worker runs it before every call, on text and structured outputs alike, and bundle validation runs the same check: when a method loads, each `PipeLLM` and `PipeStructure` resolves the setting its output is generated with (`model` for a single text, or a single `Dynamic` output, which a run generates as text unless its caller names another concept; `model_to_structure`, else `model`, else the deck's override or default for structured outputs, for anything else, a declared list of any concept included) to the model the deck serves, applies the model's constraints to the job params as the worker does, and calls the check its backend registered beside its worker factory. A refusal is an `llm_setting_refused_by_model` validation error on the field holding the setting, naming the pipe, the setting and the worker's reason, with the model named by its deck handle and never by its SDK or backend (an external plugin's refusal is shown as written only when the plugin raised it as caller-facing copy, and by its title otherwise), so `pipelex validate`, the API's validate route and a run all refuse the method before any credit is spent, where it used to validate as runnable and fail at the first call. A model no backend serves on the boot, or whose backend's SDK is not installed, is left to the run. A backend that registers no check, an external plugin's for instance, is held to the rule every worker shares: a model whose spec declares `thinking_mode = "none"` takes no reasoning setting.

## Error Handling

All reasoning-related errors use `LLMCapabilityError` (`pipelex/cogt/exceptions.py`), raised by the worker's `check_request` before the call and, when the method loads, reported as an `llm_setting_refused_by_model` validation error:

| Scenario | Error |
|----------|-------|
| `reasoning_effort` on a `thinking_mode = "none"` model | "does not support reasoning" |
| `reasoning_budget` on a provider that doesn't support it | "does not support reasoning_budget" |
| `thinking_mode = "adaptive"` on OpenAI or Mistral | "adaptive ... not supported" |
| Any reasoning param on Bedrock (aiobotocore) models | "does not support reasoning parameters" |
| A manual budget that `max_tokens` cannot hold beside the answer reserve, under the model's `min_thinking_budget` | "cannot think within max_tokens" |
| `NONE` effort on a Gemini model that lists `thinking_cannot_be_disabled` | "cannot turn thinking off" |
| A reasoning setting on a Mistral structured output whose structure method is not `instructor/mistral_tools` | "cannot reason on a structured output" |
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
| `pipelex/cogt/llm/thinking_budget.py` | `fit_thinking_budget()`: the answer reserve and the model's budget bounds |
| `pipelex/providers/openai/openai_config.py` | `OpenAIConfig` with `get_reasoning_level()` returning `ChatCompletionReasoningEffort \| None` |
| `pipelex/providers/anthropic/anthropic_config.py` | `AnthropicConfig` with `get_reasoning_level()` returning `AnthropicEffortLevel \| None` |
| `pipelex/providers/google/google_config.py` | `GoogleConfig` with `get_reasoning_level()` returning `genai_types.ThinkingLevel \| None` |
| `pipelex/providers/mistral/mistral_config.py` | `MistralConfig` with `get_reasoning_level()` returning Mistral's `ReasoningEffort \| None` |
| `pipelex/cogt/model_backends/model_spec.py` | `InferenceModelSpec.thinking_mode` field, and the `min_thinking_budget` and `max_thinking_budget` bounds read from its valued constraints |
| `pipelex/providers/openai/openai_completions_llm_worker.py` | OpenAI Completions reasoning resolution |
| `pipelex/providers/openai/openai_responses_llm_worker.py` | OpenAI Responses reasoning resolution |
| `pipelex/providers/anthropic/anthropic_llm_worker.py` | Anthropic thinking params builder |
| `pipelex/providers/google/google_llm_worker.py` | Google thinking config builder |
| `pipelex/providers/mistral/mistral_llm_worker.py` | Mistral reasoning effort resolution |
| `pipelex/providers/bedrock/bedrock_llm_worker.py` | Bedrock reasoning validation |
| `pipelex/cogt/llm/llm_worker_abstract.py` | `check_request()`, the shared rule each worker overrides and runs before every call, and `constrained_job_params()` |
| `pipelex/kernel/llm_ops.py` | `check_llm_setting_with_served_model()`: a setting checked against the model it resolves to, with the check its backend registered |
| `pipelex/pipe_operators/shared/llm_setting_check.py` | The load-time `llm_setting_refused_by_model` refusal of a `PipeLLM` or `PipeStructure` |
| `pipelex/pipelex.toml` | Default effort-to-budget maps and effort-to-level maps |

---

## Next Steps

- [Architecture Overview](./architecture-overview.md) — Understand the two-layer design
- [Test Profile Configuration](./test-profile-configuration.md) — Configure model sets for testing
