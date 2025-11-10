from pydantic import BaseModel, ConfigDict


class DomainBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    code: str
    description: str
    system_prompt: str | None = None
    main_pipe: str | None = None
