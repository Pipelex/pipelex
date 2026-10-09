import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.llm import llm_worker_abstract
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract


class TestLLMWorkerReasoningLog:
    @pytest.mark.parametrize(
        ("api_name", "settings", "expected_fields"),
        [
            ("OpenAI Responses", {"reasoning": {"effort": "high"}}, {"api_name": "OpenAI Responses", "reasoning": {"effort": "high"}}),
            (
                "Anthropic",
                {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
                {"api_name": "Anthropic", "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
            ),
            (
                "Anthropic",
                {"thinking": {"type": "enabled", "budget_tokens": 2048}, "output_config": None},
                {"api_name": "Anthropic", "thinking": {"type": "enabled", "budget_tokens": 2048}},
            ),
            ("Google", {"thinking_budget": 0}, {"api_name": "Google", "thinking_budget": 0}),
        ],
    )
    def test_the_settings_sent_are_said_once_at_debug_as_fields(
        self,
        mocker: MockerFixture,
        api_name: str,
        settings: dict[str, object],
        expected_fields: dict[str, object],
    ) -> None:
        """One fixed message; a setting the call does not send is left out, and a falsy value it does send, such as a zero budget, is kept."""
        debug = mocker.patch.object(llm_worker_abstract.log, "debug")
        verbose = mocker.patch.object(llm_worker_abstract.log, "verbose")

        LLMWorkerAbstract._log_reasoning_sent(api_name=api_name, settings=settings)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        debug.assert_called_once_with("Sending reasoning settings", fields=expected_fields)
        verbose.assert_not_called()

    @pytest.mark.parametrize(
        "settings",
        [
            {},
            {"reasoning_effort": None},
            {"thinking": None, "output_config": None},
        ],
    )
    def test_a_call_sending_no_reasoning_setting_logs_nothing(self, mocker: MockerFixture, settings: dict[str, object]) -> None:
        debug = mocker.patch.object(llm_worker_abstract.log, "debug")

        LLMWorkerAbstract._log_reasoning_sent(api_name="Mistral", settings=settings)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        debug.assert_not_called()
