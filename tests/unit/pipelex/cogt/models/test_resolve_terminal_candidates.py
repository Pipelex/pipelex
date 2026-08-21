"""Unit coverage for ``ModelManager._collect_candidates``.

The resolver underpins the gateway-membership check in ``ModelManager.setup``: it walks
aliases/waterfalls and returns every reachable terminal handle. The membership check accepts
the deck if ANY candidate is in ``deck.inference_models`` or the gateway specs.

Two regressions are pinned here:

- A self-referential alias or waterfall must NOT loop forever.
- A waterfall with multiple fallbacks must surface every fallback as a candidate (when
  ``is_model_fallback_enabled`` is true, the default) so the membership check matches the
  runtime fallback behaviour at ``model_deck._get_optional_inference_model_with_fallback``.
"""

from __future__ import annotations

import pytest

from pipelex.cogt.models.model_manager import (
    ModelManager,
)
from pipelex.cogt.models.model_reference import ModelReference

# ``_collect_candidates`` is the pure-logic leaf of the membership resolver; testing it
# directly keeps the unit tests free of ModelDeck setup boilerplate.
_collect_candidates = ModelManager._collect_candidates  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


class TestResolveTerminalCandidates:
    def test_handle_returns_self(self) -> None:
        ref = ModelReference.parse("claude-4.7-opus")
        result = _collect_candidates(
            ref=ref,
            aliases={},
            waterfalls={},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == ["claude-4.7-opus"]

    def test_alias_resolves_to_handle(self) -> None:
        ref = ModelReference.parse("@best")
        result = _collect_candidates(
            ref=ref,
            aliases={"best": "claude-4.7-opus"},
            waterfalls={},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == ["claude-4.7-opus"]

    def test_dangling_alias_returns_alias_name(self) -> None:
        """When an alias has no target mapping, surface the alias name itself so the
        membership check fails with the user-visible identifier (the alias they wrote).
        """
        ref = ModelReference.parse("@missing-alias")
        result = _collect_candidates(
            ref=ref,
            aliases={},
            waterfalls={},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == ["missing-alias"]

    def test_alias_cycle_returns_empty(self) -> None:
        """Self-referential alias chain returns no candidates — the membership check then
        skips this reference rather than tripping ``GatewayUnknownModelError`` on a key the
        user never asked the gateway to resolve.
        """
        ref = ModelReference.parse("@loop")
        result = _collect_candidates(
            ref=ref,
            aliases={"loop": "@loop"},
            waterfalls={},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == []

    def test_waterfall_returns_every_fallback(self) -> None:
        """The fix for the false ``GatewayUnknownModelError`` when only later fallbacks are
        valid. The whole point of a waterfall is "try in order, use whatever works."
        """
        ref = ModelReference.parse("~fast-llm")
        result = _collect_candidates(
            ref=ref,
            aliases={},
            waterfalls={"fast-llm": ["future-model", "current-model"]},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == ["future-model", "current-model"]

    def test_waterfall_when_fallback_disabled_returns_only_first(self) -> None:
        """Mirrors ``model_deck._get_optional_inference_model_with_fallback``: when fallback
        is disabled the runtime only tries the first entry, so the membership check should
        only validate that one.
        """
        ref = ModelReference.parse("~fast-llm")
        result = _collect_candidates(
            ref=ref,
            aliases={},
            waterfalls={"fast-llm": ["future-model", "current-model"]},
            is_fallback_enabled=False,
            visited=set(),
        )
        assert result == ["future-model"]

    def test_self_referential_waterfall_returns_empty(self) -> None:
        """Cycle protection on the waterfall branch (issue #3 from PR review).

        Before the fix, ``waterfalls["A"] = ["~A"]`` would loop forever; now the visited
        guard short-circuits the recursion.
        """
        ref = ModelReference.parse("~A")
        result = _collect_candidates(
            ref=ref,
            aliases={},
            waterfalls={"A": ["~A"]},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == []

    def test_waterfall_through_alias_unrolls_both(self) -> None:
        """Mixed chains: alias → waterfall with two fallbacks → handles."""
        ref = ModelReference.parse("@fast")
        result = _collect_candidates(
            ref=ref,
            aliases={"fast": "~tier"},
            waterfalls={"tier": ["a", "b"]},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == ["a", "b"]

    @pytest.mark.parametrize(
        ("ref_str", "aliases", "waterfalls", "expected"),
        [
            ("@shared", {"shared": "~shared"}, {"shared": ["gpt-4o-mini", "claude-haiku"]}, ["gpt-4o-mini", "claude-haiku"]),
            ("~shared", {"shared": "claude-4.7-opus"}, {"shared": ["@shared"]}, ["claude-4.7-opus"]),
        ],
    )
    def test_shared_name_alias_and_waterfall_is_not_a_cycle(
        self,
        ref_str: str,
        aliases: dict[str, str],
        waterfalls: dict[str, list[str]],
        expected: list[str],
    ) -> None:
        """An alias and a waterfall may share a name without forming a cycle.

        Aliases and waterfalls live in separate dicts with no cross-validation, so a
        deck can hold both ``@shared`` and ``~shared``. Cycle detection must key on
        ``(kind, name)``: keying on name alone false-flags the second node as visited,
        returns no candidates, and silently skips gateway membership validation.
        """
        result = _collect_candidates(
            ref=ModelReference.parse(ref_str),
            aliases=aliases,
            waterfalls=waterfalls,
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == expected

    def test_cross_kind_cycle_still_returns_empty(self) -> None:
        """Keying on ``(kind, name)`` must not disable detection of a genuine cycle that
        alternates kinds: ``@x`` → ``~x`` → ``@x`` revisits the alias node and short-circuits.
        """
        ref = ModelReference.parse("@x")
        result = _collect_candidates(
            ref=ref,
            aliases={"x": "~x"},
            waterfalls={"x": ["@x"]},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == []

    def test_waterfall_with_invalid_entry_skips_only_that_branch(self) -> None:
        """A malformed waterfall entry that fails ``ModelReference.parse`` must not poison
        the rest of the list — the resolver moves on to the next entry.
        """
        ref = ModelReference.parse("~mixed")
        result = _collect_candidates(
            ref=ref,
            aliases={},
            waterfalls={"mixed": ["", "good-handle"]},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == ["good-handle"]

    def test_preset_returns_empty(self) -> None:
        """Presets are not handles; the membership check skips them."""
        ref = ModelReference.parse("$some-preset")
        result = _collect_candidates(
            ref=ref,
            aliases={},
            waterfalls={},
            is_fallback_enabled=True,
            visited=set(),
        )
        assert result == []

    @pytest.mark.parametrize(
        ("waterfall_entries", "is_fallback_enabled", "expected"),
        [
            (["a", "b", "c"], True, ["a", "b", "c"]),
            (["a", "b", "c"], False, ["a"]),
            (["only-one"], True, ["only-one"]),
            (["only-one"], False, ["only-one"]),
        ],
    )
    def test_waterfall_entries_respect_fallback_flag(
        self,
        waterfall_entries: list[str],
        is_fallback_enabled: bool,
        expected: list[str],
    ) -> None:
        ref = ModelReference.parse("~name")
        result = _collect_candidates(
            ref=ref,
            aliases={},
            waterfalls={"name": waterfall_entries},
            is_fallback_enabled=is_fallback_enabled,
            visited=set(),
        )
        assert result == expected
