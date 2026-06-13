"""Coverage for the small protocol surfaces of :class:`PipelexMTHDSProtocol`.

Pins the ``extra`` rejection guard on ``execute``, the ``start`` not-implemented
contract, the ``models`` deck shaping (presets to ModelInfo, aliases/waterfalls kept
keyed by category, category filter passthrough), and the ``version`` handshake
including the missing-distribution fallback.
"""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.models import ModelCategory as MthdsModelCategory
from mthds.protocol.protocol import PROTOCOL_VERSION

from pipelex.builder.operations.models_ops import ModelCategory
from pipelex.pipeline.runner import (
    PipelexModelDeck,
    PipelexMTHDSProtocol,
    PipelexVersionInfo,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_MODELS_PAYLOAD: dict[str, Any] = {
    "presets": {
        "llm": [{"name": "smart_llm"}, {"name": "cheap_llm"}],
        "extract": [{"name": "doc_extractor"}],
    },
    "aliases": {
        "llm": {"best": "smart_llm"},
        "extract": {"ocr": "doc_extractor"},
    },
    "waterfalls": {
        "llm": {"main_chain": ["smart_llm", "cheap_llm"]},
        "extract": {},
    },
}


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerProtocolSurfaces:
    async def test_execute_rejects_extra_args_listing_keys_sorted(self) -> None:
        """The extra guard fires before any setup — no mocking needed — and names
        the offending keys in sorted order.
        """
        runner = PipelexMTHDSProtocol()

        with pytest.raises(PipelineRequestError) as exc_info:
            await runner.execute(pipe_code="any_pipe", extra={"zed": 1, "abc": 2})

        assert str(exc_info.value) == "The local runtime defines no extension args; got ['abc', 'zed']."

    async def test_start_raises_not_implemented_pointing_at_execute(self) -> None:
        """The local runtime does not implement async start; the message redirects to execute."""
        runner = PipelexMTHDSProtocol()

        with pytest.raises(NotImplementedError) as exc_info:
            await runner.start(pipe_code="any_pipe")

        assert "execute" in str(exc_info.value)
        assert "not implemented by the local runtime" in str(exc_info.value)

    async def test_models_shapes_deck_and_keeps_aliases_and_waterfalls_keyed_by_category(self, mocker: MockerFixture) -> None:
        """Each preset becomes one ModelInfo typed by its category; aliases and
        waterfalls stay keyed by category (no flattening, so the same alias name in
        two categories can't collide); no filter = categories None.
        """
        list_models_mock = mocker.patch("pipelex.pipeline.runner.list_models", return_value=_MODELS_PAYLOAD)
        runner = PipelexMTHDSProtocol()

        deck = await runner.models()

        assert isinstance(deck, PipelexModelDeck)
        model_entries = {(model_info.name, model_info.type) for model_info in deck.models}
        assert model_entries == {
            ("smart_llm", MthdsModelCategory.LLM),
            ("cheap_llm", MthdsModelCategory.LLM),
            ("doc_extractor", MthdsModelCategory.EXTRACT),
        }
        assert deck.aliases == {"llm": {"best": "smart_llm"}, "extract": {"ocr": "doc_extractor"}}
        assert deck.waterfalls == {"llm": {"main_chain": ["smart_llm", "cheap_llm"]}, "extract": {}}
        list_models_mock.assert_called_once_with(categories=None)

    async def test_models_category_filter_translates_to_builder_enum(self, mocker: MockerFixture) -> None:
        """A protocol-level category filter reaches list_models as the builder's enum."""
        llm_only_payload: dict[str, Any] = {
            "presets": {"llm": [{"name": "smart_llm"}]},
            "aliases": {"llm": {"best": "smart_llm"}},
            "waterfalls": {"llm": {}},
        }
        list_models_mock = mocker.patch("pipelex.pipeline.runner.list_models", return_value=llm_only_payload)
        runner = PipelexMTHDSProtocol()

        deck = await runner.models(category=MthdsModelCategory.LLM)

        list_models_mock.assert_called_once_with(categories=[ModelCategory.LLM])
        assert isinstance(deck, PipelexModelDeck)
        assert [(model_info.name, model_info.type) for model_info in deck.models] == [("smart_llm", MthdsModelCategory.LLM)]
        assert deck.aliases == {"llm": {"best": "smart_llm"}}
        assert deck.waterfalls == {"llm": {}}

    async def test_version_reports_installed_distribution(self, mocker: MockerFixture) -> None:
        """All three implementation version fields carry the installed pipelex version,
        alongside the protocol version and implementation name.
        """
        version_mock = mocker.patch("pipelex.pipeline.runner.metadata.version", return_value="9.8.7")
        runner = PipelexMTHDSProtocol()

        version_info = await runner.version()

        assert isinstance(version_info, PipelexVersionInfo)
        assert version_info.protocol_version == PROTOCOL_VERSION
        assert version_info.runner_version == "9.8.7"
        assert version_info.implementation == "pipelex"
        assert version_info.implementation_version == "9.8.7"
        assert version_info.runtime_version == "9.8.7"
        version_mock.assert_called_once_with("pipelex")

    async def test_version_falls_back_to_unknown_when_distribution_missing(self, mocker: MockerFixture) -> None:
        """A source checkout without an installed distribution must not break version()."""
        mocker.patch("pipelex.pipeline.runner.metadata.version", side_effect=metadata.PackageNotFoundError("pipelex"))
        runner = PipelexMTHDSProtocol()

        version_info = await runner.version()

        assert isinstance(version_info, PipelexVersionInfo)
        assert version_info.protocol_version == PROTOCOL_VERSION
        assert version_info.runner_version == "unknown"
        assert version_info.implementation == "pipelex"
        assert version_info.implementation_version == "unknown"
        assert version_info.runtime_version == "unknown"
