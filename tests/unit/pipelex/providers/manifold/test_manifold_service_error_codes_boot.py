"""The session's boot installs the Manifold service's refusal codes on the hub, where classification reads them.

The package's other tests hand the classifier the Manifold vocabulary through the autouse fixture, which
patches the classifier's binding; this one reads the hub's own accessor, which that fixture leaves alone,
so it fails if the plugin stops contributing its codes or the boot stops installing them.
"""

from __future__ import annotations

from pipelex.providers.manifold.manifold_error_codes import MANIFOLD_SERVICE_ERROR_CODES
from pipelex.runtime_hub import get_optional_service_error_vocabulary


class TestManifoldServiceErrorCodesBoot:
    def test_boot_installs_every_manifold_code_on_the_hub(self) -> None:
        vocabulary = get_optional_service_error_vocabulary()

        assert vocabulary is not None
        missing = {entry.code for entry in MANIFOLD_SERVICE_ERROR_CODES} - set(vocabulary.codes)
        assert not missing, f"The booted vocabulary lacks Manifold codes: {sorted(missing)}"
