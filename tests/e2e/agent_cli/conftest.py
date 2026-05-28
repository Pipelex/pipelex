"""Fixtures for offline-mode E2E tests that spawn the agent CLI as a subprocess.

The tests in this directory invoke ``.venv/bin/pipelex-agent`` directly so we exercise the
exact surface that fails under the codex-sandbox handoff. To keep the runs hermetic each
test gets its own ``HOME`` pointing at ``tmp_path`` — that controls both the location of
the ``.pipelex/`` config directory AND the ``~/.pipelex/cache/`` directory the offline
fallback reads.

The kit configs are copied wholesale so the subprocess sees a realistic Pipelex install,
not a hand-rolled minimal one. Per-test tweaks (gateway enabled/disabled, terms accepted,
primed cache content) layer on top.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.exceptions import ModelReferenceParseError
from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.pipelex_service.remote_config_cache import CACHE_SCHEMA_VERSION
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from pipelex.cogt.models.model_deck import (
        ExtractDeckBlueprint,
        ImgGenDeckBlueprint,
        LLMDeckBlueprint,
        ModelDeckBlueprint,
        SearchDeckBlueprint,
    )

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELEX_AGENT_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex-agent"
OFFLINE_BUNDLES_DIR = REPO_ROOT / "tests" / "e2e" / "data" / "offline_mode"

# Reserved/unroutable address — httpx will raise ConnectError immediately without hanging.
UNREACHABLE_REMOTE_CONFIG_URL = "http://127.0.0.1:1/pipelex_remote_config.json"

# Minimal-but-valid gateway spec bodies per model type (valid against InferenceModelSpecBlueprint).
# Each ``sdk`` names the dedicated gateway worker for its type — gateway_completions (LLM),
# gateway_img_gen (image), gateway_extract, gateway_search — i.e. a value the matching worker factory's
# gateway branch accepts (an unrecognized sdk like "gateway_image" hits ``case _: raise NotImplementedError``).
# The sdk is consumed only at worker creation, which the offline dry-run tests never reach
# (ContentGeneratorDry mocks generation), so the membership check is indifferent to it — but it must still
# be real so the fake cache stays faithful and any non-dry consumer of this helper can build a worker.
_GATEWAY_SPEC_TEMPLATE_BY_TYPE: dict[ModelType, dict[str, Any]] = {
    ModelType.LLM: {"sdk": "gateway_completions", "model_type": "llm", "inputs": ["text"], "outputs": ["text", "structured"]},
    ModelType.IMG_GEN: {"sdk": "gateway_img_gen", "model_type": "img_gen"},
    ModelType.TEXT_EXTRACTOR: {"sdk": "gateway_extract", "model_type": "text_extractor"},
    ModelType.SEARCH: {"sdk": "gateway_search", "model_type": "search"},
}


def _deck_section_handle_references(
    section: LLMDeckBlueprint | ExtractDeckBlueprint | ImgGenDeckBlueprint | SearchDeckBlueprint,
) -> list[str]:
    """Every raw model reference a deck section names via aliases, waterfalls, or presets.

    Choice defaults are intentionally NOT read here: in the kit deck they are always
    ``@alias`` / ``$preset`` references, so the terminal handles they resolve to are
    already named as alias targets / preset models and get collected anyway. Skipping
    them keeps this free of the ``disabled`` sentinel and the typed choice-default union.
    """
    raw_references: list[str] = list(section.aliases.values())
    for waterfall_entries in section.waterfalls.values():
        raw_references.extend(waterfall_entries)
    for preset in section.presets.values():
        raw_references.append(preset.model)
    return raw_references


def load_kit_model_deck_blueprint() -> ModelDeckBlueprint:
    """Load the shipped kit deck blueprint — the same deck files the offline subprocess loads."""
    deck_dir = Path(str(get_kit_configs_dir())) / "inference" / "deck"
    return load_model_deck_blueprint(model_deck_paths=ModelManager.get_model_deck_paths(deck_dir_path=str(deck_dir)))


def software_only_internal_handles() -> set[str]:
    """Handles served by the local ``internal`` backend — the ones the Pipelex Gateway never provides.

    ``PipelexBackend.INTERNAL`` is the software-only backend ("runs internally, without AI" — e.g. the
    pypdfium2 / docling text extractors). Those handles have no gateway equivalent, so they must be
    excluded from the derived gateway specs: otherwise the primed cache would claim the gateway serves a
    software-only extractor, and a deck alias like ``@default-no-inference`` / ``@default-text-from-pdf``
    could resolve through the fake ``gateway_extract`` worker instead of the real internal backend.

    Read straight from the shipped backend spec file (no booted Pipelex needed) and keyed off the enum
    value, so adding a new software-only extractor to the internal backend auto-excludes it here too.
    Provider-backed models (claude, gpt, linkup, nano-banana, ...) are intentionally NOT excluded: the
    gateway genuinely proxies those, so they belong in the faithful gateway cache.
    """
    internal_spec_path = Path(str(get_kit_configs_dir())) / "inference" / "backends" / f"{PipelexBackend.INTERNAL}.toml"
    raw_specs = load_toml_from_path(path=str(internal_spec_path))
    return {name for name, spec in raw_specs.items() if name != "defaults" and isinstance(spec, dict)}


def gateway_backend_model_specs_for_kit_deck() -> dict[str, Any]:
    """Build a gateway ``backend_model_specs`` payload covering every concrete model handle the kit deck names.

    Derived from the shipped kit deck rather than a hand-maintained list, so the primed
    offline cache auto-tracks deck changes — e.g. promoting a premium alias to a new model
    no longer silently breaks these tests. Every bare handle named in the deck's aliases,
    waterfalls, and presets (across all model types) gets a minimal spec declaring the
    gateway sdk for its type — all ``ModelManager._enforce_gateway_model_membership`` needs
    is name membership. Deck/gateway consistency itself is covered by ``TestModelDeckReferences``.

    Handles served by the software-only ``internal`` backend (see ``software_only_internal_handles``)
    are excluded: the gateway never provides them, so claiming it does would make the fake cache
    unfaithful and let a software-only extractor alias resolve through the gateway worker. Those
    handles are still reachable in the offline subprocess via the local internal backend, so the
    membership check passes for them without a gateway spec.
    """
    blueprint = load_kit_model_deck_blueprint()
    excluded_handles = software_only_internal_handles()

    handle_model_types: dict[str, ModelType] = {}
    for model_type, section in (
        (ModelType.LLM, blueprint.llm),
        (ModelType.TEXT_EXTRACTOR, blueprint.extract),
        (ModelType.IMG_GEN, blueprint.img_gen),
        (ModelType.SEARCH, blueprint.search),
    ):
        for raw_reference in _deck_section_handle_references(section):
            try:
                ref = ModelReference.parse(raw_reference)
            except ModelReferenceParseError:
                continue
            match ref.kind:
                case ModelReferenceKind.HANDLE:
                    if ref.name in excluded_handles:
                        continue
                    handle_model_types.setdefault(ref.name, model_type)
                case ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL | ModelReferenceKind.PRESET:
                    continue

    specs: dict[str, Any] = {"defaults": {"sdk": "gateway_completions"}}
    for handle, model_type in handle_model_types.items():
        specs[handle] = dict(_GATEWAY_SPEC_TEMPLATE_BY_TYPE[model_type])
    return specs


def _copy_kit_configs_into(pipelex_dir: Path) -> None:
    """Mirror the kit's ``configs/`` tree into ``pipelex_dir`` so the subprocess can boot.

    Copies the top-level config files (``pipelex.toml``, ``telemetry.toml``,
    ``pipelex_service.toml``, ``plxt.toml``) and the ``inference/`` subtree
    (``backends.toml``, ``routing_profiles.toml``, ``backends/``, ``deck/``).
    """
    kit_configs_dir = Path(str(get_kit_configs_dir()))
    pipelex_dir.mkdir(parents=True, exist_ok=True)

    for top_level_file in ("pipelex.toml", "telemetry.toml", "pipelex_service.toml", "plxt.toml"):
        shutil.copy2(kit_configs_dir / top_level_file, pipelex_dir / top_level_file)

    inference_dir = pipelex_dir / "inference"
    inference_dir.mkdir(exist_ok=True)
    for inference_file in ("backends.toml", "routing_profiles.toml"):
        shutil.copy2(kit_configs_dir / "inference" / inference_file, inference_dir / inference_file)

    for subdir in ("backends", "deck"):
        src = kit_configs_dir / "inference" / subdir
        dst = inference_dir / subdir
        dst.mkdir(exist_ok=True)
        for source_file in src.glob("*.toml"):
            shutil.copy2(source_file, dst / source_file.name)


def set_gateway_enabled(backends_path: Path, *, enabled: bool) -> None:
    """Toggle ``[pipelex_gateway].enabled`` in a backends.toml file in place.

    Avoids loading the file through ``tomlkit`` (which the kit configs are encoded with)
    by doing a targeted text rewrite — the kit file's ``enabled = true`` line directly
    follows the ``[pipelex_gateway]`` section header.
    """
    original_text = backends_path.read_text(encoding="utf-8")
    lines = original_text.splitlines(keepends=True)
    target_value = "true" if enabled else "false"
    in_gateway_section = False
    rewrote = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_gateway_section = stripped == "[pipelex_gateway]"
            continue
        if in_gateway_section and stripped.startswith("enabled"):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}enabled = {target_value}                         # set by offline-mode E2E fixture\n"
            rewrote = True
            break
    if not rewrote:
        msg = f"Could not find [pipelex_gateway].enabled in {backends_path}"
        raise AssertionError(msg)
    backends_path.write_text("".join(lines), encoding="utf-8")


def write_pipelex_service_config(pipelex_dir: Path, *, terms_accepted: bool, inference_setup_completed: bool) -> None:
    """Overwrite ``pipelex_service.toml`` so the subprocess skips the first-run gate."""
    content = (
        "[agreement]\n"
        f"terms_accepted = {str(terms_accepted).lower()}\n"
        "\n"
        "[onboarding]\n"
        f"inference_setup_completed = {str(inference_setup_completed).lower()}\n"
    )
    (pipelex_dir / "pipelex_service.toml").write_text(content, encoding="utf-8")


def write_active_routing_profile(routing_profiles_path: Path, active_profile: str) -> None:
    """Rewrite the ``active = "..."`` line in routing_profiles.toml in place."""
    original_text = routing_profiles_path.read_text(encoding="utf-8")
    lines = original_text.splitlines(keepends=True)
    rewrote = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("active"):
            lines[index] = f'active = "{active_profile}"\n'
            rewrote = True
            break
    if not rewrote:
        msg = f"Could not find 'active = ...' in {routing_profiles_path}"
        raise AssertionError(msg)
    routing_profiles_path.write_text("".join(lines), encoding="utf-8")


def write_remote_config_cache(pipelex_dir: Path, raw_config: dict[str, Any]) -> Path:
    """Write a primed ``cache/remote_config.json`` matching ``RemoteConfigCache``'s schema."""
    cache_dir = pipelex_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "remote_config.json"
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "cached_at": datetime.now(tz=timezone.utc).isoformat(),
        "raw_config": raw_config,
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    return cache_path


