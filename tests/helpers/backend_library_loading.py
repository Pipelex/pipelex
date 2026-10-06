"""Load an inference backend library from a backends table and one backend's file, both written to a temporary directory."""

from pathlib import Path

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

BOTH_MODES = [CredentialResolution.REQUIRE, CredentialResolution.SKIP]


def write_config(tmp_path: Path, *, backends_toml: str, model_specs_toml: str | None, backend_name: str = "acme") -> tuple[Path, str]:
    backends_dir = tmp_path / "backends"
    backends_dir.mkdir()
    backends_library_path = tmp_path / "backends.toml"
    backends_library_path.write_text(backends_toml)
    if model_specs_toml is not None:
        (backends_dir / f"{backend_name}.toml").write_text(model_specs_toml)
    return backends_library_path, str(backends_dir)


def load_library(
    tmp_path: Path,
    *,
    backends_toml: str,
    model_specs_toml: str | None,
    credentials: CredentialResolution,
    secrets_provider: SecretsProviderAbstract | None = None,
    backend_name: str = "acme",
) -> InferenceBackendLibrary:
    backends_library_path, backends_dir_path = write_config(
        tmp_path,
        backends_toml=backends_toml,
        model_specs_toml=model_specs_toml,
        backend_name=backend_name,
    )
    library = InferenceBackendLibrary.make_empty()
    library.load(
        secrets_provider=secrets_provider or EnvSecretsProvider(),
        backends_library_paths=[backends_library_path],
        backends_dir_path=backends_dir_path,
        credentials=credentials,
    )
    return library


def required_backend(library: InferenceBackendLibrary, backend_name: str = "acme") -> InferenceBackend:
    backend = library.get_inference_backend(backend_name=backend_name)
    assert backend is not None, f"backend '{backend_name}' is missing from {library.list_backend_names()}"
    return backend
