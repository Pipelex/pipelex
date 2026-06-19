"""Import-light guard (codex C12): discovering and registering the built-in plugins must
not import any optional backend SDK. Enforced in a subprocess whose meta-path finder raises
on the optional SDKs, which is deterministic where an in-process sys.modules check is not.
"""

import subprocess  # noqa: S404
import sys
import textwrap

_GUARD_SCRIPT = textwrap.dedent(
    """
    import sys
    import importlib.abc

    BLOCKED = ("anthropic", "mistralai", "google.genai", "boto3", "aioboto3", "fal_client", "huggingface_hub")

    class _Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            for blocked in BLOCKED:
                if fullname == blocked or fullname.startswith(blocked + "."):
                    raise ImportError(f"import-light guard blocked '{fullname}'")
            return None

    sys.meta_path.insert(0, _Blocker())

    from types import SimpleNamespace

    import pipelex.plugins.discovery as discovery

    # Isolate to the built-ins: ignore any external entry points installed in this venv,
    # whose load() could legitimately import an optional SDK.
    discovery._external_entry_points = lambda: []

    config = SimpleNamespace(plugins=SimpleNamespace(disabled=[]))
    registrar = discovery.build_registrar(config=config)
    assert registrar.inference_backends, "expected the built-in LLM backends to be registered"
    print("import-light OK")
    """
)


class TestImportLightBoot:
    def test_building_registrar_imports_no_backend_sdk(self) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _GUARD_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"import-light guard failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "import-light OK" in result.stdout
