import pytest

from pipelex.pipe_controllers.batch.pipe_batch import resolve_batch_max_concurrency


class TestResolveBatchMaxConcurrency:
    @pytest.mark.parametrize(
        ("max_concurrency_setting", "expected_bound"),
        [
            ("unbounded", None),
            (1, 1),
            (8, 8),
            (100, 100),
        ],
    )
    def test_setting_translates_to_gather_bounded_argument(
        self,
        max_concurrency_setting: int | str,
        expected_bound: int | None,
    ) -> None:
        """The literal "unbounded" config maps to None (gather_bounded's no-bound sentinel); an int passes through.

        Guards the PipeBatch fan-out wiring against regressing to passing the raw "unbounded"
        string straight into gather_bounded, which would raise TypeError on its `max_concurrency < 1` check.
        """
        assert resolve_batch_max_concurrency(max_concurrency_setting) == expected_bound
