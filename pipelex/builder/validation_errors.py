from pydantic import BaseModel


class SyntaxErrorData(BaseModel):
    message: str
    lineno: int | None = None
    offset: int | None = None
    text: str | None = None
    end_lineno: int | None = None
    end_offset: int | None = None

    @classmethod
    def from_syntax_error(cls, syntax_error: SyntaxError) -> "SyntaxErrorData":
        return cls(
            message=syntax_error.msg,
            lineno=syntax_error.lineno,
            offset=syntax_error.offset,
            text=syntax_error.text,
            end_lineno=syntax_error.end_lineno,
            end_offset=syntax_error.end_offset,
        )
