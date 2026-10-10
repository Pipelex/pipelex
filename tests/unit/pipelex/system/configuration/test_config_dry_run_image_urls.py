"""`inference.dry_run.image_urls` is a non-empty list of URLs, and anything else is refused as a validation error."""

import pytest
from pydantic import ValidationError

from pipelex.cogt.config_cogt import DryRunConfig
from tests.unit.pipelex.system.configuration.config_section_utils import base_config_section


class TestDryRunConfigImageUrls:
    def test_an_empty_list_is_a_validation_error(self) -> None:
        """It used to raise a bare `PipelexConfigError` from inside the validator, which escaped the config load's wrap."""
        with pytest.raises(ValidationError, match=r"inference\.dry_run\.image_urls must be a non-empty list"):
            DryRunConfig.model_validate({**base_config_section("inference", "dry_run"), "image_urls": []})

    def test_a_string_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Input should be a valid list"):
            DryRunConfig.model_validate({**base_config_section("inference", "dry_run"), "image_urls": "https://example.com/a.png"})
