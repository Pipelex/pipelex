"""The remote gateway config may carry per-model keys this client's model-spec blueprint does not know.

It is served by a component that deploys on its own schedule, so a client can read a config written
by a different release than itself. The loader's per-model rule tolerates that skew: an unknown
per-model key that is header-shaped is a request header the back office started serving on purpose,
and anything else is pruned rather than sent to the provider. The `defaults` block gets the same
tolerance in `test_gateway_unknown_defaults.py`; a local backend file gets the strict counterpart of
the rule — see `test_backend_library_leniency.py`.
"""

from pathlib import Path
from typing import Any, cast

from pytest_mock import MockerFixture

from pipelex import log
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.gateway_config import GatewayConfig
from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs
from pipelex.providers.gateway.gateway_factory import GatewayFactory
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

GATEWAY_BACKENDS_TOML = """
[pipelex_gateway]
enabled = true
api_key = "pk-not-a-real-key"
"""


class TestGatewayUnknownPerModelKeys:
    """The loader's per-model rule on a remote payload: header-shaped keys are headers, the rest is pruned."""

    def _load(self, tmp_path: Path, *, model_specs: BackendModelSpecs) -> InferenceBackendLibrary:
        backends_dir = tmp_path / "backends"
        backends_dir.mkdir()
        backends_library_path = tmp_path / "backends.toml"
        backends_library_path.write_text(GATEWAY_BACKENDS_TOML)
        library = InferenceBackendLibrary.make_empty()
        library.load(
            secrets_provider=EnvSecretsProvider(),
            backends_library_path=str(backends_library_path),
            backends_dir_path=str(backends_dir),
            gateway_config=GatewayConfig(model_specs=model_specs, aws_region="eu-west-3"),
        )
        return library

    def _remote_specs(self, *, per_model_extras: dict[str, Any]) -> BackendModelSpecs:
        return cast(
            "BackendModelSpecs",
            {
                "defaults": {"model_type": "llm", "sdk": "gateway_completions"},
                "gpt-4o-mini": {"model_id": "gpt-4o-mini", **per_model_extras},
            },
        )

    def test_a_header_shaped_key_becomes_a_request_header(self, tmp_path: Path) -> None:
        """`x-portkey-config` is on every served model; without it the gateway cannot route."""
        library = self._load(tmp_path, model_specs=self._remote_specs(per_model_extras={"x-portkey-config": "pc-openai-6e7576"}))

        backend = library.get_inference_backend(backend_name="pipelex_gateway")
        assert backend is not None
        assert backend.model_specs["gpt-4o-mini"].extra_headers == {"x-portkey-config": "pc-openai-6e7576"}

    def test_a_non_header_key_is_pruned_and_the_boot_survives(self, tmp_path: Path) -> None:
        """Version skew, same as an unknown `defaults` key: pruned, not fatal, and not sent to the provider."""
        library = self._load(
            tmp_path,
            model_specs=self._remote_specs(per_model_extras={"x-portkey-config": "pc-openai-6e7576", "a_field_we_removed": "openai"}),
        )

        backend = library.get_inference_backend(backend_name="pipelex_gateway")
        assert backend is not None
        model_spec = backend.model_specs["gpt-4o-mini"]
        assert model_spec.extra_headers == {"x-portkey-config": "pc-openai-6e7576"}
        assert model_spec.model_id == "gpt-4o-mini"

    def test_a_header_shaped_key_with_a_non_string_value_is_pruned_and_the_boot_survives(self, tmp_path: Path) -> None:
        """A request header value must be a string. A served non-string one is skew too: pruned, never
        stringified onto the wire, and never a boot failure — that would defeat the whole tolerance.
        """
        library = self._load(
            tmp_path,
            model_specs=self._remote_specs(per_model_extras={"x-portkey-config": "pc-openai-6e7576", "x-weird": 3}),
        )

        backend = library.get_inference_backend(backend_name="pipelex_gateway")
        assert backend is not None
        assert backend.model_specs["gpt-4o-mini"].extra_headers == {"x-portkey-config": "pc-openai-6e7576"}

    def test_a_declared_field_that_used_to_ride_in_the_bag_lands_in_the_field(self, tmp_path: Path) -> None:
        """`endpoint_path` is served on the image models today. Had it stayed a bag entry, this rule
        would prune it — the whole reason it was promoted to a field first.
        """
        library = self._load(tmp_path, model_specs=self._remote_specs(per_model_extras={"endpoint_path": "openai/deployments/x/images/generations"}))

        backend = library.get_inference_backend(backend_name="pipelex_gateway")
        assert backend is not None
        model_spec = backend.model_specs["gpt-4o-mini"]
        assert model_spec.endpoint_path == "openai/deployments/x/images/generations"
        assert not model_spec.extra_headers

    def test_the_accepted_header_reaches_the_wire(self, tmp_path: Path, mocker: MockerFixture) -> None:
        telemetry_manager = mocker.MagicMock()
        telemetry_manager.is_pipelex_gateway_portkey_tracing_enabled.return_value = False
        mocker.patch("pipelex.providers.gateway.gateway_factory.get_telemetry_manager", return_value=telemetry_manager)
        library = self._load(tmp_path, model_specs=self._remote_specs(per_model_extras={"x-portkey-config": "pc-openai-6e7576"}))
        backend = library.get_inference_backend(backend_name="pipelex_gateway")
        assert backend is not None
        model_spec = backend.model_specs["gpt-4o-mini"]

        extra_headers, _ = GatewayFactory.make_extras(model_spec, inference_job=mocker.MagicMock(spec=LLMJob), output_desc="text")

        assert extra_headers["x-portkey-config"] == "pc-openai-6e7576"

    def test_pruning_a_per_model_key_does_not_need_the_log_hub(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Same constraint as the `defaults` prune: this runs on gateway loads that precede runtime_hub.set_config()."""
        mocker.patch.object(log.log_dispatch, "_log_config_instance", None)

        library = self._load(tmp_path, model_specs=self._remote_specs(per_model_extras={"a_field_we_removed": "openai"}))

        assert library.get_inference_backend(backend_name="pipelex_gateway") is not None
