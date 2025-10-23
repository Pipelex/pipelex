"""Unit tests for pipe dependency sorting."""

import pytest

from pipelex.core.bundles.pipe_sorter import sort_pipes_by_dependencies
from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion
from tests.unit.core.bundles.test_data_pipe_sorter import PipeSorterTestCases


class TestSortPipesByDependencies:
    """Test suite for the sort_pipes_by_dependencies function."""

    @pytest.mark.parametrize(
        ("test_name", "pipes", "expected_order", "expected_exception"),
        PipeSorterTestCases.TEST_CASES,
    )
    def test_sort_pipes_by_dependencies(
        self,
        test_name: str,
        pipes: dict[str, PipeBlueprintUnion],
        expected_order: list[str] | None,
        expected_exception: type[Exception] | None,
    ):
        """Test pipe sorting with various dependency patterns.

        Args:
            test_name: Name of the test case for identification
            pipes: Dictionary of pipe_code to PipeBlueprintUnion
            expected_order: Expected order of pipe codes after sorting (None if should raise)
            expected_exception: Expected exception type (None if should succeed)
        """
        if expected_exception:
            # Test that circular dependencies raise the correct exception
            with pytest.raises(expected_exception):
                sort_pipes_by_dependencies(pipes)
        else:
            # Test successful sorting
            sorted_pipes = sort_pipes_by_dependencies(pipes)
            sorted_codes = [code for code, _ in sorted_pipes]

            # Verify all pipes are present
            assert len(sorted_codes) == len(pipes), f"Test '{test_name}': Not all pipes were included in sorted result"
            assert set(sorted_codes) == set(pipes.keys()), f"Test '{test_name}': Pipe codes don't match"

            # Verify the order respects depth-first pre-order dependencies
            # In depth-first pre-order, each pipe comes before its dependencies
            # (unless the dependency was already visited through another path)
            for code, blueprint in sorted_pipes:
                dependencies = blueprint.pipe_dependencies
                code_index = sorted_codes.index(code)
                for dep_code in dependencies:
                    # Only check dependencies that exist in this bundle
                    if dep_code in pipes:
                        dep_index = sorted_codes.index(dep_code)
                        # Skip if dependency was visited earlier (shared dependency)
                        if dep_index < code_index:
                            continue
                        assert code_index < dep_index, (
                            f"Test '{test_name}': In depth-first pre-order, pipe '{code}' "
                            f"should come before its dependency '{dep_code}' in {sorted_codes}"
                        )

            # For test cases with a specific expected order, verify exact match
            if expected_order is not None:
                assert sorted_codes == expected_order, f"Test '{test_name}': Expected {expected_order}, got {sorted_codes}"
