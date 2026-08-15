"""Templating-style semantics: how a pipe's inputs are tagged into a prompt.

One function, and its totality is the point: every prompt-rendering entry point resolves a style
here, so nothing downstream has to carry a `None` and invent a fallback for it. Two levels only —
what the pipe authored, else the runtime default from config. No model metadata, no deck, no
credentials: a style is an authoring decision, not a property of whichever model happens to run.
"""

from pipelex.config import get_config
from pipelex.tools.templating.templating_style import TemplatingStyle


def resolve_templating_style(*, authored: TemplatingStyle | None) -> TemplatingStyle:
    """The style a prompt renders under: the authored one, else the configured default."""
    return authored or get_config().pipelex.templating_config.default_templating_style
