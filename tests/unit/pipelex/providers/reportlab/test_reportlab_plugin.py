import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from pytest_mock import MockerFixture

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS
from pipelex.providers.reportlab.reportlab_pdf_renderer import ReportlabPdfWorker
from pipelex.providers.reportlab.reportlab_plugin import ReportlabDocGenPlugin
from tests.unit.pipelex.providers.reportlab.reportlab_test_helpers import reportlab_pdf_model

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig

# Imports the plugin and registers it in a fresh interpreter whose import system refuses ReportLab, so a module-level
# import of ReportLab anywhere on that path fails loudly, naming the importer.
_LAZY_IMPORT_SCRIPT = textwrap.dedent(
    """
    import importlib.abc
    import sys

    class _ReportlabBlocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "reportlab" or fullname.startswith("reportlab."):
                raise ImportError(f"the import-light guard blocked '{fullname}'")
            return None

    sys.meta_path.insert(0, _ReportlabBlocker())

    from types import SimpleNamespace

    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS
    from pipelex.providers.reportlab.reportlab_plugin import ReportlabDocGenPlugin

    registrar = PluginRegistrar(config=SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))
    ReportlabDocGenPlugin().register(registrar)
    assert list(registrar.inference_backends) == [("doc_gen", "reportlab")]
    assert not [name for name in sys.modules if name == "reportlab" or name.startswith("reportlab.")]
    print("import-light OK")
    """
)


def _registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))


class TestReportlabPlugin:
    def test_the_plugin_registers_the_reportlab_sdk_of_the_doc_gen_family(self) -> None:
        plugin = ReportlabDocGenPlugin()
        registrar = _registrar()
        plugin.register(registrar)
        assert plugin.name == "reportlab"
        assert plugin.targets_api == PLUGIN_API_VERSION
        assert list(registrar.inference_backends) == [(InferenceFamily.DOC_GEN, "reportlab")]

    def test_the_factory_builds_the_reportlab_worker(self, mocker: MockerFixture) -> None:
        registrar = _registrar()
        ReportlabDocGenPlugin().register(registrar)
        (make_worker,) = registrar.inference_backends.values()
        worker = make_worker(
            inference_model=reportlab_pdf_model(), backend=mocker.MagicMock(), sdk_clients=mocker.MagicMock(), reporting_delegate=None
        )
        assert isinstance(worker, ReportlabPdfWorker)
        assert worker.check_template(request=mocker.MagicMock()) == []

    def test_the_plugin_is_a_kernel_builtin(self) -> None:
        assert [plugin.name for plugin in KERNEL_BUILTIN_PLUGINS].count("reportlab") == 1

    def test_registering_the_plugin_imports_no_reportlab(self) -> None:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", _LAZY_IMPORT_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"import-light guard failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "import-light OK" in result.stdout
