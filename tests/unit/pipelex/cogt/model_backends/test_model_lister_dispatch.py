"""Behavioral dispatch through the model-lister seam: ``ModelLister.list_models`` resolves each
SDK's lister from the registry on the hub (no ``match`` over SDK strings), threads ``any_listed``
across SDKs, treats a registry miss and the soft ``ModelListingUnsupportedError`` signal alike
(reported as unsupported-for-listing), and wraps any other lister failure in a ``PipelexCLIError``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.cogt.exceptions import ModelListingUnsupportedError
from pipelex.cogt.model_backends.model_lists import ModelLister
from pipelex.plugins.model_lister_registry import ListModelsFn, ModelListerRegistry

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.model_backends.backend import InferenceBackend

_MODULE = "pipelex.cogt.model_backends.model_lists"


def _fake_backend(model_specs: dict[str, str]) -> InferenceBackend:
    # The loop only reads ``.model_specs`` and each spec's ``.sdk``.
    return cast(
        "InferenceBackend",
        SimpleNamespace(model_specs={name: SimpleNamespace(sdk=sdk) for name, sdk in model_specs.items()}),
    )


def _patch_hub(mocker: MockerFixture, *, backend: InferenceBackend, listers: dict[str, ListModelsFn]) -> SimpleNamespace:
    console = mocker.Mock()
    models_manager = mocker.Mock()
    models_manager.get_required_inference_backend.return_value = backend
    mocker.patch(f"{_MODULE}.get_models_manager", return_value=models_manager)
    mocker.patch(f"{_MODULE}.get_console", return_value=console)
    mocker.patch(f"{_MODULE}.get_model_lister_registry", return_value=ModelListerRegistry(listers))
    return SimpleNamespace(console=console)


def _printed(console: SimpleNamespace) -> str:
    return "\n".join(str(call.args[0]) for call in console.print.call_args_list if call.args)


@pytest.mark.asyncio(loop_scope="class")
class TestModelListerDispatch:
    async def test_registered_lister_is_invoked_with_expected_kwargs(self, mocker: MockerFixture) -> None:
        lister = mocker.AsyncMock()
        backend = _fake_backend({"model-a": "fake_sdk"})
        _patch_hub(mocker, backend=backend, listers={"fake_sdk": lister})

        await ModelLister.list_models("my_backend", flat=False)

        lister.assert_awaited_once_with(sdk="fake_sdk", backend_name="my_backend", backend=backend, flat=False, any_listed=False)

    async def test_any_listed_progresses_across_sdks(self, mocker: MockerFixture) -> None:
        lister = mocker.AsyncMock()
        # Two SDKs, both served by the same recorded lister: the first call sees any_listed=False,
        # the second sees any_listed=True (so its CSV header is suppressed).
        backend = _fake_backend({"model-a": "sdk_a", "model-b": "sdk_b"})
        _patch_hub(mocker, backend=backend, listers={"sdk_a": lister, "sdk_b": lister})

        await ModelLister.list_models("my_backend", flat=True)

        assert lister.await_count == 2
        assert lister.await_args_list[0].kwargs["any_listed"] is False
        assert lister.await_args_list[1].kwargs["any_listed"] is True

    async def test_unknown_sdk_is_reported_unsupported(self, mocker: MockerFixture) -> None:
        backend = _fake_backend({"model-a": "no_lister_sdk"})
        ctx = _patch_hub(mocker, backend=backend, listers={})

        await ModelLister.list_models("my_backend", flat=False)

        assert "we don't support for remote listing" in _printed(ctx.console)
        assert "no_lister_sdk" in _printed(ctx.console)

    async def test_lister_unsupported_signal_is_reported_unsupported(self, mocker: MockerFixture) -> None:
        # The translate path: a lister raises the core soft signal (as the Anthropic lister does for
        # a bedrock-backed client) → same outcome as a missing lister, never a hard failure.
        lister = mocker.AsyncMock(side_effect=ModelListingUnsupportedError(sdk="fake_sdk"))
        backend = _fake_backend({"model-a": "fake_sdk"})
        ctx = _patch_hub(mocker, backend=backend, listers={"fake_sdk": lister})

        await ModelLister.list_models("my_backend", flat=False)

        assert "we don't support for remote listing" in _printed(ctx.console)

    async def test_lister_failure_is_wrapped_in_cli_error(self, mocker: MockerFixture) -> None:
        lister = mocker.AsyncMock(side_effect=RuntimeError("provider API exploded"))
        backend = _fake_backend({"model-a": "fake_sdk"})
        _patch_hub(mocker, backend=backend, listers={"fake_sdk": lister})

        with pytest.raises(PipelexCLIError, match="Error listing models for SDK 'fake_sdk' in backend 'my_backend'"):
            await ModelLister.list_models("my_backend", flat=False)
