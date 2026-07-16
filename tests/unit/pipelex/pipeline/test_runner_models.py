"""Pin the protocol `models()` deck shape on :class:`PipelexMTHDSProtocol`.

The aliases/waterfalls routing extensions are keyed BY CATEGORY: the same alias name exists
in several categories pointing at different models, and the old flat maps (built by
``update()``-ing the per-category maps together) silently dropped entries on those
collisions. This is the regression pin for that fix — plus the presets→flat-``models``
projection, each entry carrying its category as ``type``.

Pure unit test (no Pipelex boot): ``list_models`` is patched at the runner's import site.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.pipeline.runner import PipelexMTHDSProtocol

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_DECK_RAW = {
    "presets": {
        "llm": [{"name": "gpt-mini"}, {"name": "claude-x"}],
        "extract": [{"name": "extracto"}],
    },
    "aliases": {
        "llm": {"default-small": "gpt-mini"},
        "extract": {"default-small": "extracto"},
    },
    "waterfalls": {
        "llm": {"default-small": ["gpt-mini", "claude-x"]},
        "extract": {"default-small": ["extracto"]},
    },
}


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerModels:
    async def test_deck_keeps_category_keyed_aliases_on_cross_category_collision(self, mocker: MockerFixture) -> None:
        """The SAME alias name in two categories points at different models — both entries must survive."""
        mocker.patch("pipelex.pipeline.runner.list_models", return_value=_DECK_RAW)

        deck = await PipelexMTHDSProtocol().models()

        assert {(model.name, model.type) for model in deck.models} == {
            ("gpt-mini", "llm"),
            ("claude-x", "llm"),
            ("extracto", "extract"),
        }
        assert deck.aliases["llm"]["default-small"] == "gpt-mini"
        assert deck.aliases["extract"]["default-small"] == "extracto"
        assert deck.waterfalls["llm"]["default-small"] == ["gpt-mini", "claude-x"]
        assert deck.waterfalls["extract"]["default-small"] == ["extracto"]
