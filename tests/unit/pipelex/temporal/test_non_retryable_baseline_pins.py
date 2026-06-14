"""Pin the deterministic dry-run error classes into the baseline ``non_retryable_error_types``.

The terminality contract of the dry-run mock errors rests on a *string* linkage: the class name
literal in ``pipelex/pipelex.toml`` must match ``cls.__name__``. A rename on either side silently
makes a deterministic failure retryable again — the retry-forever / wasted-retry family this
project has already been bitten by — with the whole suite staying green. This test makes that
drift loud.
"""

from pathlib import Path

import tomli

from pipelex.cogt.content_generation.exceptions import DryRunMockBuildError, DryRunObjectFidelityError


class TestNonRetryableBaselinePins:
    def test_deterministic_dry_errors_are_pinned_non_retryable(self) -> None:
        toml_path = Path(__file__).parents[4] / "pipelex" / "pipelex.toml"
        config = tomli.loads(toml_path.read_text(encoding="utf-8"))
        baseline = config["temporal"]["worker_config"]["retry_policy_config"]["non_retryable_error_types"]

        assert DryRunMockBuildError.__name__ in baseline
        assert DryRunObjectFidelityError.__name__ in baseline
