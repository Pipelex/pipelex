from typing import ClassVar


class ModelDeckCheckTestData:
    # Every name `TestModelDeckCheck`'s deck holds, under every kind and spelling, plus names it holds nowhere,
    # so a check made in any model type meets references it accepts and references it refuses.
    EVERY_REFERENCE: ClassVar[list[str]] = [
        "$cheap-llm",
        "@best-gpt",
        "~small-llm",
        "gpt-4o-mini",
        "$cheap-extract",
        "@best-extract",
        "~fallback-extract",
        "extract-engine",
        "$cheap-img",
        "@best-img",
        "~fallback-img",
        "img-painter",
        "$cheap-search",
        "@best-search",
        "~fallback-search",
        "web-searcher",
        "$cheap-judgment",
        "@best-judgment",
        "~fallback-judgment",
        "verdict-giver",
        "handle:img-painter",
        "alias:best-gpt",
        "preset:cheap-img",
        "waterfall:small-llm",
        "best-gpt",
        "small-llm",
        "cheap-llm",
        "held-nowhere",
        "@held-nowhere",
    ]
