from pipelex.tools.misc.package_utils import get_package_version
from pipelex.urls import URLs


def get_user_agent() -> str:
    version = get_package_version()
    homepage_url = URLs.homepage
    return f"Pipelex/{version} ({homepage_url})"
