import pytest

from pipelex.cogt.imgg.imgg_handle import ImggHandle


@pytest.fixture(
    params=[
        ImggHandle.FLUX_1_PRO_LEGACY,
        ImggHandle.FLUX_1_1_PRO,
        ImggHandle.FLUX_1_1_ULTRA,
        ImggHandle.SDXL_LIGHTNING,
        ImggHandle.OPENAI_GPT_IMAGE_1,
    ]
)
def imgg_handle(request: pytest.FixtureRequest) -> ImggHandle:
    assert isinstance(request.param, ImggHandle)
    return request.param
