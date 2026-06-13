"""End-to-end proof of the additive multi-file library model, backed by real on-disk `.mthds` files.

A same-domain method is authored as separate, additive `.mthds` files (a forward-declared header +
a separate definition) sharing a non-native concept. The bundles live next to this module — one
sub-directory per scenario — so the header/definition split is visible as actual files rather than
inline strings:

    signature_only/        concepts + header (PipeSignature), no definition  -> not yet runnable
    header_and_definition/ concepts + header + concrete definition           -> concrete wins, runnable
    qualified_sibling_ref/ concepts + controller (qualified ref) + definition -> cross-file ref resolves
    cross_batch_library/   root bundle + a separate `-L` library dir          -> bare concept resolves across batches

The shared concept (`KeyFinding`) is deliberately non-native: a native-only contract would pass even
with the cross-file resolution bug present, so it would not prove anything.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.pipeline.validate_bundle import validate_bundle, validate_bundles_from_directory

_BUNDLES_DIR = Path(__file__).parent


@pytest.mark.asyncio(loop_scope="class")
class TestAdditiveMultiFileLibraryE2E:
    async def test_signature_only_is_not_yet_runnable(self, load_empty_library: Callable[[], str]):
        """Header alone (no definition): lenient validation passes, the pipe stays a signature, and the
        unimplemented header is reported as a pending signature — i.e. the bundle is not yet runnable.
        """
        load_empty_library()
        result = await validate_bundles_from_directory(directory=_BUNDLES_DIR / "signature_only", allow_signatures=True)

        pipe_codes = {pipe.code for pipe in result.pipes}
        assert {"find_key_findings", "research_brief"} <= pipe_codes
        find_key_findings = next(pipe for pipe in result.pipes if pipe.code == "find_key_findings")
        assert find_key_findings.is_signature
        # `is_runnable` on the validate JSON envelope is exactly `not pending_signatures`.
        assert result.pending_signatures == ["research.find_key_findings"]

    async def test_definition_reconciles_with_header_and_is_runnable(self, load_empty_library: Callable[[], str]):
        """Adding the concrete definition lets strict validation pass: the concrete replaces the
        signature, and nothing is left pending — the assembled library is runnable. The header's bare
        `Text`/`KeyFinding` contract reconciles with the definition's qualified `native.Text`/
        `research.KeyFinding` spelling, proving the comparison is by normalized concept identity.
        """
        load_empty_library()
        result = await validate_bundles_from_directory(directory=_BUNDLES_DIR / "header_and_definition", allow_signatures=False)

        find_key_findings = next((pipe for pipe in result.pipes if pipe.code == "find_key_findings"), None)
        assert find_key_findings is not None
        assert not find_key_findings.is_signature
        assert result.pending_signatures == []

    async def test_qualified_sibling_pipe_ref_resolves_across_files(self, load_empty_library: Callable[[], str]):
        """A controller's QUALIFIED same-domain step ref (`research.find_key_findings`) resolves to a
        concrete pipe declared only in a sibling file.
        """
        load_empty_library()
        result = await validate_bundles_from_directory(directory=_BUNDLES_DIR / "qualified_sibling_ref", allow_signatures=False)

        pipe_codes = {pipe.code for pipe in result.pipes}
        assert {"research_brief", "find_key_findings"} <= pipe_codes
        assert result.pending_signatures == []

    async def test_bare_concept_ref_resolves_across_load_batches(self, load_empty_library: Callable[[], str]):
        """A root bundle references `KeyFinding` by bare code while the concept is declared in a
        separate `-L` library directory loaded as its own batch.
        """
        load_empty_library()
        scenario_dir = _BUNDLES_DIR / "cross_batch_library"
        result = await validate_bundle(
            mthds_file_path=scenario_dir / "root.mthds",
            library_dirs=[scenario_dir / "library"],
            allow_signatures=False,
        )

        assert "extract_finding" in {pipe.code for pipe in result.pipes}
        assert result.pending_signatures == []
