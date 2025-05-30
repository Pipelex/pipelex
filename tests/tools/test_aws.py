import pytest

from pipelex.config import get_config
from pipelex.tools.aws.aws_config import AwsKeyMethod


# Not testing AwsKeyMethod.ENV because it's not supposed to work in the test environment.
# @pytest.fixture(params=list(AwsKeyMethod))
@pytest.fixture(params=[AwsKeyMethod.SECRET_PROVIDER])
def aws_key_method(request: pytest.FixtureRequest) -> AwsKeyMethod:
    assert isinstance(request.param, AwsKeyMethod)
    return request.param


@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
def test_get_aws_access_keys(aws_key_method: AwsKeyMethod):
    aws_config = get_config().pipelex.aws_config
    aws_access_key_id, aws_secret_access_key, aws_region = aws_config.get_aws_access_keys_with_method(api_key_method=aws_key_method)
    assert aws_access_key_id
    assert aws_secret_access_key
    assert aws_region
