import asyncio

import pytest

from pipelex.pipe_operators.func.pipe_func_call_context import function_of_call_in_flight, pipe_func_call_in_flight


def _compute_totals() -> str:
    return "totals"


def _compute_taxes() -> str:
    return "taxes"


class TestPipeFuncCallContext:
    def test_the_function_is_named_for_its_own_step_and_only_for_the_scope(self) -> None:
        assert function_of_call_in_flight(pipe_ref="invoicing.totals") is None

        with pipe_func_call_in_flight(pipe_ref="invoicing.totals", function=_compute_totals):
            assert function_of_call_in_flight(pipe_ref="invoicing.totals") is _compute_totals
            assert function_of_call_in_flight(pipe_ref="invoicing.taxes") is None
            with pipe_func_call_in_flight(pipe_ref="invoicing.taxes", function=_compute_taxes):
                assert function_of_call_in_flight(pipe_ref="invoicing.taxes") is _compute_taxes
            assert function_of_call_in_flight(pipe_ref="invoicing.totals") is _compute_totals

        assert function_of_call_in_flight(pipe_ref="invoicing.totals") is None

    @pytest.mark.asyncio
    async def test_concurrent_calls_each_see_their_own_function(self) -> None:
        async def _call(*, pipe_ref: str, function: object) -> object:
            assert callable(function)
            with pipe_func_call_in_flight(pipe_ref=pipe_ref, function=function):
                await asyncio.sleep(0)
                return function_of_call_in_flight(pipe_ref=pipe_ref)

        seen = await asyncio.gather(
            _call(pipe_ref="invoicing.totals", function=_compute_totals),
            _call(pipe_ref="invoicing.taxes", function=_compute_taxes),
        )

        assert seen == [_compute_totals, _compute_taxes]
