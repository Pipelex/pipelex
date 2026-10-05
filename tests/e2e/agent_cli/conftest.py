"""Fixtures for offline-mode E2E tests that spawn the agent CLI as a subprocess.

The tests in this directory invoke ``.venv/bin/pipelex-agent`` directly so we exercise the
exact surface that fails under the codex-sandbox handoff. To keep the runs hermetic each
test gets its own ``HOME`` pointing at ``tmp_path``, which controls the location of the
``.pipelex/`` config directory.

The kit configs are copied wholesale so the subprocess sees a realistic Pipelex install,
not a hand-rolled minimal one. Per-test tweaks (the active routing profile) layer on top.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipelex.kit.paths import get_kit_configs_dir

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELEX_AGENT_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex-agent"
OFFLINE_BUNDLES_DIR = REPO_ROOT / "tests" / "e2e" / "data" / "offline_mode"


def _copy_kit_configs_into(pipelex_dir: Path) -> None:
    """Mirror the kit's ``configs/`` tree into ``pipelex_dir`` so the subprocess can boot.

    Copies the top-level config files (``pipelex.toml``, ``telemetry.toml``, ``plxt.toml``)
    and the ``inference/`` subtree
    (``backends.toml``, ``routing_profiles.toml``, ``backends/``, ``deck/``).
    """
    kit_configs_dir = Path(str(get_kit_configs_dir()))
    pipelex_dir.mkdir(parents=True, exist_ok=True)

    for top_level_file in ("pipelex.toml", "telemetry.toml", "plxt.toml"):
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


@pytest.fixture
def hermetic_home(tmp_path: Path) -> Path:
    """Return a tmp ``HOME`` that already has a populated ``.pipelex/`` config tree.

    Tests further tweak the resulting directory (the active routing profile) before invoking the
    subprocess.
    """
    pipelex_dir = tmp_path / ".pipelex"
    _copy_kit_configs_into(pipelex_dir)
    return tmp_path


@pytest.fixture
def offline_subprocess_env(hermetic_home: Path) -> dict[str, str]:
    """Base subprocess env that points the CLI at the hermetic HOME.

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
        # Force CI test mode so vertexai is skipped.
        "RUN_MODE": "ci_test",
        # Dummy credentials — the test never makes a real provider call (dry-run only) and
        # ``lenient=True`` (set by ``--dry-run``) skips backends whose env vars are missing
        # rather than raising. We populate every key so backend loading is deterministic
        # regardless of the developer's shell environment.
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
        "TYPESAFE_API_KEY": "dummy-typesafe-key",
        "XAI_API_KEY": "dummy-xai-key",
    }
    return env


# Public helpers re-exported for use from test modules.
__all__ = [
    "OFFLINE_BUNDLES_DIR",
    "PIPELEX_AGENT_BIN",
    "write_active_routing_profile",
]
