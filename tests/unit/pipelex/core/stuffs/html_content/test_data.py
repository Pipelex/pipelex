from typing import Any, ClassVar


class TestData:
    # Input content
    SAMPLE_INNER_HTML = "<p>Hello World</p>"
    SAMPLE_CSS_CLASS = "my-class"

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP: ClassVar[dict[str, Any]] = {"inner_html": "<p>Hello World</p>", "css_class": "my-class"}
    EXPECTED_SMART_DUMP_NO_CLASS: ClassVar[dict[str, Any]] = {"inner_html": "<p>Hello World</p>", "css_class": None}

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = "<p>Hello World</p>"
    EXPECTED_RENDERED_MARKDOWN = "<p>Hello World</p>"
    EXPECTED_RENDERED_HTML = '<div class="my-class"><p>Hello World</p></div>'
    # The JSON rendering is the MODEL's, member for member. It used to rename
    # `inner_html` to `html`, which made a payload that did not satisfy the schema
    # its own output contract publishes - `native.Html` pins `inner_html` and pins
    # it required, so a consumer reading the contract found the member absent and
    # a member the standard does not define in its place.
    EXPECTED_RENDERED_JSON: ClassVar[dict[str, Any]] = {"inner_html": "<p>Hello World</p>", "css_class": "my-class"}
    EXPECTED_RENDERED_JSON_NO_CLASS: ClassVar[dict[str, Any]] = {"inner_html": "<p>Hello World</p>", "css_class": None}
    EXPECTED_RENDERED_HTML_NO_CLASS = "<p>Hello World</p>"
    EXPECTED_RENDERED_FOR_PROMPT = "<p>Hello World</p>"

    # XSS protection test cases
    XSS_CSS_CLASS = '<script>alert("xss")</script>'
    EXPECTED_XSS_PROTECTED_HTML = '<div class="&lt;script&gt;alert(&#34;xss&#34;)&lt;/script&gt;"><p>Hello World</p></div>'
