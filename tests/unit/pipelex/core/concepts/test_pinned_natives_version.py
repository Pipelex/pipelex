"""The label on the pinned native set, held against the standard this engine implements.

`PINNED_NATIVES_MTHDS_VERSION` names the standard version in which the pinned native set last
changed. The authority on that number is the standard's own page, and `test_pinned_natives_vs_standard.py`
holds the constant to it — but that comparison reads the sibling `mthds/` checkout and skips without
it, which is most contributors most of the time. This module is the reading that needs nothing but
the installed `mthds`.

It is a bound in one direction, deliberately: without the page, nothing here can know whether the
standard re-pinned the set at its latest version, so a label that *lags* a re-pinning — which is how
this constant sat at `1.0.0` across the standard's `2.0.0` cut — is the page comparison's to catch
and not this one's. What this module catches is the other direction, a label naming a standard
version this engine does not implement.
"""

from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.core.concepts.native.pinned_blueprints import PINNED_NATIVES_MTHDS_VERSION
from pipelex.tools.misc.semver import parse_version


class TestPinnedNativesVersionAgreesWithTheEngine:
    def test_pinned_set_is_not_from_a_standard_version_this_engine_does_not_implement(self):
        """An implementation of standard version `V` materializes the greatest pinned set not above `V`.

        `pinned_blueprints.py` holds exactly one pinned set, so the rule reduces to a bound: the set
        it holds cannot have been pinned by a standard version later than the one the installed
        `mthds` implements. A pin bump that moves the standard backwards, or a re-pinning transcribed
        into this repo ahead of the `mthds` bump that carries it, fails this without needing the page.
        """
        assert parse_version(PINNED_NATIVES_MTHDS_VERSION) <= parse_version(MTHDS_STANDARD_VERSION), (
            f"the pinned native set is labelled {PINNED_NATIVES_MTHDS_VERSION!r}, later than the standard version this "
            f"engine implements ({MTHDS_STANDARD_VERSION!r}) — this engine cannot materialize a set pinned in the future"
        )
