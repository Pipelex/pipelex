import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap

# Imports every module of the document engine contract in a fresh interpreter whose import system refuses ReportLab,
# so a module-level import of ReportLab anywhere on the contract's import path fails loudly, naming the importer. A
# plugin's engine imports the contract, and a contract that loaded the built-in engine's library would make it copy
# what it needs instead.
_CONTRACT_IMPORT_SCRIPT = textwrap.dedent(
    """
    import importlib
    import importlib.abc
    import pkgutil
    import sys

    class _ReportlabBlocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "reportlab" or fullname.startswith("reportlab."):
                raise ImportError(f"the import-light guard blocked '{fullname}'")
            return None

    sys.meta_path.insert(0, _ReportlabBlocker())

    import pipelex.cogt.doc_gen

    names = sorted(module.name for module in pkgutil.iter_modules(pipelex.cogt.doc_gen.__path__, "pipelex.cogt.doc_gen."))
    assert "pipelex.cogt.doc_gen.layout_display" in names
    assert "pipelex.cogt.doc_gen.template_environment" in names
    for name in names:
        importlib.import_module(name)
    assert not [name for name in sys.modules if name == "reportlab" or name.startswith("reportlab.")]
    print(f"import-light OK: {len(names)} modules")
    """
)


class TestContractImportLight:
    def test_importing_the_contract_imports_no_reportlab(self) -> None:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", _CONTRACT_IMPORT_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"import-light guard failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "import-light OK" in result.stdout
