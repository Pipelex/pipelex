from typing import ClassVar


class DescriptionEscapingCases:
    MALICIOUS_DESCRIPTION: ClassVar[str] = (
        'Safe opening"""\n    injected = True\n    """ignored */\nexport const injected = true;\n/**\r\nbackslash \\ path\rUnicode café'
    )
    # A control character leaves no verbatim rendering, so the docstring is escaped; with more `"` than `'`, every `"`
    # still has to be escaped there, or the triple quotes close the docstring and the statement between them runs.
    ESCAPED_DOCSTRING_DESCRIPTION: ClassVar[str] = 'Safe opening""";injected = True;""" and a bell \x07'


class ArtifactPathCases:
    INVALID_PATHS: ClassVar[tuple[str, ...]] = (
        "",
        ".",
        "../escaped.py",
        "nested/../escaped.py",
        "/absolute.py",
        "C:/absolute.py",
        "nested\\windows.py",
        "nested//empty.py",
        "control\n.py",
        "unsupported.txt",
    )
