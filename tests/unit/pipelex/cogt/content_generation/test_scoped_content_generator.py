"""Unit tests for the `scoped_content_generator` ContextVar scope in `pipelex.runtime_hub`.

The scope lets an in-process run (the validation sweep, the in-process graph dry-run)
pin an inline content generator so its inference leaves resolve it through
`get_content_generator()` instead of the hub default — which, under a Temporal-enabled
hub, is `ContentGeneratorInWorkflow` and would dispatch activities. Mirrors the
`scoped_event_log` unit tests: set/restore, nesting, restore-on-exception, and
concurrent ContextVar isolation.
"""

import asyncio

import pytest

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.runtime_hub import get_content_generator, scoped_content_generator
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider


def _make_inline_generator() -> ContentGenerator:
    return ContentGenerator(generated_content_factory=GeneratedContentFactory(storage_provider=InMemoryStorageProvider()))


class TestScopedContentGenerator:
    def test_override_set_and_restored(self):
        """Inside the scope the resolved generator is the override; outside it is the hub default."""
        generator = _make_inline_generator()
        assert get_content_generator() is not generator
        with scoped_content_generator(generator):
            assert get_content_generator() is generator
        assert get_content_generator() is not generator

    def test_nesting_restores_outer_override(self):
        """An inner scope shadows the outer one and restores it on exit."""
        outer_generator = _make_inline_generator()
        inner_generator = _make_inline_generator()
        with scoped_content_generator(outer_generator):
            assert get_content_generator() is outer_generator
            with scoped_content_generator(inner_generator):
                assert get_content_generator() is inner_generator
            assert get_content_generator() is outer_generator
        assert get_content_generator() is not outer_generator

    def test_override_restored_on_exception(self):
        """The override is restored even when the scoped block raises."""
        generator = _make_inline_generator()

        def raise_inside_scope() -> None:
            with scoped_content_generator(generator):
                assert get_content_generator() is generator
                msg = "boom"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="boom"):
            raise_inside_scope()
        assert get_content_generator() is not generator

    @pytest.mark.asyncio
    async def test_concurrent_scopes_do_not_cross_contaminate(self):
        """Two concurrently-scoped tasks each see their own override (ContextVar isolation)."""
        generator_alpha = _make_inline_generator()
        generator_beta = _make_inline_generator()
        observed: dict[str, ContentGeneratorProtocol] = {}

        async def scope_and_observe(content_generator: ContentGeneratorProtocol, key: str) -> None:
            with scoped_content_generator(content_generator):
                await asyncio.sleep(0.01)
                observed[key] = get_content_generator()
                await asyncio.sleep(0.01)

        await asyncio.gather(
            scope_and_observe(generator_alpha, "alpha"),
            scope_and_observe(generator_beta, "beta"),
        )

        assert observed["alpha"] is generator_alpha
        assert observed["beta"] is generator_beta
        assert get_content_generator() is not generator_alpha
        assert get_content_generator() is not generator_beta
