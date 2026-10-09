import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.llm import llm_worker_abstract
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract


class TestLLMWorkerReasoningLog:
    @pytest.mark.parametrize(
        ("api_name", "settings", "expected_line"),
        [
            ("OpenAI Responses", {"reasoning": {"effort": "high"}}, "OpenAI Responses request sends reasoning={'effort': 'high'}"),
            (
                "Anthropic",
                {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
                "Anthropic request sends thinking={'type': 'adaptive'}, output_config={'effort': 'high'}",
            ),
            (
                "Anthropic",
                {"thinking": {"type": "enabled", "budget_tokens": 2048}, "output_config": None},
                "Anthropic request sends thinking={'type': 'enabled', 'budget_tokens': 2048}",
            ),
            ("Google", {"thinking_budget": 0}, "Google request sends thinking_budget=0"),
        ],
    )
    def test_the_settings_sent_are_said_once_at_verbose(
        self,
        mocker: MockerFixture,
        api_name: str,
        settings: dict[str, object],
        expected_line: str,
    ) -> None:
        """A setting the call does not send is left out; a falsy value it does send, such as a zero budget, is kept."""
        verbose = mocker.patch.object(llm_worker_abstract.log, "verbose")

        LLMWorkerAbstract._log_reasoning_sent(api_name=api_name, settings=settings)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        verbose.assert_called_once_with(expected_line)

    @pytest.mark.parametrize(
        "settings",
        [
            {},
            {"reasoning_effort": None},
            {"thinking": None, "output_config": None},
        ],
    )
    def test_a_call_sending_no_reasoning_setting_logs_nothing(self, mocker: MockerFixture, settings: dict[str, object]) -> None:
        verbose = mocker.patch.object(llm_worker_abstract.log, "verbose")

        LLMWorkerAbstract._log_reasoning_sent(api_name="Mistral", settings=settings)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        verbose.assert_not_called()
