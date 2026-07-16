"""Tests for LibraryManager blueprint accumulation, get_crate(), and fingerprint idempotency."""

from typing import cast

import pytest
from pytest_mock import MockerFixture

from pipelex.hub import clear_current_library, get_library_manager, set_current_library
from pipelex.libraries.library import Library
from pipelex.libraries.library_manager import LibraryManager
from tests.unit.pipelex.libraries.test_library_crate_data import BlueprintSamples


class TestLibraryCrateAccumulation:
    """Tests for blueprint accumulation and get_crate() on LibraryManager."""

    def test_get_crate_returns_none_for_unknown_library_id(self):
        """get_crate() returns None for a library_id that was never opened."""
        manager = LibraryManager()
        result = manager.get_crate(library_id="nonexistent")
        assert result is None

    def test_get_crate_returns_none_when_no_blueprints_loaded(self):
        """get_crate() returns None when a library exists but no blueprints were loaded."""
        manager = LibraryManager()
        manager.open_library(library_id="test-lib")
        result = manager.get_crate(library_id="test-lib")
        assert result is None

    def test_get_crate_builds_crate_from_accumulated_blueprints(self):
        """get_crate() builds a crate containing all concepts and pipes from loaded blueprints.

        Uses the hub's LibraryManager + set_current_library so that load_from_blueprints()
        can resolve concepts through the hub during pipe construction.
        """
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)
        try:
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[BlueprintSamples.SCORING_BUNDLE])

            crate = library_manager.get_crate(library_id=library_id)
            assert crate is not None
            assert "scoring.WeightedScore" in crate.concepts
            assert "scoring.compute_score" in crate.pipes
            assert crate.fingerprint != ""
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    def test_multiple_load_from_blueprints_all_included_in_crate(self):
        """Blueprints from multiple load_from_blueprints() calls are all included in the crate."""
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)
        try:
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[BlueprintSamples.SCORING_BUNDLE])
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[BlueprintSamples.ANALYTICS_BUNDLE])

            crate = library_manager.get_crate(library_id=library_id)
            assert crate is not None
            # From first load
            assert "scoring.WeightedScore" in crate.concepts
            assert "scoring.compute_score" in crate.pipes
            # From second load
            assert "analytics.Metric" in crate.concepts
            assert "analytics.compute_metric" in crate.pipes
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    def test_load_from_crate_idempotent_on_same_fingerprint(self):
        """load_from_crate() returns empty list on second call with the same fingerprint."""
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)
        try:
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[BlueprintSamples.SCORING_BUNDLE])

            crate = library_manager.get_crate(library_id=library_id)
            assert crate is not None

            # Open a second library to load the crate into
            second_library_id = "idempotency-test-lib"
            library_manager.open_library(library_id=second_library_id)

            # First load should return pipes
            pipes_first = library_manager.load_from_crate(library_id=second_library_id, crate=crate)
            assert len(pipes_first) > 0

            # Second load with same fingerprint should be skipped (empty list)
            pipes_second = library_manager.load_from_crate(library_id=second_library_id, crate=crate)
            assert pipes_second == []

            library_manager.teardown(library_id=second_library_id)
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    def test_is_crate_loaded_tracks_fingerprint_lifecycle(self):
        """is_crate_loaded() is False before load, True after, and False again after teardown."""
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)
        try:
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[BlueprintSamples.SCORING_BUNDLE])

            crate = library_manager.get_crate(library_id=library_id)
            assert crate is not None

            second_library_id = "is-crate-loaded-test-lib"
            library_manager.open_library(library_id=second_library_id)

            assert library_manager.is_crate_loaded(library_id="nonexistent", fingerprint=crate.fingerprint) is False
            assert library_manager.is_crate_loaded(library_id=second_library_id, fingerprint=crate.fingerprint) is False

            library_manager.load_from_crate(library_id=second_library_id, crate=crate)
            assert library_manager.is_crate_loaded(library_id=second_library_id, fingerprint=crate.fingerprint) is True
            assert library_manager.is_crate_loaded(library_id=second_library_id, fingerprint="some-other-fingerprint") is False

            library_manager.teardown(library_id=second_library_id)
            assert library_manager.is_crate_loaded(library_id=second_library_id, fingerprint=crate.fingerprint) is False
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    def test_teardown_clears_blueprints_for_library_id(self):
        """teardown(library_id) clears accumulated blueprints for that library_id."""
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)
        try:
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[BlueprintSamples.SCORING_BUNDLE])

            # Verify crate exists before teardown
            crate = library_manager.get_crate(library_id=library_id)
            assert crate is not None

            # Teardown
            library_manager.teardown(library_id=library_id)

            # After teardown, get_crate should return None (library_id no longer known)
            result = library_manager.get_crate(library_id=library_id)
            assert result is None
        finally:
            clear_current_library()

    def test_failed_load_from_crate_does_not_cache_fingerprint(self, mocker: MockerFixture):
        """A failed load_from_crate() must not cache the fingerprint, allowing retries."""
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)
        try:
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[BlueprintSamples.SCORING_BUNDLE])

            crate = library_manager.get_crate(library_id=library_id)
            assert crate is not None

            # Open a target library to load the crate into
            target_library_id = "failure-retry-test-lib"
            library_manager.open_library(library_id=target_library_id)

            try:
                # Make validate_library raise to simulate a load failure (Library is a frozen
                # Pydantic model, so we patch the class method rather than the instance)
                mocker.patch.object(Library, "validate_library", side_effect=RuntimeError("simulated failure"))

                with pytest.raises(RuntimeError, match="simulated failure"):
                    library_manager.load_from_crate(library_id=target_library_id, crate=crate)

                # Fingerprint must NOT be cached — a retry should attempt loading again
                concrete_manager = cast("LibraryManager", library_manager)
                loaded_set = concrete_manager._loaded_fingerprints.get(target_library_id, set())  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                assert crate.fingerprint not in loaded_set
            finally:
                library_manager.teardown(library_id=target_library_id)
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()