@pytest.fixture
def hermetic_home(tmp_path: Path) -> Path:
    """Return a tmp ``HOME`` that already has a populated ``.pipelex/`` config tree.

    Tests further tweak the resulting directory (toggle gateway, prime cache, ...) before
    invoking the subprocess.
    """
    pipelex_dir = tmp_path / ".pipelex"
    _copy_kit_configs_into(pipelex_dir)
    write_pipelex_service_config(pipelex_dir, terms_accepted=True, inference_setup_completed=True)
    return tmp_path


@pytest.fixture
def offline_subprocess_env(hermetic_home: Path) -> dict[str, str]:
    """Base subprocess env that points the CLI at the hermetic HOME and an unreachable
    remote-config URL.

    Tests extend this dict before passing it to ``subprocess.run``. Dummy credentials are
    populated for every backend that the kit's ``backends.toml`` references so the dry-run
    setup doesn't fail with ``InferenceBackendCredentialsError`` for backends we don't care
    about — under ``needs_inference=False`` Pipelex is lenient on credential validation, but
    only at the resolution layer; the env-var substitution itself still requires the var to
    exist.
    """
    env: dict[str, str] = {
        "HOME": str(hermetic_home),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PIPELEX_REMOTE_CONFIG_URL": UNREACHABLE_REMOTE_CONFIG_URL,
        # Force CI test mode so vertexai is skipped and terms-acceptance gate doesn't fire
        # for code paths that still consult the integration mode.
        "RUN_MODE": "ci_test",
        # Dummy credentials — the test never makes a real provider call (dry-run only) and
        # ``lenient=True`` (set by ``--dry-run``) skips backends whose env vars are missing
        # rather than raising. We populate every key so backend loading is deterministic
        # regardless of the developer's shell environment.
        "PIPELEX_GATEWAY_API_KEY": "dummy-gateway-key",
        "ANTHROPIC_API_KEY": "dummy-anthropic-key",
        "AWS_REGION": "us-east-1",
        "AZURE_API_BASE": "https://example.invalid",
        "AZURE_API_KEY": "dummy-azure-key",
        "AZURE_API_VERSION": "2024-01-01",
        "BLACKBOX_API_KEY": "dummy-blackbox-key",
        "FAL_API_KEY": "dummy-fal-key",
        "GCP_CREDENTIALS_FILE_PATH": "/dev/null",
        "GCP_LOCATION": "us-central1",
        "GCP_PROJECT_ID": "dummy-project",
        "GOOGLE_API_KEY": "dummy-google-key",
        "GROQ_API_KEY": "dummy-groq-key",
        "HF_TOKEN": "dummy-hf-token",
        "LINKUP_API_KEY": "dummy-linkup-key",
        "MINIMAX_API_KEY": "dummy-minimax-key",
        "MISTRAL_API_KEY": "dummy-mistral-key",
        "OPENAI_API_KEY": "dummy-openai-key",
        "OPENROUTER_API_KEY": "dummy-openrouter-key",
        "PORTKEY_API_KEY": "dummy-portkey-key",
        "SCALEWAY_API_KEY": "dummy-scaleway-key",
        "SCALEWAY_ENDPOINT": "https://example.invalid",
        "XAI_API_KEY": "dummy-xai-key",
    }
    return env


# Public helpers re-exported for use from test modules.
__all__ = [
    "OFFLINE_BUNDLES_DIR",
    "PIPELEX_AGENT_BIN",
    "UNREACHABLE_REMOTE_CONFIG_URL",
    "gateway_backend_model_specs_for_kit_deck",
    "load_kit_model_deck_blueprint",
    "set_gateway_enabled",
    "software_only_internal_handles",
    "write_active_routing_profile",
    "write_remote_config_cache",
]
