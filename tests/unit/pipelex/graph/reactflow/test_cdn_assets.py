"""Unit tests for the CDN asset constants module."""

import base64
import re

from pipelex.graph.reactflow.standalone_assets import (
    ELKJS,
    ELKJS_VERSION,
    MTHDS_UI_CSS,
    MTHDS_UI_JS,
    MTHDS_UI_VERSION,
    CDNAsset,
)


class TestCdnAssets:
    _SRI_PATTERN = re.compile(r"^sha384-[A-Za-z0-9+/]+=*$")

    def test_assets_are_cdnasset_instances(self) -> None:
        assert isinstance(MTHDS_UI_JS, CDNAsset)
        assert isinstance(MTHDS_UI_CSS, CDNAsset)
        assert isinstance(ELKJS, CDNAsset)

    def test_urls_target_jsdelivr_npm(self) -> None:
        for asset in (MTHDS_UI_JS, MTHDS_UI_CSS, ELKJS):
            assert asset.url.startswith("https://cdn.jsdelivr.net/npm/"), asset.url

    def test_urls_pin_to_declared_versions(self) -> None:
        assert f"@pipelex/mthds-ui@{MTHDS_UI_VERSION}/" in MTHDS_UI_JS.url
        assert f"@pipelex/mthds-ui@{MTHDS_UI_VERSION}/" in MTHDS_UI_CSS.url
        assert f"elkjs@{ELKJS_VERSION}/" in ELKJS.url

    def test_integrity_is_sha384_and_decodes_to_48_bytes(self) -> None:
        for asset in (MTHDS_UI_JS, MTHDS_UI_CSS, ELKJS):
            assert self._SRI_PATTERN.match(asset.integrity), asset.integrity
            digest_b64 = asset.integrity.split("-", 1)[1]
            digest_bytes = base64.b64decode(digest_b64, validate=True)
            assert len(digest_bytes) == 48, f"{asset.integrity} decoded to {len(digest_bytes)} bytes (expected 48)"

    def test_crossorigin_is_anonymous(self) -> None:
        for asset in (MTHDS_UI_JS, MTHDS_UI_CSS, ELKJS):
            assert asset.crossorigin == "anonymous"

    def test_js_and_css_paths_distinguished(self) -> None:
        assert MTHDS_UI_JS.url.endswith("/graph-viewer.js")
        assert MTHDS_UI_CSS.url.endswith("/graph-viewer.css")
        assert ELKJS.url.endswith("/elk.bundled.js")
