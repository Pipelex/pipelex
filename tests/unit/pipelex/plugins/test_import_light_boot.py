"""Import-light guard (codex C12): discovering and registering the built-in plugins must
not import any backend SDK (whether an optional extra like anthropic/linkup or a heavy core
dep like openai/portkey_ai/pypdfium2 — each plugin must defer its import into make_worker) nor
``temporalio`` (which ships only with the external ``pipelex-temporal`` plugin — core discovery
must never pull the Temporal SDK). Enforced in a subprocess whose meta-path finder raises on those
SDKs, which is deterministic where an in-process sys.modules check is not.
"""

import subprocess  # noqa: S404
import sys
import textwrap

_GUARD_SCRIPT = textwrap.dedent(
    """
    import sys
    import importlib.abc

    BLOCKED = (
        "anthropic",
        "mistralai",
        "google.genai",
        "boto3",
        "aioboto3",
        "fal_client",
        "huggingface_hub",
        "docling",
        "linkup",
        "openai",
        "portkey_ai",
        "pypdfium2",
        "temporalio",
        # No web framework either: the F3 HTTP-error-mapper seam is framework-agnostic
        # (it carries the core ``ErrorReport`` type). A host runtime owns FastAPI/Starlette;
        # discovery/registration in core must never pull one in.
        "fastapi",
        "starlette",
    )

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

    # Temporal ships externally (pipelex-temporal); core's built-ins claim no hub slots. temporalio
    # stays in the BLOCKED set above: core discovery must never pull the Temporal SDK, and
    # temporal.is_enabled=True must not change that (no core built-in reads it). The slot-claim
    # import-light guarantee for the Temporal thunks is pinned in the pipelex-temporal suite.
    config = SimpleNamespace(plugins=SimpleNamespace(disabled=[]), temporal=SimpleNamespace(is_enabled=True))
    registrar = discovery.build_registrar(config=config)
    assert registrar.inference_backends, "expected the built-in LLM backends to be registered"
    assert registrar.model_listers, "expected the built-in model listers to be registered import-light"
    assert registrar.orchestrators, "expected the built-in orchestrators to be registered"
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
