"""Tests for resolving a model reference down to a concrete handle."""

import pytest

from pipelex.kernel.llm_ops import concrete_llm_model_handle


@pytest.mark.dry_runnable
class TestConcreteLlmModelHandle:
    """The reported model must be the same whether or not the pipe actually ran."""

    def test_an_alias_resolves_in_one_hop(self) -> None:
        assert concrete_llm_model_handle("@default-general") == "claude-4.6-sonnet"

    def test_a_preset_follows_the_chain_past_its_alias(self) -> None:
        """The case that made DRY and LIVE disagree: a preset's model is itself an alias."""
        assert concrete_llm_model_handle("$writing-factual") == concrete_llm_model_handle("@default-premium")
        assert not concrete_llm_model_handle("$writing-factual").startswith(("@", "$"))

    def test_a_concrete_handle_is_returned_unchanged(self) -> None:
        assert concrete_llm_model_handle("claude-4.6-sonnet") == "claude-4.6-sonnet"

    def test_an_unknown_reference_is_returned_unchanged_rather_than_raising(self) -> None:
        """This feeds an observability field; a missing deck entry must not fail assembly."""
        assert concrete_llm_model_handle("@no-such-alias") == "@no-such-alias"
