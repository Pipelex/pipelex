from pydantic import BaseModel


class Pipeline(BaseModel):
    pipeline_run_id: str
