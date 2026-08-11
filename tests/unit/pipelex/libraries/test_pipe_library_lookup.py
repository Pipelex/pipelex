from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.libraries.pipe.exceptions import PipeLibraryError, PipeNotFoundError
from pipelex.libraries.pipe.pipe_library import PipeLibrary


def _make_stub_pipe(mocker: MockerFixture, code: str, domain_code: str) -> Any:
    """Create a minimal mock pipe with code, domain_code, and pipe_ref."""
    mock_pipe = mocker.MagicMock()
    mock_pipe.code = code
    mock_pipe.domain_code = domain_code
    mock_pipe.pipe_ref = f"{domain_code}.{code}"
    return mock_pipe


class TestPipeLibraryLookup:
    """Tests for PipeLibrary lookup with pipe_ref-based indexing."""

    # ── Direct pipe_ref lookup ──────────────────────────────────────

    def test_pipe_ref_lookup(self, mocker: MockerFixture):
        """Domain-qualified pipe_ref lookup works as primary path."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["scoring.compute_score"] = mock_pipe
        result = library.get_optional_pipe("scoring.compute_score")
        assert result is mock_pipe

    def test_pipe_ref_wrong_domain_returns_none(self, mocker: MockerFixture):
        """Domain-qualified ref returns None when domain does not exist."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["scoring.compute_score"] = mock_pipe
        result = library.get_optional_pipe("wrong_domain.compute_score")
        assert result is None

    # ── In-body resolution is strict: no bare-code search ────────────

    def test_bare_code_does_not_resolve_in_body(self, mocker: MockerFixture):
        """A bare code is not an in-body reference the library will chase across domains.

        In-body refs arrive qualified, so a bare one reaching here is not a lookup to be helped along.
        Searching for it is what let a pipe reach a pipe no `[exports]` rule had released.
        """
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["scoring.compute_score"] = mock_pipe
        assert library.get_optional_pipe("compute_score") is None

    def test_bare_code_no_match_returns_none(self):
        """Bare code lookup returns None when no pipe has that code."""
        library = PipeLibrary.make_empty()
        result = library.get_optional_pipe("nonexistent")
        assert result is None

    # ── The entry affordance: a code a human typed ───────────────────

    def test_entry_pipe_exact_ref_hits_directly(self, mocker: MockerFixture):
        """A fully-qualified code goes straight through, no search."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["scoring.compute_score"] = mock_pipe
        assert library.get_optional_entry_pipe("scoring.compute_score") is mock_pipe

    def test_entry_pipe_bare_code_matches_across_domains(self, mocker: MockerFixture):
        """`pipelex run compute_score` keeps working: the user is pointing at a pipe, not writing a ref.

        The library holds a second domain with a different code, so the search genuinely has to look
        past a non-match in another domain rather than find the only pipe there is.
        """
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["scoring.compute_score"] = mock_pipe
        library.root["analytics.summarize"] = _make_stub_pipe(mocker, code="summarize", domain_code="analytics")
        assert library.get_optional_entry_pipe("compute_score") is mock_pipe

    def test_entry_pipe_ambiguous_bare_code_raises(self, mocker: MockerFixture):
        """Two domains declaring the code: refuse to guess, and name both so the user can pick."""
        library = PipeLibrary.make_empty()
        library.root["scoring.compute_score"] = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["analytics.compute_score"] = _make_stub_pipe(mocker, code="compute_score", domain_code="analytics")
        with pytest.raises(PipeLibraryError, match="is ambiguous") as exc_info:
            library.get_optional_entry_pipe("compute_score")
        assert "analytics.compute_score" in str(exc_info.value)
        assert "scoring.compute_score" in str(exc_info.value)

    def test_entry_pipe_no_match_returns_none(self):
        library = PipeLibrary.make_empty()
        assert library.get_optional_entry_pipe("nonexistent") is None

    def test_entry_pipe_required_raises_not_found(self):
        library = PipeLibrary.make_empty()
        with pytest.raises(PipeNotFoundError):
            library.get_required_entry_pipe("nonexistent")

    def test_entry_pipe_ignores_aliased_dependency_entries(self, mocker: MockerFixture):
        """An installed package must not make a host pipe's bare code ambiguous.

        Otherwise the entry affordance reintroduces, through its own door, exactly the contextual
        instability the strict in-body rule removes: `pipelex run compute_score` would start failing
        because someone added an unrelated dependency that happens to ship the same code.
        """
        library = PipeLibrary.make_empty()
        host_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["scoring.compute_score"] = host_pipe
        library.add_dependency_pipe(alias="lib", pipe=_make_stub_pipe(mocker, code="compute_score", domain_code="vendor"))

        assert library.get_optional_entry_pipe("compute_score") is host_pipe

    def test_entry_pipe_reaches_a_pipe_no_export_released(self, mocker: MockerFixture):
        """The affordance deliberately does not consult `[exports]`.

        Package visibility governs what one method may reference from inside another. A pipe someone
        names by hand at an entry point is not an in-body reference, so the rule does not apply — and
        the docstring says so, which is worth more with a test under it.
        """
        library = PipeLibrary.make_empty()
        unexported = _make_stub_pipe(mocker, code="internal_helper", domain_code="scoring")
        library.root["scoring.internal_helper"] = unexported

        assert library.get_optional_entry_pipe("internal_helper") is unexported

    # ── Multi-domain coexistence ────────────────────────────────────

    def test_multi_domain_coexistence(self, mocker: MockerFixture):
        """Two pipes with the same code in different domains coexist and are individually retrievable."""
        library = PipeLibrary.make_empty()
        pipe_scoring = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        pipe_analytics = _make_stub_pipe(mocker, code="compute_score", domain_code="analytics")
        library.root["scoring.compute_score"] = pipe_scoring
        library.root["analytics.compute_score"] = pipe_analytics

        assert library.get_optional_pipe("scoring.compute_score") is pipe_scoring
        assert library.get_optional_pipe("analytics.compute_score") is pipe_analytics
        assert len(library.root) == 2

    def test_add_new_pipe_multi_domain(self, mocker: MockerFixture):
        """add_new_pipe stores by pipe_ref so same code in different domains works."""
        library = PipeLibrary.make_empty()
        pipe_scoring = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        pipe_analytics = _make_stub_pipe(mocker, code="compute_score", domain_code="analytics")
        library.add_new_pipe(pipe=pipe_scoring)
        library.add_new_pipe(pipe=pipe_analytics)

        assert "scoring.compute_score" in library.root
        assert "analytics.compute_score" in library.root

    # ── Cross-package refs ──────────────────────────────────────────

    def test_cross_package_ref_with_pipe_ref(self, mocker: MockerFixture):
        """Cross-package ref with domain-qualified remainder resolves correctly."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.add_dependency_pipe(alias="lib", pipe=mock_pipe)
        result = library.get_optional_pipe("lib->scoring.compute_score")
        assert result is mock_pipe

    def test_cross_package_ref_wrong_domain(self, mocker: MockerFixture):
        """Cross-package ref with wrong domain returns None."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.add_dependency_pipe(alias="lib", pipe=mock_pipe)
        result = library.get_optional_pipe("lib->wrong_domain.compute_score")
        assert result is None

    def test_cross_package_ref_bare_code_unambiguous(self, mocker: MockerFixture):
        """Cross-package ref with bare code resolves when unambiguous."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.add_dependency_pipe(alias="lib", pipe=mock_pipe)
        result = library.get_optional_pipe("lib->compute_score")
        assert result is mock_pipe

    # ── Malformed refs ──────────────────────────────────────────────

    @pytest.mark.parametrize(
        "malformed_ref",
        [
            "foo..bar",
            ".foo",
            "foo.",
        ],
    )
    def test_malformed_dotted_ref_returns_none(self, malformed_ref: str):
        """Malformed dotted refs return None instead of raising."""
        library = PipeLibrary.make_empty()
        result = library.get_optional_pipe(malformed_ref)
        assert result is None

    @pytest.mark.parametrize(
        "malformed_ref",
        [
            "lib->foo..bar",
            "lib->.foo",
            "lib->foo.",
        ],
    )
    def test_malformed_cross_package_ref_returns_none(self, malformed_ref: str):
        """Malformed cross-package refs return None instead of raising."""
        library = PipeLibrary.make_empty()
        result = library.get_optional_pipe(malformed_ref)
        assert result is None

    # ── get_required_pipe error cases ───────────────────────────────

    def test_get_required_pipe_malformed_raises_not_found(self):
        """Malformed ref through get_required_pipe raises PipeNotFoundError."""
        library = PipeLibrary.make_empty()
        with pytest.raises(PipeNotFoundError):
            library.get_required_pipe("foo..bar")

    def test_get_required_pipe_domain_mismatch_raises_not_found(self, mocker: MockerFixture):
        """Domain mismatch through get_required_pipe raises PipeNotFoundError."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["scoring.compute_score"] = mock_pipe
        with pytest.raises(PipeNotFoundError):
            library.get_required_pipe("wrong_domain.compute_score")

    # ── Collision tests ───────────────────────────────────────────────

    def test_same_code_different_domains_no_collision(self, mocker: MockerFixture):
        """Same bare code in different domains does NOT collide — this would have failed under old bare-code indexing."""
        library = PipeLibrary.make_empty()
        pipe_scoring = _make_stub_pipe(mocker, code="process", domain_code="scoring")
        pipe_analytics = _make_stub_pipe(mocker, code="process", domain_code="analytics")

        # Both add_new_pipe calls succeed — no collision
        library.add_new_pipe(pipe=pipe_scoring)
        library.add_new_pipe(pipe=pipe_analytics)

        # Both retrievable by pipe_ref
        assert library.get_optional_pipe("scoring.process") is pipe_scoring
        assert library.get_optional_pipe("analytics.process") is pipe_analytics

    def test_same_pipe_ref_collision_raises(self, mocker: MockerFixture):
        """Same pipe_ref (same domain + same code) from separate add calls raises PipeLibraryError."""
        library = PipeLibrary.make_empty()
        pipe_first = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        pipe_duplicate = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")

        library.add_new_pipe(pipe=pipe_first)
        with pytest.raises(PipeLibraryError, match="already exists"):
            library.add_new_pipe(pipe=pipe_duplicate)

    # ── remove_pipes_by_refs ────────────────────────────────────────

    def test_remove_pipes_by_refs(self, mocker: MockerFixture):
        """remove_pipes_by_refs removes pipes by their pipe_ref keys."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["scoring.compute_score"] = mock_pipe
        library.remove_pipes_by_refs(pipe_refs=["scoring.compute_score"])
        assert "scoring.compute_score" not in library.root
