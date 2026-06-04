"""Regression guard: the package-default ``pipelex/pipelex.toml`` ships
``[temporal.queue_options]`` as an empty table — no ``[temporal.queue_options.<queue>]``
sub-tables.

Shipping an overlay for the baseline's ``default_task_queue`` name (e.g.
``temporal_task_queue``) would create an orphan overlay the moment a
downstream deployment renames its queue. Config merging cannot delete
baseline keys, so that orphan would be unrecoverable from the override.
The downstream `.pipelex/pipelex.toml` and `pipelex/kit/configs/pipelex.toml`
template were aligned to match this rationale.

If a future change re-adds a `[temporal.queue_options.<queue>]` block to
the package default, this test fails loudly.
"""

from pathlib import Path

import tomli

import pipelex

_PIPELEX_DEFAULT_CONFIG_PATH = Path(pipelex.__file__).parent / "pipelex.toml"


class TestShippingDefaultQueueOptionsEmpty:
    def test_no_queue_specific_overlay_shipped(self) -> None:
        with _PIPELEX_DEFAULT_CONFIG_PATH.open("rb") as handle:
            config = tomli.load(handle)

        queue_options = config["temporal"]["queue_options"]
        sub_tables = [key for key, value in queue_options.items() if isinstance(value, dict)]
        assert sub_tables == [], (
            f"Package-default `[temporal.queue_options]` must ship empty to avoid orphan-overlay drift "
            f"when a deployment renames its default_task_queue. Found unexpected sub-tables: {sub_tables}."
        )
