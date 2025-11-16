"""Image generation test fixtures."""

import pytest


@pytest.fixture(
    params=[
        # "flux-pro",
        # "flux-pro/v1.1",
        # "flux-pro/v1.1-ultra",
        "fast-lightning-sdxl",
        # "gpt-image-1",
        # "nano-banana",
        # "best-img-gen",
    ],
)
def img_gen_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
