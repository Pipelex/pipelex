from pathlib import Path

import pytest

from pipelex.pipeline.validate_bundle import validate_bundle, validate_bundles_from_directory


@pytest.mark.asyncio
class TestOutOfOrderRefines:
    """Integration tests for out-of-order concept refinement bug."""

    async def test_simple_out_of_order_refines_single_file(self):
        """Test that concept loading fails when refining concept is defined before base (single file).

        This test reproduces the bug where:
        1. VIPCustomer is defined BEFORE Customer in the MTHDS file
        2. VIPCustomer refines Customer
        3. When loading concepts, VIPCustomer is processed first
        4. ConceptFactory._handle_refines tries to generate a structure class
           that inherits from Customer
        5. Customer's class isn't registered yet, so lookup fails
        6. Error: "Base class 'Customer' not found in native classes or class registry"
        """
        mthds_file_path = Path(__file__).parent / "out_of_order_refines.mthds"
        assert mthds_file_path.exists(), f"MTHDS file not found: {mthds_file_path}"

        # validate_bundle internally loads libraries which triggers ConceptFactory.make_from_blueprint
        # This should fail because VIPCustomer is defined before Customer
        # with pytest.raises(ConceptFactoryError) as exc_info:
        await validate_bundle(mthds_file_path=mthds_file_path)

    async def test_multi_level_out_of_order_refines_across_files(self):
        """Test multi-level refinement chain fails when concepts are out of order across files.

        This test reproduces a more complex scenario where:

        File 1 (base_domain.mthds):
          - Person (root concept with structure)

        File 2 (middle_domain.mthds) - concepts defined in REVERSE order:
          - PlatinumCustomer refines VIPCustomer (defined FIRST)
          - VIPCustomer refines Customer (defined SECOND)
          - Customer refines Person (defined THIRD)

        The inheritance chain is: PlatinumCustomer -> VIPCustomer -> Customer -> Person

        When loading middle_domain.mthds:
        1. PlatinumCustomer is processed first
        2. It tries to refine VIPCustomer, but VIPCustomer is not yet registered
        3. Error: "Base class 'VIPCustomer' not found in native classes or class registry"

        This demonstrates the bug with:
        - Multi-level inheritance chains
        - Cross-file concept dependencies
        - All concepts defined in the wrong order
        """
        multi_file_dir = Path(__file__).parent / "multi_file"
        assert multi_file_dir.exists(), f"Multi-file test directory not found: {multi_file_dir}"
        assert (multi_file_dir / "base_domain.mthds").exists(), "base_domain.mthds not found"
        assert (multi_file_dir / "middle_domain.mthds").exists(), "middle_domain.mthds not found"

        # validate_bundles_from_directory loads all MTHDS files in the directory
        # Files are loaded in order, but within middle_domain.mthds concepts are out of order
        # with pytest.raises(ConceptFactoryError) as exc_info:
        await validate_bundles_from_directory(directory=multi_file_dir)
