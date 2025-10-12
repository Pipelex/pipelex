# Rules to choose LLM models used in PipeLLMs.

## LLM Configuration System

In order to use it in a pipe, an LLM is referenced by its llm_handle (alias) and possibly by an llm_preset.
LLM configurations are managed through the new inference backend system with files located in `.pipelex/inference/`:

- **Model Deck**: `.pipelex/inference/deck/base_deck.toml` and `.pipelex/inference/deck/overrides.toml`
- **Backends**: `.pipelex/inference/backends.toml` and `.pipelex/inference/backends/*.toml`
- **Routing**: `.pipelex/inference/routing_profiles.toml`

## LLM Handles

An llm_handle can be either:
1. **A direct model name** (like "gpt-4o-mini", "claude-3-sonnet") - automatically available for all models loaded by the inference backend system
2. **An alias** - user-defined shortcuts that map to model names, defined in the `[aliases]` section:

```toml
[aliases]
base-claude = "claude-4.5-sonnet"
base-gpt = "gpt-5"
base-gemini = "gemini-2.5-flash"
base-mistral = "mistral-medium"
```

The system first looks for direct model names, then checks aliases if no direct match is found. The system handles model routing through backends automatically.

## Using an LLM Handle in a PipeLLM

Here is an example of using an llm_handle to specify which LLM to use in a PipeLLM:

```plx
[pipe.hello_world]
type = "PipeLLM"
description = "Write text about Hello World."
output = "Text"
model = { model = "gpt-5", temperature = 0.9 }
prompt = """
Write a haiku about Hello World.
"""
```

As you can see, to use the LLM, you must also indicate the temperature (float between 0 and 1) and max_tokens (either an int or the string "auto").

## LLM Presets

Presets are meant to record the choice of an llm with its hyper parameters (temperature and max_tokens) if it's good for a particular task. LLM Presets are skill-oriented.

Examples:
```toml
llm_to_reason = { model = "base-claude", temperature = 1 }
llm_to_extract_invoice = { model = "claude-3-7-sonnet", temperature = 0.1, max_tokens = "auto" }
```

The interest is that these presets can be used to set the LLM choice in a PipeLLM, like this:

```plx
[pipe.extract_invoice]
type = "PipeLLM"
description = "Extract invoice information from an invoice text transcript"
inputs = { invoice_text = "InvoiceText" }
output = "Invoice"
model = "llm_to_extract_invoice"
prompt = """
Extract invoice information from this invoice:

The category of this invoice is: $invoice_details.category.

@invoice_text
"""
```

The setting here `model = "llm_to_extract_invoice"` works because "llm_to_extract_invoice" has been declared as an llm_preset in the deck.
You must not use an LLM preset in a PipeLLM that does not exist in the deck. If needed, you can add llm presets.


You can override the predefined llm presets by setting them in `.pipelex/inference/deck/overrides.toml`.

