"""One-line boot-time warn shown when the installed model deck has fallen behind the kit.

The warn is intentionally cheap (no hashing) so it can fire on every CLI invocation without slowing
the boot path. ``pipelex update`` and ``pipelex doctor`` perform the deeper hash-based diff.
"""

from __future__ import annotations

import os

from pipelex.cogt.models.deck_manifest import is_deck_stale_fast
from pipelex.hub import get_console
from pipelex.system.configuration.config_loader import config_manager

DECK_NOTICE_SUPPRESS_ENV_VAR = "PIPELEX_NO_DECK_NOTICE"


def warn_if_deck_stale() -> None:
    """Print a one-line yellow advisory when the installed deck appears to be out of date.

    Suppressed entirely when ``PIPELEX_NO_DECK_NOTICE=1`` is set in the environment.
    Silent when no deck dir exists yet (init_check elsewhere already prompts the user to run init).
    """
    if os.environ.get(DECK_NOTICE_SUPPRESS_ENV_VAR) == "1":
        return

    deck_dir = config_manager.model_decks_dir_path
    if not deck_dir.exists():
        return

    if not is_deck_stale_fast(deck_dir):
        return

    get_console().print(
        "[yellow]⚠[/yellow] [dim]Pipelex model deck may be out of date — run [cyan]pipelex update[/cyan] to refresh "
        f"(set [cyan]{DECK_NOTICE_SUPPRESS_ENV_VAR}=1[/cyan] to silence)[/dim]",
        highlight=False,
    )
