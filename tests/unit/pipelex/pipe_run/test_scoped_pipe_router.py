import pytest

from pipelex.interpreter_hub import get_pipe_router, scoped_pipe_router, set_pipe_router, teardown_current_pipe_router
from pipelex.pipe_run.pipe_router import PipeRouter


class TestScopedPipeRouter:
    def test_sets_router_inside_block(self) -> None:
        scoped = PipeRouter()
        with scoped_pipe_router(scoped):
            assert get_pipe_router() is scoped

    def test_restores_prior_override_not_none_on_exit(self) -> None:
        # The key improvement over the raw teardown_current_pipe_router(), which
        # unconditionally resets the override to None: scoped_pipe_router must
        # restore whatever override was active before the block.
        base = PipeRouter()
        set_pipe_router(base)
        try:
            scoped = PipeRouter()
            with scoped_pipe_router(scoped):
                assert get_pipe_router() is scoped
            assert get_pipe_router() is base
        finally:
            teardown_current_pipe_router()

    def test_nested_scope_restores_outer_override_on_inner_exit(self) -> None:
        outer = PipeRouter()
        inner = PipeRouter()
        with scoped_pipe_router(outer):
            assert get_pipe_router() is outer
            with scoped_pipe_router(inner):
                assert get_pipe_router() is inner
            assert get_pipe_router() is outer

    def test_restores_prior_override_even_when_block_raises(self) -> None:
        base = PipeRouter()
        set_pipe_router(base)
        try:
            scoped = PipeRouter()
            msg = "boom"
            with pytest.raises(RuntimeError, match="boom"), scoped_pipe_router(scoped):
                raise RuntimeError(msg)
            assert get_pipe_router() is base
        finally:
            teardown_current_pipe_router()
