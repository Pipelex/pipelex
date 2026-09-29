from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.render_job import RenderedDocument, RenderJob, RenderResources
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.document_renderer_registry import DocumentRendererRegistry, engine_choice_key
from pipelex.plugins.exceptions import DocumentEngineChoiceError, DuplicateDocumentRendererError
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))


class _StubRenderer:
    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:  # ruff: ignore[unused-method-argument]
        return RenderedDocument(data=job.filename.encode())


class _CountingFactory:
    def __init__(self) -> None:
        self.nb_calls = 0

    def __call__(self) -> _StubRenderer:
        self.nb_calls += 1
        return _StubRenderer()


class TestDocumentRendererRegistry:
    def test_a_registered_engine_resolves_for_its_format_and_source(self) -> None:
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_document_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, engine="stub", make_renderer=_StubRenderer)

        registry = DocumentRendererRegistry(entries=registrar.document_renderers, engine_choices={})
        entry = registry.resolve(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)

        assert entry is not None
        assert entry.engine == "stub"
        assert entry.source_plugin == "alpha"
        assert entry.check_template is None
        assert "document engine stub for pdf from layout" in discovery.contributions

    def test_a_format_or_source_no_engine_prints_resolves_to_none(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_document_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, engine="stub", make_renderer=_StubRenderer)
        registry = DocumentRendererRegistry(entries=registrar.document_renderers, engine_choices={})

        assert registry.resolve(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.HTML) is None
        assert registry.resolve(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT) is None
        assert registry.get_renderer(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT) is None

    def test_a_duplicate_engine_name_fails_loud_naming_both_plugins(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_document_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, engine="stub", make_renderer=_StubRenderer)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        with pytest.raises(DuplicateDocumentRendererError) as exc_info:
            registrar.add_document_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, engine="stub", make_renderer=_StubRenderer)

        message = str(exc_info.value)
        assert "alpha" in message
        assert "beta" in message

    def test_several_engines_need_the_configuration_to_choose(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_document_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, engine="first", make_renderer=_StubRenderer)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_document_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, engine="second", make_renderer=_StubRenderer)

        unchosen = DocumentRendererRegistry(entries=registrar.document_renderers, engine_choices={})
        with pytest.raises(DocumentEngineChoiceError) as exc_info:
            unchosen.resolve(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
        assert "first" in str(exc_info.value)
        assert "second" in str(exc_info.value)

        choice_key = engine_choice_key(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
        assert choice_key == "pdf.layout"
        chosen = DocumentRendererRegistry(entries=registrar.document_renderers, engine_choices={choice_key: "second"})
        entry = chosen.resolve(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
        assert entry is not None
        assert entry.engine == "second"

    def test_choosing_an_engine_that_is_not_installed_is_refused(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_document_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, engine="stub", make_renderer=_StubRenderer)
        registry = DocumentRendererRegistry(entries=registrar.document_renderers, engine_choices={"pdf.layout": "missing"})

        with pytest.raises(DocumentEngineChoiceError) as exc_info:
            registry.resolve(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)

        message = str(exc_info.value)
        assert "missing" in message
        assert "stub" in message

    def test_an_engine_is_built_once_on_first_use(self) -> None:
        factory = _CountingFactory()
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_document_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, engine="stub", make_renderer=factory)
        registry = DocumentRendererRegistry(entries=registrar.document_renderers, engine_choices={})
        assert factory.nb_calls == 0

        first = registry.get_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
        second = registry.get_renderer(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)

        assert first is not None
        assert first is second
        assert factory.nb_calls == 1
