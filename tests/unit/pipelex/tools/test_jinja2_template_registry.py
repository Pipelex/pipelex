"""Unit tests for the Jinja2 TemplateRegistry."""

import pytest
from jinja2 import DictLoader, Environment

from pipelex.tools.jinja2.jinja2_template_loader import TemplateLoader
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry


class TestTemplateRegistry:
    """Tests for TemplateRegistry functionality."""

    def setup_method(self) -> None:
        """Clear registry before each test."""
        TemplateRegistry.clear()

    def teardown_method(self) -> None:
        """Clear registry after each test to avoid polluting other tests."""
        TemplateRegistry.clear()

    def test_register_and_get(self) -> None:
        """Test basic registration and retrieval."""
        template_key = "test/template.html.jinja2"
        template_content = "<html>{{ title }}</html>"

        TemplateRegistry.register(template_key, template_source=template_content)
        retrieved = TemplateRegistry.get(template_key)

        assert retrieved == template_content

    def test_get_nonexistent_raises_keyerror(self) -> None:
        """Test that getting a non-existent template raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            TemplateRegistry.get("nonexistent/template.jinja2")

        assert "nonexistent/template.jinja2" in str(exc_info.value)
        assert "not found in registry" in str(exc_info.value)

    def test_is_registered(self) -> None:
        """Test is_registered check."""
        template_key = "test/check.jinja2"
        template_content = "{{ content }}"

        assert not TemplateRegistry.is_registered(template_key)

        TemplateRegistry.register(template_key, template_source=template_content)

        assert TemplateRegistry.is_registered(template_key)

    def test_keys(self) -> None:
        """Test listing all registered template keys."""
        TemplateRegistry.register("key1", template_source="content1")
        TemplateRegistry.register("key2", template_source="content2")
        TemplateRegistry.register("key3", template_source="content3")

        keys = TemplateRegistry.keys()

        assert len(keys) == 3
        assert "key1" in keys
        assert "key2" in keys
        assert "key3" in keys

    def test_clear(self) -> None:
        """Test clearing the registry."""
        TemplateRegistry.register("key1", template_source="content1")
        TemplateRegistry.register("key2", template_source="content2")

        assert len(TemplateRegistry.keys()) == 2

        TemplateRegistry.clear()

        assert len(TemplateRegistry.keys()) == 0

    def test_get_dict_loader(self) -> None:
        """Test that DictLoader is created from registry."""
        TemplateRegistry.register("base.html", template_source="<html>{% block content %}{% endblock %}</html>")
        TemplateRegistry.register("child.html", template_source="{% extends 'base.html' %}{% block content %}Hello{% endblock %}")

        loader = TemplateRegistry.get_dict_loader()

        assert isinstance(loader, DictLoader)

        # Verify loader can retrieve templates
        source, _, _ = loader.get_source(None, "base.html")  # type: ignore[arg-type]
        assert "<html>" in source

    def test_dict_loader_supports_includes(self) -> None:
        """Test that DictLoader enables {% include %} statements."""
        # Register templates
        TemplateRegistry.register("_partial.html", template_source="<div>Partial content</div>")
        TemplateRegistry.register("main.html", template_source="<html>{% include '_partial.html' %}</html>")

        # Create environment with DictLoader
        loader = TemplateRegistry.get_dict_loader()
        env = Environment(loader=loader)

        # Render template with include
        template = env.get_template("main.html")
        result = template.render()

        assert "<html>" in result
        assert "<div>Partial content</div>" in result

    def test_overwrite_existing_template(self) -> None:
        """Test that registering with same key overwrites."""
        template_key = "test/overwrite.jinja2"

        TemplateRegistry.register(template_key, template_source="original content")
        assert TemplateRegistry.get(template_key) == "original content"

        TemplateRegistry.register(template_key, template_source="new content")
        assert TemplateRegistry.get(template_key) == "new content"


class TestTemplateLoader:
    """Tests for the centralized TemplateLoader."""

    def setup_method(self) -> None:
        """Clear registry and loader state before each test."""
        TemplateRegistry.clear()
        TemplateLoader.reset()
        # Register a test template set for testing
        TemplateLoader.register_set(
            name="test_set",
            package="pipelex.graph.mermaidflow.templates",
            templates=[("_basic_body.html.jinja2", "test/template.html.jinja2")],
        )

    def test_register_set(self) -> None:
        """Test that register_set() adds a template set."""
        TemplateLoader.register_set(
            name="another_set",
            package="pipelex.graph.mermaidflow.templates",
            templates=[("mermaid.html.jinja2", "mermaid/main.html.jinja2")],
        )
        assert "another_set" in TemplateLoader.available_sets()

    def test_register_duplicate_is_idempotent(self) -> None:
        """Test that registering duplicate set is idempotent."""
        # Register again - should be no-op
        TemplateLoader.register_set(
            name="test_set",
            package="pipelex.graph.mermaidflow.templates",
            templates=[("_basic_body.html.jinja2", "test/template.html.jinja2")],
        )
        # Should still be registered
        assert "test_set" in TemplateLoader.available_sets()

    def test_load_registers_template(self) -> None:
        """Test that load() registers the specified template set."""
        TemplateLoader.load("test_set")
        assert TemplateRegistry.is_registered("test/template.html.jinja2")

    def test_load_is_idempotent(self) -> None:
        """Test that calling load() multiple times is safe."""
        TemplateLoader.load("test_set")
        initial_content = TemplateRegistry.get("test/template.html.jinja2")
        TemplateLoader.load("test_set")
        assert TemplateRegistry.get("test/template.html.jinja2") == initial_content

    def test_reload(self) -> None:
        """Test that reload() forces a fresh load."""
        TemplateLoader.load("test_set")
        initial_content = TemplateRegistry.get("test/template.html.jinja2")
        TemplateLoader.reload("test_set")
        assert TemplateRegistry.get("test/template.html.jinja2") == initial_content

    def test_load_all(self) -> None:
        """Test that load_all() loads all registered template sets."""
        TemplateLoader.load_all()
        assert TemplateRegistry.is_registered("test/template.html.jinja2")

    def test_load_unknown_set_raises(self) -> None:
        """Test that loading unknown template set raises ValueError."""
        with pytest.raises(ValueError, match="Unknown template set 'nonexistent'"):
            TemplateLoader.load("nonexistent")

    def test_is_loaded(self) -> None:
        """Test that is_loaded() tracks loaded state."""
        assert not TemplateLoader.is_loaded("test_set")
        TemplateLoader.load("test_set")
        assert TemplateLoader.is_loaded("test_set")

    def test_available_sets(self) -> None:
        """Test that available_sets() returns registered sets."""
        sets = TemplateLoader.available_sets()
        assert "test_set" in sets
