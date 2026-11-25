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


class UnservedReferenceTestData:
    # The one model the deck serves, as an LLM.
    SERVED_HANDLE = "served-model"
    # A model a catalog of the deployment declares on a backend it does not enable, as `claude-4.5-haiku` is with
    # `anthropic` switched off.
    CATALOGED_HANDLE = "switched-off-model"
    # Names no catalog knows: one a letter away from the served handle, one near nothing.
    NEAR_HANDLE = "served-modle"
    FAR_HANDLE = "zzz"
