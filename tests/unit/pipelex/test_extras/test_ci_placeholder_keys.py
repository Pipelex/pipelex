import re
import tomllib
from pathlib import Path
from typing import Any, cast

from pipelex.test_extras.shared_pytest_plugins import ENV_VAR_KEYS_WHICH_MAY_NEED_PLACEHOLDERS_IN_CI

KIT_BACKENDS_PATH = Path(__file__).parents[4] / "pipelex" / "kit" / "configs" / "inference" / "backends.toml"

# `${VAR}` and `${env:VAR}`. A `${secret:…}` reference is resolved by the secrets provider and a
# fallback chain (`|`) carries its own default, so neither needs a CI placeholder.
_ENV_REFERENCE = re.compile(r"\$\{(?:env:)?([A-Z0-9_]+)\}")


class TestCiPlaceholderKeys:
    def test_every_enabled_kit_backend_variable_gets_a_ci_placeholder(self) -> None:
        """A kit backend shipped enabled must have each of its variables in the CI placeholder list.

        CI runners hold no provider keys at all, and every test module boots live, so an enabled
        backend whose variable is not given a placeholder fails the boot of every shard — which is
        what a new bring-your-own-key backend does if this list is forgotten.
        """
        backends = cast("dict[str, dict[str, Any]]", tomllib.loads(KIT_BACKENDS_PATH.read_text(encoding="utf-8")))
        missing: dict[str, str] = {}
        for backend_name, backend_table in backends.items():
            if not backend_table.get("enabled", True):
                continue
            for value in backend_table.values():
                if not isinstance(value, str):
                    continue
                for var_name in _ENV_REFERENCE.findall(value):
                    if var_name not in ENV_VAR_KEYS_WHICH_MAY_NEED_PLACEHOLDERS_IN_CI:
                        missing[var_name] = backend_name
        assert not missing, f"Add these to ENV_VAR_KEYS_WHICH_MAY_NEED_PLACEHOLDERS_IN_CI (variable -> backend): {missing}"
