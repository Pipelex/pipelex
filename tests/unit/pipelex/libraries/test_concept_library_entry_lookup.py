"""The concept entry affordance: how a human-supplied concept string resolves.

Mirrors the pipe-side entry affordance deliberately without sharing code with it (see
wip/pipe-refs/entry-affordance-share-vs-duplicate.md). The rows only discriminate against the
old crate-wide rule when a sibling domain declares the same code — a single-domain fixture
passes under either rule — so most cases here build the two-domain `alpha`/`beta` fixture.
"""

import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptLibraryConceptNotFoundError
from pipelex.libraries.concept.concept_library import ConceptLibrary


def _make_concept(*, code: str, domain_code: str) -> Concept:
    return ConceptFactory.make(
        concept_code=code,
        domain_code=domain_code,
        description=f"{domain_code} {code}",
        structure_class_name="TextContent",
    )


class TestConceptLibraryEntryLookup:
    # ── Fully-specified refs ────────────────────────────────────────

    def test_exact_ref_hits_directly(self):
        library = ConceptLibrary.make_empty()
        memo_alpha = _make_concept(code="Memo", domain_code="alpha")
        library.add_new_concept(concept=memo_alpha)
        assert library.get_optional_entry_concept("alpha.Memo") is memo_alpha

    def test_exact_ref_wrong_domain_returns_none(self):
        library = ConceptLibrary.make_empty()
        library.add_new_concept(concept=_make_concept(code="Memo", domain_code="alpha"))
        assert library.get_optional_entry_concept("beta.Memo") is None

    def test_cross_package_ref_is_a_direct_hit(self):
        library = ConceptLibrary.make_empty()
        dep_memo = _make_concept(code="Memo", domain_code="dep_domain")
        library.add_dependency_concept(alias="lib", concept=dep_memo)
        assert library.get_optional_entry_concept("lib->dep_domain.Memo") is dep_memo
        assert library.get_optional_entry_concept("other->dep_domain.Memo") is None

    # ── Natives resolve first (the standard's step 1) ───────────────

    def test_native_wins_over_a_domain_declared_same_code(self):
        library = ConceptLibrary.make_empty_with_native_concepts()
        library.root["alpha.Text"] = _make_concept(code="Text", domain_code="alpha")
        resolved = library.get_required_entry_concept("Text", search_scope="alpha")
        assert resolved.concept_ref == "native.Text"

    # ── Bare codes: scope preference, then crate-wide unique match ──

    def test_bare_code_own_only_resolves_through_scope(self):
        library = ConceptLibrary.make_empty()
        memo_alpha = _make_concept(code="Memo", domain_code="alpha")
        library.add_new_concept(concept=memo_alpha)
        assert library.get_optional_entry_concept("Memo", search_scope="alpha") is memo_alpha

    def test_bare_code_sibling_only_falls_back_crate_wide(self):
        """A scope that lacks the code no longer kills the lookup (the old multi-domain walk
        raised the first miss as a ConceptLibraryError that bypassed every caller's handler).
        """
        library = ConceptLibrary.make_empty()
        memo_beta = _make_concept(code="Memo", domain_code="beta")
        library.add_new_concept(concept=memo_beta)
        assert library.get_optional_entry_concept("Memo", search_scope="alpha") is memo_beta

    def test_bare_code_both_declare_prefers_the_scope(self):
        """The entry pipe's own domain wins over a same-named sibling — the preference the old
        code expressed with an insert(0) that could never fire, now actually deciding.
        """
        library = ConceptLibrary.make_empty()
        memo_alpha = _make_concept(code="Memo", domain_code="alpha")
        memo_beta = _make_concept(code="Memo", domain_code="beta")
        library.add_new_concept(concept=memo_alpha)
        library.add_new_concept(concept=memo_beta)
        assert library.get_optional_entry_concept("Memo", search_scope="alpha") is memo_alpha
        assert library.get_optional_entry_concept("Memo", search_scope="beta") is memo_beta

    def test_bare_code_ambiguous_without_scope_raises_naming_candidates(self):
        library = ConceptLibrary.make_empty()
        library.add_new_concept(concept=_make_concept(code="Memo", domain_code="alpha"))
        library.add_new_concept(concept=_make_concept(code="Memo", domain_code="beta"))
        with pytest.raises(ConceptLibraryConceptNotFoundError, match="ambiguous") as exc_info:
            library.get_optional_entry_concept("Memo")
        assert "alpha.Memo" in str(exc_info.value)
        assert "beta.Memo" in str(exc_info.value)

    def test_bare_code_nowhere_returns_none_and_required_raises(self):
        library = ConceptLibrary.make_empty()
        assert library.get_optional_entry_concept("Memo") is None
        with pytest.raises(ConceptLibraryConceptNotFoundError, match="not found"):
            library.get_required_entry_concept("Memo")

    def test_invalid_string_raises_the_one_catchable_class(self):
        """Every entry refusal — invalid string included — is ConceptLibraryConceptNotFoundError,
        so the input-shaping boundary catches a single exception class.
        """
        library = ConceptLibrary.make_empty()
        with pytest.raises(ConceptLibraryConceptNotFoundError, match="not a valid"):
            library.get_optional_entry_concept("not_pascal_case")

    # ── Aliased dependency entries ──────────────────────────────────

    def test_crate_wide_search_ignores_aliased_dependency_entries(self):
        """An installed package must not make a host concept's bare code ambiguous."""
        library = ConceptLibrary.make_empty()
        host_memo = _make_concept(code="Memo", domain_code="alpha")
        library.add_new_concept(concept=host_memo)
        library.add_dependency_concept(alias="lib", concept=_make_concept(code="Memo", domain_code="vendor"))
        assert library.get_optional_entry_concept("Memo") is host_memo

    def test_bare_code_with_aliased_scope_reaches_the_dependency_concept(self):
        """Package-scoped preference: when the entry pipe came from a dependency, its scope
        carries the alias (`lib->dep_domain`), so the dependency's own concept — keyed under
        the alias and invisible to the crate-wide scan — is a direct scoped hit.
        """
        library = ConceptLibrary.make_empty()
        dep_memo = _make_concept(code="Memo", domain_code="dep_domain")
        library.add_dependency_concept(alias="lib", concept=dep_memo)
        assert library.get_optional_entry_concept("Memo", search_scope="lib->dep_domain") is dep_memo
        # Without the aliased scope, the aliased entry stays out of reach of a bare code.
        assert library.get_optional_entry_concept("Memo") is None

    def test_dotted_ref_with_aliased_scope_reaches_the_dependency_domain(self):
        """A dependency package can span several domains: a dotted ref naming one of them
        resolves through the scope's alias — and the scope wins even when the host declares the
        same `domain.Concept` spelling, mirroring the bare-code arm's precedence. Without an
        aliased scope, the host concept is the only reachable one.
        """
        library = ConceptLibrary.make_empty()
        dep_note = _make_concept(code="Note", domain_code="dep_other")
        library.add_dependency_concept(alias="lib", concept=dep_note)
        assert library.get_optional_entry_concept("dep_other.Note", search_scope="lib->dep_domain") is dep_note
        host_note = _make_concept(code="Note", domain_code="dep_other")
        library.add_new_concept(concept=host_note)
        assert library.get_optional_entry_concept("dep_other.Note", search_scope="lib->dep_domain") is dep_note
        assert library.get_optional_entry_concept("dep_other.Note") is host_note

    def test_bare_code_reaches_a_sibling_domain_of_the_dependency_package(self):
        """A multi-domain dependency keys every concept under its one alias: an entry pipe in one
        of its domains can still resolve a bare code declared in a sibling domain of the same
        package — the package search that the alias-excluding crate-wide scan cannot perform.
        """
        library = ConceptLibrary.make_empty()
        dep_memo = _make_concept(code="Memo", domain_code="dep_b")
        library.add_dependency_concept(alias="lib", concept=dep_memo)
        assert library.get_optional_entry_concept("Memo", search_scope="lib->dep_a") is dep_memo
        # A same-code host concept does not shadow the package's own concept under an aliased scope.
        library.add_new_concept(concept=_make_concept(code="Memo", domain_code="host_domain"))
        assert library.get_optional_entry_concept("Memo", search_scope="lib->dep_a") is dep_memo

    def test_bare_code_ambiguous_within_the_dependency_package_raises(self):
        library = ConceptLibrary.make_empty()
        library.add_dependency_concept(alias="lib", concept=_make_concept(code="Memo", domain_code="dep_a"))
        library.add_dependency_concept(alias="lib", concept=_make_concept(code="Memo", domain_code="dep_b"))
        with pytest.raises(ConceptLibraryConceptNotFoundError, match="ambiguous") as exc_info:
            library.get_optional_entry_concept("Memo", search_scope="lib->dep_c")
        assert "lib->dep_a.Memo" in str(exc_info.value)
        assert "lib->dep_b.Memo" in str(exc_info.value)

    def test_aliased_bare_ref_searches_that_package_only(self):
        """`alias->Concept` is the explicit spelling of the package search: it resolves a bare
        code within the named dependency and never reaches a host concept.
        """
        library = ConceptLibrary.make_empty()
        dep_memo = _make_concept(code="Memo", domain_code="dep_b")
        library.add_dependency_concept(alias="lib", concept=dep_memo)
        library.add_new_concept(concept=_make_concept(code="Memo", domain_code="host_domain"))
        assert library.get_optional_entry_concept("lib->Memo") is dep_memo
        assert library.get_optional_entry_concept("other->Memo") is None
