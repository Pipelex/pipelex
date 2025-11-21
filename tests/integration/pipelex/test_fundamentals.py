import pytest


# We use gha_disabled here because those tests are called directly and explicitly by the tests-check.yml file before the rest of the tests.
@pytest.mark.gha_disabled
class TestFundamentals:
    def test_boot(self):
        # This test does nothing but the conftest runs Pipelex.make()
        # Therefore this test will fail if Pipelex.make() fails.
        pass
