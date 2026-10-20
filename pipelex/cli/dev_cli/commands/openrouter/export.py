"""Render disabled draft backend entries using the runtime's current vocabulary."""

from decimal import Decimal, InvalidOperation

import tomlkit

from pipelex.cli.dev_cli.commands.openrouter.catalog import OpenRouterModel
from pipelex.cogt.model_backends.model_spec_document import describe_model_spec_document_rejection

INPUT_MODALITIES = {"text": "text", "image": "images", "file": "pdf", "audio": "audio", "video": "video"}


def price_per_million(*, price: object) -> float | None:
    if not isinstance(price, str):
        return None
    try:
        value = Decimal(price) * 1_000_000
        if not value.is_finite() or value < 0:
            return None
        converted = float(value)
        if converted == float("inf"):
            return None
        return converted
    except (InvalidOperation, ValueError, OverflowError):
        return None


def models_to_toml(*, models: list[OpenRouterModel]) -> str:
    document = tomlkit.document()
    document.add(tomlkit.comment("Draft OpenRouter backend. Review routing, capabilities and prices before enabling each entry."))
    document.add(tomlkit.comment("Token prices are USD per million tokens. Missing costs remain unknown; image/request fees need review."))
    for model in models:
        architecture = model.architecture
        if architecture is None:
            msg = f"Model {model.id!r} has no architecture; cannot export a backend entry"
            raise ValueError(msg)
        outputs = architecture.output_modalities
        if not outputs or any(output not in {"text", "image"} for output in outputs):
            msg = f"Model {model.id!r} has unsupported output modalities; export text and image models separately with --filter"
            raise ValueError(msg)
        entry = tomlkit.table()
        entry.add("enabled", False)
        if "image" in outputs:
            entry.add("model_type", "img_gen")
            entry.add("sdk", "openrouter_img_gen")
        else:
            entry.add("model_type", "llm")
            entry.add("sdk", "openai")
        inputs = [INPUT_MODALITIES[modality] for modality in architecture.input_modalities if modality in INPUT_MODALITIES]
        entry.add("inputs", inputs)
        exported_outputs = list(outputs)
        if "image" not in outputs and "structured_outputs" in model.supported_parameters:
            exported_outputs.append("structured")
            entry.add("structure_method", "instructor/openrouter_structured_outputs")
        entry.add("outputs", exported_outputs)
        # A context window is not an output limit. Omit an unknown limit.
        max_completion_tokens = (model.top_provider or {}).get("max_completion_tokens")
        if isinstance(max_completion_tokens, int) and not isinstance(max_completion_tokens, bool) and max_completion_tokens > 0:
            entry.add("max_tokens", max_completion_tokens)
        pricing = model.pricing or {}
        costs = tomlkit.inline_table()
        for source, destination in (("prompt", "input"), ("completion", "output")):
            price = price_per_million(price=pricing.get(source))
            if price is not None:
                costs.add(destination, price)
        if costs:
            entry.add("costs", costs)
        document.add(model.id, entry)
    rejection = describe_model_spec_document_rejection(document=document.unwrap())
    if rejection:
        raise ValueError(rejection)
    return document.as_string()
